# Implementation Plan: YouTube RAG Pipeline

## Overview
Implementare una pipeline RAG automatizzata per estrarre video YouTube da un canale specifico, scaricare le trascrizioni con timestamp, eseguire chunking intelligente tramite Docling, generare embeddings e salvare tutto in Supabase con pgvector per ricerca semantica.

## Requirements Summary
- Estrarre solo video nuovi (ultimi 7 giorni) da UN canale YouTube specifico
- Utilizzare YouTube Data API v3 ufficiale per search + Captions API per trascrizioni
- Supportare trascrizioni ufficiali con fallback su auto-generated
- Limitare lingue a italiano e inglese
- Chunking ibrido tramite Docling con preservazione dei timestamp
- Metadata completi per ogni chunk: URL video, channel ID, start_time, end_time, chunk_index
- Deduplicazione: verificare DB prima di processare video già esistenti
- Retry logic: 1 solo tentativo extra su fallimento trascrizione
- Trigger manuale (CLI) per fase di sviluppo/testing
- Configurazione completa tramite variabili d'ambiente
- Min/max chunk size configurabili
- Embedding model configurabile (OpenAI/alternative)
- **Schema Normalization**: Evitare FK ridondanti - i dati si recuperano tramite le relazioni (Video → Transcript → Chunk)

## Research Findings

### Best Practices
- **YouTube API Quota Management**: Search costa 100 unità, captions 200-300. Con 10k quota giornaliera = ~30-50 video/giorno
- **RFC 3339 Timestamps**: Formato richiesto da YouTube API per `publishedAfter` (es: `2024-12-13T00:00:00Z`)
- **Docling Hybrid Chunking**: Combina struttura gerarchica + token limits per chunk semanticamente coerenti
- **pgvector**: Ottimizzato per similarity search su Supabase; supporta indici HNSW per performance
- **Batch Embedding**: Riduce latenza/costo aggregando chunk prima di chiamare OpenAI API
- **Transcript Timestamps**: YouTube fornisce `start` (secondi) e `duration` per ogni caption segment

### Reference Implementations
- [PRPs/examples/backend_agent_api/tools.py](PRPs/examples/backend_agent_api/tools.py) - Pattern per RAG retrieval e embedding
- [PRPs/examples/backend_agent_api/clients.py](PRPs/examples/backend_agent_api/clients.py) - Setup Supabase e OpenAI clients
- [PRPs/examples/docling_hybrid_chunking.py](PRPs/examples/docling_hybrid_chunking.py) - HybridChunker con tokenizer
- [PRPs/examples/youtube_transcript_api.md](PRPs/examples/youtube_transcript_api.md) - Specifiche YouTube API search

### Technology Decisions
- **YouTube API**: Google YouTube Data API v3 + Captions API (ufficiale, supporto timestamp nativo)
- **Chunking**: Docling HybridChunker (preserva semantica, rispetta token limits)
- **Database**: Supabase PostgreSQL con pgvector extension (già in uso nel progetto)
- **Embedding**: OpenAI text-embedding-3-small (default), configurabile via env
- **Type Safety**: Pydantic models per validazione (pattern esistente nel codebase)
- **Logging**: Structured logging con correlation IDs (vedi logging_guide.md)

## Implementation Tasks

### Phase 1: Foundation & Setup
1. **Definire Pydantic Schemas**
   - Description: Creare modelli per Video, Transcript, Chunk, metadata
   - Files to create: `src/rag_pipeline/schemas.py`
   - Dependencies: None
   - Estimated effort: 1h
   - Details:
     ```python
     class Video(BaseModel):
         video_id: str
         channel_id: str
         title: str
         published_at: datetime
         url: str
     
     class TranscriptSegment(BaseModel):
         text: str
         start: float
         duration: float
     
     class Chunk(BaseModel):
         chunk_text: str
         chunk_index: int
         start_time: str  # HH:MM:SS
         end_time: str    # HH:MM:SS
         video_id: str
         channel_id: str
         video_url: str
     ```

