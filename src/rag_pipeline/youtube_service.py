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

    def __init__(self, api_key: str, ID_channel: str):
        """Inizializzazione del Servizio di Youtube.
        
        Args:
            api_key (str): Chiave API di YouTube
            ID_channel : ID del canale target (deve iniziare con 'UC'ed essere lungo 24 chars, validazione seguente)
            
        Raises:
            ValueError: se l'ID del canale non è valido.
            """
        
        self.api_key = api_key
        self.ID_channel = ID_channel
        self.base_url = "https://www.googleapis.com/youtube/v3"

        #Validazione del formato dell'ID del canale

        if not ID_channel.startswith("UC") or len(ID_channel) != 24:
            raise ValueError(
                f"Invalid ID_channel: {ID_channel}. It must start with 'UC' and be 24 chars long"
            )