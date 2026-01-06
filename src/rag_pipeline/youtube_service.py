import os
from datetime import datetime, timedelta, timezone
from typing import Optional
import httpx
from pydantic import BaseModel, ValidationError

from src.rag_pipeline.schemas import Video, Transcript


class TranscriptSegment(BaseModel):
    """Segmento della trascrizione in cui essa è divisa, con informazioni timing"""
    text: str
    start: float
    duration: float

class YoutubeService:
    """Servizio per utilizzare l'API di YouTube v3"""

    def __init__(self, api_key: str, ID_channel: str) -> None:
        """Inizializzazione del Servizio di Youtube.
        
        Args:
            api_key (str): Chiave API di YouTube
            ID_channel : ID del canale target (deve iniziare con 'UC'ed essere lungo 24 chars, validazione seguente)
            
        Raises:
            ValueError: se l'ID del canale non è valido.
            """
        
        self.api_key = api_key
        self.ID_channel = ID_channel

        #Validazione del formato dell'ID del canale

        if not ID_channel.startswith("UC") or len(ID_channel) != 24:
            raise ValueError(
                f"Invalid ID_channel: {ID_channel}. It must start with 'UC' and be 24 chars long"
            )
        if int(os.getenv("YOUTUBE_LOOKBACK_DAYS", "7")) < 1:
            raise ValueError(
                "Lookback days must be greater than 0"
                )
        
        self.base_url = "https://www.googleapis.com/youtube/v3"
        
        async def search_videos(self) -> list[Video]:
            """
            Cerca video nel canale configurato pubblicati negli ultimi X giorni.
        
            I video vengono restituiti in ordine di data di pubblicazione, dal più recente al meno recente

            Returns: 
                Lista di oggetti Video che contengono i metadata del video
            """
            published_after = (
                datetime.now(timezone.utc) - timedelta(days = int(os.getenv("YOUTUBE_LOOKBACK_DAYS", "7")))
            ).isoformat().replace("+00:00", "Z")

            params = {
                "part": "snippet_id",
                "channelId": self.ID_channel,
                "order": "date",
                "type": "video",
                "eventType": "completed",
                "publishedAfter": published_after,
                "maxResults": 50,
                "key": self.api_key,
            }