2. **Setup Variabili d'Ambiente**
   - Description: Definire tutte le env vars necessarie in .env.example
   - Files to create: `src/rag_pipeline/.env.example`
   - Dependencies: None
   - Estimated effort: 30min
   - Details:
     ```
     YOUTUBE_API_KEY=your_youtube_api_key
     YOUTUBE_CHANNEL_ID=UC...
     EMBEDDING_MODEL_CHOICE=text-embedding-3-small
     EMBEDDING_BASE_URL=https://api.openai.com/v1
     EMBEDDING_API_KEY=your_openai_key
     SUPABASE_URL=https://xxx.supabase.co
     SUPABASE_SERVICE_KEY=your_service_key
     MIN_CHUNK_SIZE=256
     MAX_CHUNK_SIZE=512
     MAX_CHUNK_TOKENS=512
     ```

3. **Configurare DB Schema**
   - Description: Definire tabelle videos, transcripts, chunks in Supabase
   - Files to create: `PRPs/examples/rag_pipeline_tables.sql`
   - Dependencies: Consultare schema_example/RAG_AI_Agent.png
   - Estimated effort: 1h
   - Details:
     ```sql
     CREATE TABLE videos (
       id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
       video_id TEXT UNIQUE NOT NULL,
       channel_id TEXT NOT NULL,
       title TEXT,
       published_at TIMESTAMPTZ,
       url TEXT,
       processed_at      DEFAULT NOW()
     );
     
     CREATE TABLE transcripts (
       id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
       video_id TEXT REFERENCES videos(video_id),
       full_transcript TEXT,
       language TEXT,
       created_at TIMESTAMPTZ DEFAULT NOW()
     );
     
     CREATE TABLE chunks (
       id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
       transcript_id UUID REFERENCES transcripts(id),
       chunk_text TEXT NOT NULL,
       chunk_index INT,
       start_time TEXT,
       end_time TEXT,
       tokens INT,
       embedding vector(1536),  -- pgvector
       created_at TIMESTAMPTZ DEFAULT NOW()
     ); 
     
     CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);
     ```  

### Phase 2: Core Components

4. **YouTube Search Service**
   - Description: Implementare ricerca video tramite YouTube Data API v3
   - Files to create: `src/rag_pipeline/youtube_service.py`
   - Dependencies: Task 1 (schemas), Task 2 (env vars)
   - Estimated effort: 2h
   - Details:
     - Usare `requests` o `httpx` per chiamate API
     - Parametri: `part=snippet,id`, `channelId`, `type=video`, `order=date`, `publishedAfter` (RFC3339)
     - Calcolare `publishedAfter` come 7 giorni fa da datetime.now()
     - Parsing response: estrarre `videoId`, `title`, `publishedAt`
     - Return: List[Video]
     - Error handling: HTTPException se quota esaurita o errori API

5. **Transcript Downloader Service**
   - Description: Scaricare trascrizioni via YouTube Captions API con timestamp
   - Files to create: Estendere `src/rag_pipeline/youtube_service.py`
   - Dependencies: Task 4
   - Estimated effort: 3h
   - Details:
     - Usare YouTube Data API v3 `captions.list` + `captions.download`
     - Filtrare lingue: solo 'it' e 'en'
     - Fallback: se non disponibile ufficiale → auto-generated
     - Retry logic: 1 tentativo extra con exponential backoff
     - Parse formato SRT/VTT → List[TranscriptSegment]
     - Convertire timestamp secondi → HH:MM:SS
     - Return: (full_transcript: str, segments: List[TranscriptSegment], language: str)
     - Se entrambi i tentativi falliscono: raise TranscriptNotAvailableError

6. **Docling Chunking Service**
   - Description: Chunking ibrido con preservazione timestamp
   - Files to create: `src/rag_pipeline/chunking_service.py`
   - Dependencies: Task 1, riferimento a docling_hybrid_chunking.py
   - Estimated effort: 4h
   - Details:
     - Input in memoria: wrappare transcript in stream, assegnare nome manuale
     - Usare HybridChunker con tokenizer (sentence-transformers/all-MiniLM-L6-v2)
     - Parametri: `max_tokens=MAX_CHUNK_TOKENS` (da env), `merge_peers=True`
     - Per ogni chunk: calcolare `start_time` e `end_time` dai segment originali
     - Algoritmo timestamp:
       ```
       - Chunk contiene testo da posizione char X a Y
       - Mappare posizioni char → segment originali
       - start_time = primo segment.start
       - end_time = ultimo segment.start + segment.duration
       ```
     - Return: List[Chunk] con tutti metadata

