from unittest.mock import AsyncMock

import pytest

import bot.services.suno_client as suno_client


class _FakeResponse:
    def __init__(self, json_data):
        self._json_data = json_data

    def raise_for_status(self):
        pass

    def json(self):
        return self._json_data


async def test_generate_song_returns_clip_ids(monkeypatch):
    post = AsyncMock(return_value=_FakeResponse([{"id": "clip-1"}, {"id": "clip-2"}]))
    monkeypatch.setattr(suno_client._client, "post", post)

    ids = await suno_client.generate_song("upbeat summer song")

    assert ids == ["clip-1", "clip-2"]
    post.assert_awaited_once_with(
        "/api/generate",
        json={"prompt": "upbeat summer song", "make_instrumental": False, "wait_audio": False},
    )


async def test_wait_for_clips_returns_immediately_when_ready(monkeypatch):
    clips = [
        {"id": "clip-1", "audio_url": "https://cdn.example/1.mp3", "title": "Song 1"},
        {"id": "clip-2", "audio_url": "https://cdn.example/2.mp3", "title": "Song 2"},
    ]
    get = AsyncMock(return_value=_FakeResponse(clips))
    monkeypatch.setattr(suno_client._client, "get", get)

    result = await suno_client.wait_for_clips(["clip-1", "clip-2"], interval=0)

    assert result == clips
    get.assert_awaited_once_with("/api/get", params={"ids": "clip-1,clip-2"})


async def test_wait_for_clips_polls_until_ready(monkeypatch):
    pending = [{"id": "clip-1", "audio_url": None}, {"id": "clip-2", "audio_url": None}]
    ready = [
        {"id": "clip-1", "audio_url": "https://cdn.example/1.mp3"},
        {"id": "clip-2", "audio_url": "https://cdn.example/2.mp3"},
    ]
    get = AsyncMock(side_effect=[_FakeResponse(pending), _FakeResponse(ready)])
    monkeypatch.setattr(suno_client._client, "get", get)

    result = await suno_client.wait_for_clips(["clip-1", "clip-2"], interval=0)

    assert result == ready
    assert get.await_count == 2


async def test_wait_for_clips_raises_timeout_error(monkeypatch):
    pending = [{"id": "clip-1", "audio_url": None}, {"id": "clip-2", "audio_url": None}]
    get = AsyncMock(return_value=_FakeResponse(pending))
    monkeypatch.setattr(suno_client._client, "get", get)

    with pytest.raises(TimeoutError):
        await suno_client.wait_for_clips(["clip-1", "clip-2"], timeout=0, interval=0)


async def test_wait_for_clips_raises_on_empty_ids():
    with pytest.raises(ValueError):
        await suno_client.wait_for_clips([])


async def test_wait_for_clips_keeps_polling_on_partial_response(monkeypatch):
    partial = [{"id": "clip-1", "audio_url": "https://cdn.example/1.mp3"}]
    ready = [
        {"id": "clip-1", "audio_url": "https://cdn.example/1.mp3"},
        {"id": "clip-2", "audio_url": "https://cdn.example/2.mp3"},
    ]
    get = AsyncMock(side_effect=[_FakeResponse(partial), _FakeResponse(ready)])
    monkeypatch.setattr(suno_client._client, "get", get)

    result = await suno_client.wait_for_clips(["clip-1", "clip-2"], interval=0)

    assert result == ready
    assert get.await_count == 2


async def test_wait_for_clips_times_out_on_empty_response(monkeypatch):
    get = AsyncMock(return_value=_FakeResponse([]))
    monkeypatch.setattr(suno_client._client, "get", get)

    with pytest.raises(TimeoutError):
        await suno_client.wait_for_clips(["clip-1", "clip-2"], timeout=0, interval=0)
