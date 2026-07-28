import asyncio
import time

import httpx

from bot.config import config

_client = httpx.AsyncClient(base_url=config.suno_api_base_url, timeout=30.0)


async def generate_song(prompt: str) -> list[str]:
    response = await _client.post(
        "/api/generate",
        json={"prompt": prompt, "make_instrumental": False, "wait_audio": False},
    )
    response.raise_for_status()
    clips = response.json()
    return [clip["id"] for clip in clips]


async def wait_for_clips(
    ids: list[str], timeout: float = 240.0, interval: float = 8.0
) -> list[dict]:
    if not ids:
        raise ValueError("wait_for_clips called with no clip ids")
    deadline = time.monotonic() + timeout
    while True:
        response = await _client.get("/api/get", params={"ids": ",".join(ids)})
        response.raise_for_status()
        clips = response.json()
        if all(clip.get("audio_url") for clip in clips):
            return clips
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Suno clips not ready after {timeout}s: ids={ids}")
        await asyncio.sleep(interval)