7. **Embedding Service**
   - Description: Generare embeddings via OpenAI API
   - Files to create: `src/rag_pipeline/embedding_service.py`
   - Dependencies: Task 1, riferimento a tools.py
   - Estimated effort: 2h
   - Details:
     - Usare AsyncOpenAI client (vedi clients.py pattern)
     - Batch processing: aggregare fino a 100 chunk prima di chiamare API
     - Model configurabile via `EMBEDDING_MODEL_CHOICE`
     - Error handling: retry su rate limit (exponential backoff)
     - Return: List[List[float]] (embedding vectors)

8. **Database Service**
   - Description: Interazione con Supabase per CRUD operations
   - Files to create: `src/rag_pipeline/db_service.py`
   - Dependencies: Task 3 (schema DB), riferimento a db_utils.py
   - Estimated effort: 2h
   - Details:
     - check_video_exists(video_id) → bool
     - insert_video(video: Video) → UUID
     - insert_transcript(video_id, transcript, language) → UUID
     - batch_insert_chunks(chunks: List[Chunk], embeddings: List[List[float]]) → None
     - Usare Supabase client (vedi clients.py)
     - Deduplicazione: SELECT WHERE video_id = ? prima di insert

### Phase 3: Pipeline Orchestration

9. **Pipeline Orchestrator**
   - Description: Coordinare l'intero flusso end-to-end
   - Files to create: `src/rag_pipeline/pipeline.py`
   - Dependencies: Tasks 4-8
   - Estimated effort: 3h
   - Details:
     ```python
     async def run_pipeline():
         # 1. Search videos
         videos = await youtube_service.search_videos(channel_id, days=7)
         
         # 2. Filter already processed
         new_videos = [v for v in videos if not db_service.check_video_exists(v.video_id)]
         
         # 3. For each new video:
         for video in new_videos:
             try:
                 # 3a. Download transcript (with retry)
                 transcript, segments, lang = await youtube_service.get_transcript(video.video_id)
                 
                 # 3b. Chunk transcript
                 chunks = chunking_service.chunk_transcript(transcript, segments, video)
                 
                 # 3c. Generate embeddings (batch)
                 embeddings = await embedding_service.embed_chunks([c.chunk_text for c in chunks])
                 
                 # 3d. Store in DB
                 video_uuid = db_service.insert_video(video)
                 transcript_uuid = db_service.insert_transcript(video.video_id, transcript, lang)
                 db_service.batch_insert_chunks(chunks, embeddings)
                 
                 logger.info(f"Successfully processed video {video.video_id}")
             except TranscriptNotAvailableError:
                 logger.error(f"Failed to get transcript for {video.video_id}")
                 continue
     ```

10. **CLI Entry Point**
    - Description: Script CLI per trigger manuale
    - Files to create: `src/rag_pipeline/main.py`
    - Dependencies: Task 9
    - Estimated effort: 1h
    - Details:
      ```python
      import asyncio
      from pipeline import run_pipeline
      
      if __name__ == "__main__":
          asyncio.run(run_pipeline())
      ```
    - Comando esecuzione: `python -m src.rag_pipeline.main`

### Phase 4: Testing & Validation

11. **Unit Tests per Services**
    - Description: Test individuali per ogni service
    - Files to create: `tests/rag_pipeline/test_*.py`
    - Dependencies: Tasks 4-8, riferimento a testing_guide.md
    - Estimated effort: 4h
    - Details:
      - test_youtube_service.py: mock API responses
      - test_chunking_service.py: verificare preservazione timestamp
      - test_embedding_service.py: mock OpenAI API
      - test_db_service.py: usare Supabase test DB o mock
      - Usare pytest + pytest-asyncio

12. **Integration Test Pipeline**
    - Description: Test end-to-end con dati mock
    - Files to create: `tests/rag_pipeline/test_pipeline_integration.py`
    - Dependencies: Task 9
    - Estimated effort: 2h
    - Details:
      - Mock YouTube API per restituire 2-3 video fake
      - Mock transcript response
      - Verificare: video inserito in DB, chunk creati, embeddings generati
      - Verificare deduplicazione (run 2x, solo 1 insert)

