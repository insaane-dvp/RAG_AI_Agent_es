"""
Quick sanity check for YouTube Data API v3 key wiring.
Loads env from .env (development) and performs a search on the target channel.
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone
import os
import sys

try:
    import requests  # type: ignore
    from dotenv import load_dotenv  # type: ignore
except Exception:
    print("Missing dependencies. Install with: pip install requests python-dotenv", file=sys.stderr)
    raise

# Load .env from the rag_pipeline folder in development mode
env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    load_dotenv(env_path, override=True)

API_KEY = os.getenv("YOUTUBE_API_KEY")
CHANNEL_ID = os.getenv("YOUTUBE_CHANNEL_ID")
LOOKBACK_DAYS = int(os.getenv("YOUTUBE_LOOKBACK_DAYS", "7"))

if not API_KEY:
    print("YOUTUBE_API_KEY is not set. Add it to src/rag_pipeline/.env or set it in the environment.", file=sys.stderr)
    sys.exit(1)

if not CHANNEL_ID:
    print("YOUTUBE_CHANNEL_ID is not set. Add it to src/rag_pipeline/.env or set it in the environment.", file=sys.stderr)
    sys.exit(1)

published_after = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).isoformat().replace("+00:00", "Z")

params = {
    "key": API_KEY,
    "channelId": CHANNEL_ID,
    "part": "snippet,id",
    "order": "date",
    "type": "video",
    "publishedAfter": published_after,
    "maxResults": 10,
}

resp = requests.get("https://www.googleapis.com/youtube/v3/search", params=params, timeout=30)
resp.raise_for_status()
data = resp.json()

items = data.get("items", [])
print(f"OK: returned {len(items)} videos since {published_after}")
for i, item in enumerate(items[:5]):
    vid = item.get("id", {}).get("videoId")
    title = item.get("snippet", {}).get("title")
    published_at = item.get("snippet", {}).get("publishedAt")
    print(f"[{i}] {title} (videoId={vid}) publishedAt={published_at}")
