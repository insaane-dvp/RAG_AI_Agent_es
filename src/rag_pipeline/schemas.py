# Data validation in Python grazie a Pydantic
from datetime import datetime, timezone
from pydantic import BaseModel, Field, validator


class Video(BaseModel):
    """Validazione dei metadata relativi ai video YouTube processati dall'agente AI."""

    IDvideo: str = Field(..., description = "ID video")
    name : str = Field(..., description = "Nome del video")  # Nome associato dall'agente AI
    summary : str = Field(default = "", description = "Riassunto del video fatto dall'agente dopo la trascrizione")
    IDChannel: str = Field(..., description = "ID canale Youtube") # Per ora tutto uguale essendo l'agente su un solo canale
    publishedAt: datetime = Field(..., description = "Data di pubblicazione del video")
    url: str = Field(default = "", description = "URL del video")
    duration: int = Field(default = 0, description = "Durata del video in secondi")
    processedAt: datetime = Field(default_factory = lambda: datetime.now(timezone.utc), description = "Data di processamento del video")

    class Config:
        """Configurazione del modello pydantic."""

        json_encoders = {
            datetime: lambda value: value.isoformat()
        }

        validate_assignment = True
        @validator("IDvideo")
        def IDvideo_validation(cls, value) -> str: #passo cls(classe "modello" dove si trova la funzione) e il valore
            """Controllo che l'ID non sia vuoto e un valore valido"""
            value = value.strip()
            if not value:
                raise ValueError("ID video vuoto")
            if len(value) != 11:
                raise ValueError("ID del video non valido")
            return value
        
        @validator("name")
        def name_validation(cls, value) -> str:
            """Controllo che il nome non sia vuoto"""
            value = value.strip()
            if not value :
                raise ValueError("Nome del video vuoto")
            if len(value) > 100:
                raise ValueError("Nome del video troppo lungo")
            return value
        
        @validator("summary", pre = True, always = True)
        def summary_validation(cls, value) -> str:
            """Controllo del riasunto se è vuoto o troppo lungo"""
            value = "" if value is None else str(value).strip()
            if not value:
                raise ValueError("Riassunto vuoto")
            if len(value) > 500:
                raise ValueError("Riassunto troppo lungo")
            return value
        
        @validator("IDChannel")
        def IDChannel_validation(cls, value) -> str:
            """Controllo che l'ID del canale non sia vuoto"""
            value = value.strip()
            if not value: 
                raise ValueError("ID del canale vuoto")
            if len(value) != 24 or not value.startswith("UC"):
                raise ValueError("ID del canale non valido")
            return value
            
        @validator("url", always = True)
        # values dichiarato come dict indica un dizionario, cioè l'insieme del valori validati fino a quel momento
        def url_validator(cls, value : str, values : dict ) -> str:
            """Controllo che l'URL non sia vuoto, e in caso lo fosse, genero io l'URL"""
            if value:
                return value.strip()
            if 'IDVideo' not in values:
                raise ValueError("ID del video non trovato")
            return f"https://www.youtube.com/watch?v={values['IDVideo']}"
        
        @validator("duration")
        def duration_validator(cls, value : int) -> int:
            """Controllo che la durata sia un numero positivo"""
            if value <= 0:
                raise ValueError("Durata non valida")
            return value

        @validator("publishedAt")
        def publishedAt_validator(cls, value : datetime) -> datetime: 
            """Controllo che la data di pubblicazione sia valida"""
            if value > datetime.now(timezone.utc):
                raise ValueError("Data di pubblicazione impossibile")
            return value
        
        @validator("processedAt")
        def processedAt_validator(cls, value : datetime, values : dict) -> datetime: 
            """Controllo che la data di processo del video sia valida"""
            if value > datetime.now(timezone.utc):
                raise ValueError("Data di pubblicazione impossibile")
            if 'publishedAt' not in values: 
                raise ValueError("Data di pubblicazione non trovata, impossibile aver processato")
            if value < values['publishedAt']: 
                raise ValueError("Data di pubblicazione non valida")
            return value