13. **Validation Script**
    - Description: Script manuale per validare output
    - Files to create: `scripts/validate_pipeline.py`
    - Dependencies: Task 9
    - Estimated effort: 1h
    - Details:
      - Query DB per contare video/transcripts/chunks
      - Verificare presenza embeddings (vector non NULL)
      - Stampare sample chunk con metadata
      - Test similarity search su chunk inseriti

## Codebase Integration Points

### Files to Modify
- `src/rag_pipeline/__init__.py` - Esporre servizi principali
- `.env.example` (root) - Aggiungere variabili YouTube/pipeline

### New Files to Create
- `src/rag_pipeline/schemas.py` - Pydantic models
- `src/rag_pipeline/youtube_service.py` - YouTube API interaction
- `src/rag_pipeline/chunking_service.py` - Docling chunking
- `src/rag_pipeline/embedding_service.py` - OpenAI embeddings
- `src/rag_pipeline/db_service.py` - Supabase operations
- `src/rag_pipeline/pipeline.py` - Orchestrator
- `src/rag_pipeline/main.py` - CLI entry point
- `PRPs/examples/rag_pipeline_tables.sql` - DB schema
- `tests/rag_pipeline/test_*.py` - Test suite

### Existing Patterns to Follow
- Dependency injection via dataclass (vedi AgentDeps in agent.py)
- Env loading pattern: check `ENVIRONMENT` variabile (agent.py L14-26)
- Async/await per I/O operations (tools.py pattern)
- Google-style docstrings con Args/Returns/Raises (db_utils.py)
- Structured logging con correlation_id (vedi logging_guide.md)
- Pydantic BaseModel per validazione (vedi schemas nel progetto)

## Technical Design

### Architecture Diagram
```
┌─────────────────────────────────────────────────────────┐
│                     CLI Trigger                          │
│                  (main.py manual run)                    │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              Pipeline Orchestrator                       │
│         (Coordina tutti i service)                       │
└──┬──────┬────────┬────────┬──────────┬─────────────────┘
   │      │        │        │          │
   ▼      ▼        ▼        ▼          ▼
┌──────┐┌──────┐┌──────┐┌──────┐  ┌──────────┐
│YouTube││Trans-││Chunk-││Embed-│  │    DB    │
│Search ││cript ││ing   ││ding  │  │ Service  │
│Service││Svc   ││Svc   ││Svc   │  │(Supabase)│
└───┬───┘└──┬───┘└──┬───┘└──┬───┘  └────┬─────┘
    │       │       │       │           │
    ▼       ▼       ▼       ▼           ▼
┌────────────────────────────────────────────┐
│         External Dependencies               │
│  • YouTube Data API v3                     │
│  • YouTube Captions API                    │
│  • OpenAI Embeddings API                   │
│  • Supabase PostgreSQL + pgvector          │
│  • Docling HybridChunker                   │
└────────────────────────────────────────────┘
```

### Data Flow
1. **Input**: `YOUTUBE_CHANNEL_ID` da env, `publishedAfter` calcolato (7 giorni fa)
2. **Search**: YouTube API restituisce List[videoId] + metadata
3. **Dedup Check**: Query DB per filtrare video già processati
4. **Transcript Download**: Per ogni nuovo video → fetch captions (ITA/EN, con fallback auto-gen)
5. **Chunking**: Transcript → Docling HybridChunker → List[Chunk] con timestamp mappati
6. **Embedding**: Batch chunk texts → OpenAI API → List[vector(1536)]
7. **Storage**: Insert video → insert transcript → batch insert chunks+embeddings
8. **Output**: Log success/failure, DB popolato per RAG retrieval

### API Endpoints (N/A - CLI tool)
Nessun endpoint HTTP; la pipeline è un script standalone CLI.

## Dependencies and Libraries

### Nuove Dipendenze
- `google-api-python-client` - YouTube Data API client ufficiale
- `docling` - Hybrid chunking (già presente: `docling==2.x`)
- `transformers` - Tokenizer per Docling (già presente)
- Già presenti:
  - `pydantic` - Validation
  - `httpx` - HTTP client async
  - `openai` - Embeddings
  - `supabase` - DB client
  - `python-dotenv` - Env vars

