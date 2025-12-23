# Copilot Instructions

## Prompt di riferimento (mantieni integro)
> STEP DA SEGUIRE PER OGNI TASK DA VOLER IMPLEMENTARE\n> PIV LOOP\n> PLANNING: farsi un “vibe plan” mentale\n> Per farlo, informarsi online se esiste già qualcosa di simile a cui ispirarsi\n> Studiare in modo dettagliato un piano per l’agente AI, basato sulla mia conversazione. Per farlo: \n> GOALS, SUCCESS CRITERIAS, DOCUMENTATION REFERENCE, TASK LIST (archon),\n> VALIDATION STRATEGY e CODEBASE STRUCTURE\n> \n> IMPLEMENTAZIONE: scrivere il codice per implementare la task\n> \n> VALIDAZIONE: validare il funzionamento della task\n> \n> ITERAZIONE: se la task non funziona (bug) o funziona, in ogni caso ripartire dall’inizio.\n> \n> PIV #1 (RAG PIPELINE)... (testo completo già nel prompt utente)

## Architettura e riferimenti chiave
- Backend Pydantic AI agent + FastAPI: vedi [PRPs/examples/backend_agent_api/agent.py](PRPs/examples/backend_agent_api/agent.py) e [PRPs/examples/backend_agent_api/agent_api.py](PRPs/examples/backend_agent_api/agent_api.py)
- Strumenti RAG, web search, SQL, code exec: [PRPs/examples/backend_agent_api/tools.py](PRPs/examples/backend_agent_api/tools.py)
- Prompt e istruzioni tool: [PRPs/examples/backend_agent_api/prompt.py](PRPs/examples/backend_agent_api/prompt.py)
- Linee guida interne: [CLAUDE.md](CLAUDE.md) + [PRPs/ai_docs/tool_guide.md](PRPs/ai_docs/tool_guide.md), [logging_guide.md](PRPs/ai_docs/logging_guide.md), [testing_guide.md](PRPs/ai_docs/testing_guide.md)
- Schema tabelle DB: consulta [schema_example/RAG_AI_Agent.png](schema_example/RAG_AI_Agent.png)

## Convenzioni essenziali
- Type annotations obbligatorie, docstring Google-style, niente `Any` senza motivazione (vedi CLAUDE.md)
- Env-first: `ENVIRONMENT` decide se caricare .env locale o solo env cloud (pattern in agent.py)
- Manual trigger finché in sviluppo; niente cron/webhook ora
- Pipeline da seguire: opzione 1 (modulare) o 2 (lineare) del planning; non introdurre altre varianti senza consenso
- Ruolo: l’AI è code-assistant, non sostituto; proporre, spiegare e chiedere conferma prima di decisioni impattanti

## RAG Pipeline YouTube (vincoli dal prompt)
- Canale unico via env `YOUTUBE_CHANNEL_ID`; filtra solo video nuovi (<7 giorni) con `publishedAfter` RFC3339
- YouTube Data API search: parametri da [PRPs/examples/youtube_transcript_api.md](PRPs/examples/youtube_transcript_api.md); ordina per `date`, `type=video`, `part=snippet,id`
- Transcript: usa API ufficiale; fallback consentito a auto-generated; lingue ammesse: ITA, EN
- Retry: 1 solo tentativo extra se transcript fallisce; poi errore
- Dedup: controlla DB prima di processare `videoId` già presenti
- Metadata per chunk: URL video, channelId, `start_time`, `end_time`, chunk index

## Chunking con Docling (hybrid)
- Per input file: usa automazione Docling standard (vedi [PRPs/examples/docling_hybrid_chunking.py](PRPs/examples/docling_hybrid_chunking.py))
- Per input in memoria/grezzi: esplicita formato, incapsula in stream, assegna nome/metadati manuali
- Rispetta min/max chunk size e max tokens da env; preserva timestamps nei chunk

## Storage e embedding
- Supabase come DB + pgvector per embeddings; mantieni struttura videos → transcripts → chunks (con vettori)
- Batch embedding quando possibile per costo/latency; ma non introdurre rate limiting/throttling (quota 10k sufficiente)
- Embedding configurabile via env: imposta `EMBEDDING_MODEL_CHOICE` e `EMBEDDING_BASE_URL` (vedi [PRPs/ai_docs/examples/backend_agent/.env.example](PRPs/ai_docs/examples/backend_agent/.env.example))

## Debug & validazione
- Log strutturati e correlation id (vedi logging_guide.md)
- Validazione step-by-step: search → transcript → chunking → embedding → upsert DB
- In caso di errore transcript o embedding: segnala chiaramente e ferma pipeline (no loop infinito)