class Transcript(BaseModel):
    """Validazione della trascrizione YouTube estratta da un video con metadati e timeline."""

    IDtranscript: str = Field(..., description="ID univoco della trascrizione")
    IDvideo: str = Field(..., description="ID del video YouTube associato (FK)")
    language: str = Field(..., description="Lingua della trascrizione (ITA o EN)")
    is_auto_generated: bool = Field(default=False, description="True se trascrizione auto-generata da YouTube")
    text: str = Field(..., description="Testo completo della trascrizione")
    transcript_raw: dict = Field(default_factory=dict, description="Raw transcript data con timing da YouTube API")
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Data di creazione della trascrizione")
    processedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Data di processamento della trascrizione")

    class Config:
        """Configurazione del modello Pydantic."""
        json_encoders = {
            datetime: lambda value: value.isoformat()
        }
        validate_assignment = True

        @validator("IDtranscript")
        def IDtranscript_validation(cls, value: str) -> str:
            """ID trascrizione non deve essere vuoto."""
            value = value.strip()
            if not value:
                raise ValueError("ID della trascrizione vuoto")
            return value

        @validator("IDvideo")
        def IDvideo_validation(cls, value: str) -> str:
            """ID video deve essere valido (11 caratteri)."""
            value = value.strip()
            if not value:
                raise ValueError("ID video vuoto")
            if len(value) != 11:
                raise ValueError("ID del video non valido")
            return value

        @validator("language")
        def language_validation(cls, value: str) -> str:
            """Lingua supportata: ITA o EN."""
            value = value.upper().strip()
            if value not in ["ITA", "EN"]:
                raise ValueError("Lingua non supportata. Ammesse: ITA, EN")
            return value

        @validator("text")
        def content_validation(cls, value: str) -> str:
            """Content non deve essere vuoto."""
            value = str(value).strip()
            if not value:
                raise ValueError("Contenuto della trascrizione vuoto")
            return value

        @validator("processedAt")
        def processedAt_validator(cls, value: datetime, values: dict) -> datetime:
            """Data processamento deve essere valida."""
            if value > datetime.now(timezone.utc):
                raise ValueError("Data di processamento nel futuro")
            return value


class Chunk(BaseModel):
    """Validazione dei chunk estratti da una trascrizione per embedding e RAG retrieval.
    
    Note: IDvideo, IDChannel e url sono recuperabili tramite FK IDtranscript → Transcript → Video
    """

    IDchunk: str = Field(..., description="ID univoco del chunk")
    IDtranscript: str = Field(..., description="ID della trascrizione associata (FK)")
    chunk_index: int = Field(..., description="Indice ordinale del chunk nella trascrizione (0-based)")
    content: str = Field(..., description="Contenuto testuale del chunk")
    start_time: int = Field(default=0, description="Timestamp inizio in secondi")
    end_time: int = Field(default=0, description="Timestamp fine in secondi")
    tokens_count: int = Field(default=0, description="Conteggio token nel chunk")
    language: str = Field(default="EN", description="Lingua del chunk (ITA o EN)")
    metadata: dict = Field(default_factory=dict, description="Metadati aggiuntivi (source, format, ecc)")
    embedding: list | None = Field(default=None, description="Vettore embedding (1536 dim OpenAI, nullable)")
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Data creazione chunk")

    class Config:
        """Configurazione del modello Pydantic."""
        json_encoders = {
            datetime: lambda value: value.isoformat()
        }
        validate_assignment = True

        @validator("IDchunk")
        def IDchunk_validation(cls, value: str) -> str:
            """ID chunk non deve essere vuoto."""
            value = value.strip()
            if not value:
                raise ValueError("ID del chunk vuoto")
            return value

        @validator("IDtranscript")
        def IDtranscript_validation(cls, value: str) -> str:
            """ID trascrizione non deve essere vuoto."""
            value = value.strip()
            if not value:
                raise ValueError("ID della trascrizione vuoto")
            return value

        @validator("chunk_index")
        def chunk_index_validation(cls, value: int) -> int:
            """Indice chunk non può essere negativo."""
            if value < 0:
                raise ValueError("Indice del chunk negativo")
            return value

        @validator("content")
        def content_validation(cls, value: str) -> str:
            """Content non deve essere vuoto."""
            value = str(value).strip()
            if not value:
                raise ValueError("Contenuto del chunk vuoto")
            return value

        @validator("start_time")
        def start_time_validation(cls, value: int) -> int:
            """Tempo inizio non può essere negativo."""
            if value < 0:
                raise ValueError("Tempo di inizio negativo")
            return value

        @validator("end_time")
        def end_time_validation(cls, value: int, values: dict) -> int:
            """Tempo fine deve essere >= start_time e non negativo."""
            if value < 0:
                raise ValueError("Tempo di fine negativo")
            if 'start_time' in values and value < values['start_time']:
                raise ValueError("Tempo di fine minore del tempo di inizio")
            return value

        @validator("tokens_count")
        def tokens_count_validation(cls, value: int) -> int:
            """Conteggio token non può essere negativo."""
            if value < 0:
                raise ValueError("Conteggio dei token negativo")
            return value

        @validator("language")
        def language_validation(cls, value: str) -> str:
            """Lingua supportata: ITA o EN."""
            value = value.upper().strip()
            if value not in ["ITA", "EN"]:
                raise ValueError("Lingua non supportata. Ammesse: ITA, EN")
            return value

        @validator("embedding")
        def embedding_validation(cls, value: list | None) -> list | None:
            """Embedding deve avere 1536 dimensioni (OpenAI) se presente."""
            if value is not None:
                if not isinstance(value, list):
                    raise ValueError("Embedding deve essere una lista")
                if len(value) != 1536:
                    raise ValueError(f"Embedding deve avere 1536 dimensioni, ricevute {len(value)}")
                if not all(isinstance(x, (int, float)) for x in value):
                    raise ValueError("Embedding deve contenere solo numeri")
            return value