### Requirements Update
Aggiungere a `requirements.txt`:
```
google-api-python-client>=2.100.0
google-auth-httplib2>=0.1.0
google-auth-oauthlib>=1.0.0
```

## Testing Strategy

### Unit Tests
- `test_youtube_service.py`: Mock YouTube API responses, verificare parsing corretto
- `test_chunking_service.py`: Testare preservazione timestamp, rispetto min/max size
- `test_embedding_service.py`: Mock OpenAI, verificare batch processing
- `test_db_service.py`: Mock Supabase o usare test DB, verificare deduplicazione

### Integration Tests
- `test_pipeline_integration.py`: Flusso completo con dati mock, verificare DB finale
- Test retry logic: simulare fallimento transcript → verificare 1 retry → error

### Edge Cases
- Video senza trascrizioni disponibili (né ufficiali né auto-gen)
- Transcript in lingua non supportata (né IT né EN)
- Video già processato (deduplicazione)
- Chunk con timestamp non mappabili (gestire gracefully)
- Quota API esaurita (error chiaro, non crash)
- Embedding API rate limit (retry con backoff)

### Validation Manual
- Script `validate_pipeline.py` per query DB e verificare:
  - Conteggio video/transcripts/chunks
  - Sample chunk con metadata completi
  - Test similarity search funzionante

## Success Criteria
- [ ] Pipeline esegue search YouTube e restituisce solo video <7 giorni
- [ ] Trascrizioni scaricate con timestamp preservati (start/end per ogni chunk)
- [ ] Deduplicazione funzionante: video già processati sono saltati
- [ ] Chunk rispettano min/max size da env
- [ ] Embeddings generati e salvati correttamente in pgvector
- [ ] Metadata completi: video_url, channel_id, start_time, end_time, chunk_index
- [ ] Retry logic: 1 tentativo extra su fallimento, poi errore chiaro
- [ ] Solo lingue IT/EN processate
- [ ] Fallback auto-generated funzionante
- [ ] Logging strutturato con correlation ID
- [ ] Unit tests passano (coverage >80%)
- [ ] Integration test end-to-end passa
- [ ] Nessun rate limiting necessario (10k quota sufficiente)
- [ ] Trigger manuale CLI funzionante

## Notes and Considerations

### Potenziali Sfide
- **Timestamp Mapping**: Docling non è nativamente designed per testo con timestamp. Soluzione: mantenere mapping char_position → segment per calcolare start/end dopo chunking
- **Auto-Generated Quality**: Trascrizioni auto-gen possono avere errori. Considerare flag `is_auto_generated` in DB per filtraggio futuro
- **Lingua Detection**: YouTube potrebbe restituire lang code diverso da 'it'/'en' (es: 'it-IT'). Usare `.startswith('it')` o `.startswith('en')`
- **Chunk Overlap**: Valutare se introdurre overlap tra chunk per contesto (non nel MVP, considerare post-launch)

### Future Enhancements
- [ ] Supporto multi-canale (array di channel IDs)
- [ ] Webhook trigger via FastAPI endpoint
- [ ] Cronjob scheduling automatico
- [ ] Dashboard per monitoring (video processati, errori, quota usage)
- [ ] Support lingue aggiuntive
- [ ] Re-processing periodico di video vecchi (se transcript aggiornata)
- [ ] Metadata aggiuntivi: view count, like count, descrizione video
- [ ] Filtri avanzati: keyword filtering, duration filtering

### Riferimenti Importanti
- [CLAUDE.md](../CLAUDE.md) - Core principles, type safety, KISS/YAGNI
- [PRPs/ai_docs/tool_guide.md](../PRPs/ai_docs/tool_guide.md) - Pattern tool implementation
- [PRPs/ai_docs/logging_guide.md](../PRPs/ai_docs/logging_guide.md) - Structured logging
- [PRPs/ai_docs/testing_guide.md](../PRPs/ai_docs/testing_guide.md) - Testing conventions
- [schema_example/RAG_AI_Agent.png](../schema_example/RAG_AI_Agent.png) - DB schema reference
- [.github/copilot-instructions.md](../.github/copilot-instructions.md) - AI agent guidelines

---
*Questo piano è pronto per l'esecuzione seguendo il PIV LOOP: Planning → Implementation → Validation → Iteration*
