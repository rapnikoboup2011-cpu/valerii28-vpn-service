# Suno Song Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let VPN-bot subscribers generate a song from a text prompt via `/song <prompt>`, using an already-deployed suno-api instance, gated on an active Remnawave subscription.

**Architecture:** A new `bot/services/suno_client.py` httpx wrapper talks to the external suno-api (generate + poll for ready clips). A new `bot/services/remnawave_client.is_subscription_active()` answers the access-gate question against the Remnawave panel (source of truth for subscription state). A new `bot/handlers/song.py` router wires the `/song` command to both, with failures reported to the admin the same way `handlers/user.py` already does.

**Tech Stack:** Python, aiogram 3.15.0, httpx 0.27.2 (already a dependency — no new packages needed), pytest 8.3.4 + pytest-asyncio 0.24.0 (`asyncio_mode = auto`, see `pytest.ini`).

## Global Constraints

- No new third-party dependencies — `httpx` is already in `requirements.txt`.
- No per-user rate limiting on song generation (deferred, see spec's Out of scope).
- No new DB table for song requests/history — nothing depends on persisting them.
- Simple single-prompt Suno mode only (`/api/generate`), not custom mode.
- suno-api instance is already deployed and reachable at a fixed URL with no auth in front of it — only `SUNO_API_BASE_URL` needs configuring, nothing else about its deployment changes.
- Match existing code conventions exactly: dataclass-based `Config`, module-level `httpx.AsyncClient` in service files (see `bot/services/remnawave_client.py`), tests use `pytest-asyncio` auto mode + `monkeypatch.setattr("bot.module.path.function", AsyncMock(...))` + `SimpleNamespace` fakes for aiogram objects (see `tests/test_handlers_successful_payment.py`), no `from __future__ import annotations` in `bot/services/*.py` or `bot/handlers/*.py` (matches `remnawave_client.py` / `user.py`, unlike `config.py`/`db.py`).
- Full spec: `docs/superpowers/specs/2026-07-28-suno-song-generation-design.md`.

---

### Task 1: Config — `SUNO_API_BASE_URL`

**Files:**
- Modify: `bot/config.py`
- Modify: `.env.example`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `config.suno_api_base_url: str` (empty string if unset), consumed by Task 3's `suno_client.py`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py`:

```python
def test_suno_api_base_url_loads_from_env(monkeypatch):
    monkeypatch.setenv("SUNO_API_BASE_URL", "https://suno.example.com")

    from bot.config import Config

    cfg = Config()

    assert cfg.suno_api_base_url == "https://suno.example.com"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py::test_suno_api_base_url_loads_from_env -v`
Expected: FAIL with `AttributeError: 'Config' object has no attribute 'suno_api_base_url'`

- [ ] **Step 3: Add the field**

In `bot/config.py`, add this line inside the `Config` dataclass, right after the `remnawave_api_token` line (line 25):

```python
    suno_api_base_url: str = os.getenv("SUNO_API_BASE_URL", "")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: all tests PASS

- [ ] **Step 5: Document the env var**

Append to `.env.example`:

```
# --- Suno API (self-hosted https://github.com/gcui-art/suno-api) ---
SUNO_API_BASE_URL=https://suno.example.com
```

- [ ] **Step 6: Commit**

```bash
git add bot/config.py .env.example tests/test_config.py
git commit -m "feat: add SUNO_API_BASE_URL config"
```

---

### Task 2: `remnawave_client.is_subscription_active`

**Files:**
- Modify: `bot/services/remnawave_client.py`
- Test: Create `tests/test_remnawave_client.py`

**Interfaces:**
- Consumes: `db.get_user(telegram_id) -> aiosqlite.Row | None` (existing, `bot/db/db.py:45`), `get_user(remnawave_uuid) -> dict` (existing, same file, line 56).
- Produces: `is_subscription_active(telegram_id: int) -> bool`, consumed by Task 4's `song.py` handler.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_remnawave_client.py`:

```python
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import bot.services.remnawave_client as remnawave_client


async def test_is_subscription_active_false_without_local_user(monkeypatch):
    monkeypatch.setattr(remnawave_client.db_module, "get_user", AsyncMock(return_value=None))
    remote_get_user = AsyncMock()
    monkeypatch.setattr(remnawave_client, "get_user", remote_get_user)

    result = await remnawave_client.is_subscription_active(111)

    assert result is False
    remote_get_user.assert_not_awaited()


async def test_is_subscription_active_false_without_remnawave_uuid(monkeypatch):
    monkeypatch.setattr(
        remnawave_client.db_module, "get_user", AsyncMock(return_value={"remnawave_uuid": None})
    )
    remote_get_user = AsyncMock()
    monkeypatch.setattr(remnawave_client, "get_user", remote_get_user)

    result = await remnawave_client.is_subscription_active(111)

    assert result is False
    remote_get_user.assert_not_awaited()


async def test_is_subscription_active_true_for_active_future_expiry(monkeypatch):
    monkeypatch.setattr(
        remnawave_client.db_module, "get_user", AsyncMock(return_value={"remnawave_uuid": "uuid-1"})
    )
    future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat().replace("+00:00", "Z")
    monkeypatch.setattr(
        remnawave_client,
        "get_user",
        AsyncMock(return_value={"status": "ACTIVE", "expireAt": future}),
    )

    result = await remnawave_client.is_subscription_active(111)

    assert result is True


async def test_is_subscription_active_false_for_expired_date(monkeypatch):
    monkeypatch.setattr(
        remnawave_client.db_module, "get_user", AsyncMock(return_value={"remnawave_uuid": "uuid-1"})
    )
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    monkeypatch.setattr(
        remnawave_client,
        "get_user",
        AsyncMock(return_value={"status": "ACTIVE", "expireAt": past}),
    )

    result = await remnawave_client.is_subscription_active(111)

    assert result is False


async def test_is_subscription_active_false_for_non_active_status(monkeypatch):
    monkeypatch.setattr(
        remnawave_client.db_module, "get_user", AsyncMock(return_value={"remnawave_uuid": "uuid-1"})
    )
    future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat().replace("+00:00", "Z")
    monkeypatch.setattr(
        remnawave_client,
        "get_user",
        AsyncMock(return_value={"status": "DISABLED", "expireAt": future}),
    )

    result = await remnawave_client.is_subscription_active(111)

    assert result is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_remnawave_client.py -v`
Expected: FAIL — `AttributeError: module 'bot.services.remnawave_client' has no attribute 'db_module'` (and no `is_subscription_active`)

- [ ] **Step 3: Implement**

In `bot/services/remnawave_client.py`, add this import alongside the existing ones at the top (after `from bot.config import config` on line 19):

```python
from bot.db import db as db_module
```

Then add this function at the end of the file (after `get_subscription_url`, currently ending at line 64):

```python


async def is_subscription_active(telegram_id: int) -> bool:
    user_row = await db_module.get_user(telegram_id)
    if user_row is None or not user_row["remnawave_uuid"]:
        return False

    remnawave_user = await get_user(user_row["remnawave_uuid"])
    if remnawave_user.get("status") != "ACTIVE":
        return False

    expire_at = datetime.fromisoformat(remnawave_user["expireAt"].replace("Z", "+00:00"))
    return expire_at > datetime.now(timezone.utc)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_remnawave_client.py -v`
Expected: all 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add bot/services/remnawave_client.py tests/test_remnawave_client.py
git commit -m "feat: add is_subscription_active to remnawave_client"
```

---

### Task 3: `suno_client.py`

**Files:**
- Create: `bot/services/suno_client.py`
- Test: Create `tests/test_suno_client.py`

**Interfaces:**
- Consumes: `config.suno_api_base_url` (Task 1).
- Produces: `generate_song(prompt: str) -> list[str]` and `wait_for_clips(ids: list[str], timeout: float = 240.0, interval: float = 8.0) -> list[dict]`, both consumed by Task 4's `song.py` handler. `wait_for_clips` raises `TimeoutError` if clips aren't ready within `timeout` seconds.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_suno_client.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_suno_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.services.suno_client'`

- [ ] **Step 3: Implement**

Create `bot/services/suno_client.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_suno_client.py -v`
Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add bot/services/suno_client.py tests/test_suno_client.py
git commit -m "feat: add suno_client for song generation and polling"
```

---

### Task 4: `/song` handler, registration, docs

**Files:**
- Create: `bot/handlers/song.py`
- Modify: `bot/main.py`
- Modify: `README.md`
- Test: Create `tests/test_handlers_song.py`

**Interfaces:**
- Consumes: `remnawave_client.is_subscription_active(telegram_id: int) -> bool` (Task 2), `suno_client.generate_song(prompt: str) -> list[str]` and `suno_client.wait_for_clips(ids: list[str]) -> list[dict]` (Task 3), `config.admin_telegram_id: int` (existing, `bot/config.py:22`).
- Produces: `song.router` (aiogram `Router`), registered in `main.py`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_handlers_song.py`:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.handlers.song import cmd_song


def _make_message(user_id: int = 111):
    bot = SimpleNamespace(send_message=AsyncMock())
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id),
        bot=bot,
        answer=AsyncMock(),
        answer_audio=AsyncMock(),
    )


def _command(args):
    return SimpleNamespace(args=args)


async def test_cmd_song_without_prompt_shows_usage(monkeypatch):
    is_active = AsyncMock()
    monkeypatch.setattr("bot.handlers.song.remnawave_client.is_subscription_active", is_active)

    message = _make_message()

    await cmd_song(message, _command(None))

    message.answer.assert_awaited_once()
    assert "Использование" in message.answer.call_args.args[0]
    is_active.assert_not_awaited()


async def test_cmd_song_rejects_inactive_subscription(monkeypatch):
    monkeypatch.setattr(
        "bot.handlers.song.remnawave_client.is_subscription_active", AsyncMock(return_value=False)
    )
    generate = AsyncMock()
    monkeypatch.setattr("bot.handlers.song.suno_client.generate_song", generate)

    message = _make_message()

    await cmd_song(message, _command("summer song"))

    message.answer.assert_awaited_once()
    assert "подпис" in message.answer.call_args.args[0].lower()
    generate.assert_not_awaited()


async def test_cmd_song_happy_path_sends_both_clips(monkeypatch):
    monkeypatch.setattr(
        "bot.handlers.song.remnawave_client.is_subscription_active", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        "bot.handlers.song.suno_client.generate_song",
        AsyncMock(return_value=["clip-1", "clip-2"]),
    )
    clips = [
        {"id": "clip-1", "audio_url": "https://cdn.example/1.mp3", "title": "Song 1"},
        {"id": "clip-2", "audio_url": "https://cdn.example/2.mp3", "title": "Song 2"},
    ]
    monkeypatch.setattr("bot.handlers.song.suno_client.wait_for_clips", AsyncMock(return_value=clips))

    message = _make_message()

    await cmd_song(message, _command("summer song"))

    assert message.answer.await_count == 1  # only the "generating..." message
    assert message.answer_audio.await_count == 2
    message.bot.send_message.assert_not_awaited()


async def test_cmd_song_notifies_admin_on_generation_failure(monkeypatch):
    monkeypatch.setattr(
        "bot.handlers.song.remnawave_client.is_subscription_active", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        "bot.handlers.song.suno_client.generate_song",
        AsyncMock(side_effect=RuntimeError("suno-api down")),
    )
    monkeypatch.setattr("bot.handlers.song.config.admin_telegram_id", 999)

    message = _make_message()

    await cmd_song(message, _command("summer song"))

    message.bot.send_message.assert_awaited_once()
    args, _ = message.bot.send_message.call_args
    assert args[0] == 999
    assert "111" in args[1]
    assert message.answer.await_count == 2  # "generating..." + failure message
    message.answer_audio.assert_not_awaited()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_handlers_song.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.handlers.song'`

- [ ] **Step 3: Implement the handler**

Create `bot/handlers/song.py`:

```python
from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, URLInputFile

from bot.config import config
from bot.services import remnawave_client, suno_client

router = Router()


@router.message(Command("song"))
async def cmd_song(message: Message, command: CommandObject) -> None:
    prompt = (command.args or "").strip()
    if not prompt:
        await message.answer(
            "Использование: /song <описание песни>\nНапример: /song весёлая песня про лето"
        )
        return

    if not await remnawave_client.is_subscription_active(message.from_user.id):
        await message.answer(
            "Генерация песен доступна только подписчикам VPN. Оформите подписку через /start."
        )
        return

    await message.answer("🎵 Генерирую песню, обычно это занимает 1–3 минуты...")

    try:
        clip_ids = await suno_client.generate_song(prompt)
        clips = await suno_client.wait_for_clips(clip_ids)
    except Exception as exc:  # noqa: BLE001 - any failure must be reported to admin regardless of cause
        try:
            await message.bot.send_message(
                config.admin_telegram_id,
                f"⚠️ Генерация песни для user_id={message.from_user.id} упала: {exc}",
            )
        except Exception:  # noqa: BLE001 - admin alert failing must not swallow the user notice
            pass
        await message.answer("Не получилось сгенерировать песню, попробуйте позже.")
        return

    for clip in clips:
        await message.answer_audio(
            audio=URLInputFile(clip["audio_url"]),
            title=clip.get("title") or "Song",
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_handlers_song.py -v`
Expected: all 4 tests PASS

- [ ] **Step 5: Register the router**

In `bot/main.py`, change the import on line 11 from:

```python
from bot.handlers import user
```

to:

```python
from bot.handlers import song, user
```

And add a line after `dp.include_router(user.router)` (line 24):

```python
    dp.include_router(user.router)
    dp.include_router(song.router)
```

- [ ] **Step 6: Update README.md**

In `README.md`, add a new bullet at the end of the "Как это работает" section (after line 10):

```markdown
5. Подписчики с активной подпиской могут написать `/song <описание песни>` — бот сгенерирует песню через self-hosted [suno-api](https://github.com/gcui-art/suno-api) и пришлёт готовые аудио прямо в чат.
```

In the "Настройка" section, add a bullet to the `.env` list (after line 16):

```markdown
   - `SUNO_API_BASE_URL` — адрес вашего развёрнутого suno-api (для команды `/song`)
```

In the "Структура" section, update the code block (lines 34-42) to:

```
bot/
  config.py           — тарифы (в звёздах) и переменные окружения
  db/db.py             — sqlite: пользователи и заказы
  services/
    remnawave_client.py — создание/продление пользователей VPN, проверка активной подписки
    suno_client.py       — генерация песни и поллинг готовых клипов через suno-api
  handlers/
    user.py              — /start, выбор тариф, инвойс, pre_checkout_query, successful_payment
    song.py               — /song, генерация песни для подписчиков
  main.py              — точка входа (long-polling бота)
```

- [ ] **Step 7: Run the full test suite**

Run: `pytest -v`
Expected: all tests PASS (existing + new)

- [ ] **Step 8: Commit**

```bash
git add bot/handlers/song.py bot/main.py README.md tests/test_handlers_song.py
git commit -m "feat: add /song command for subscribers"
```

---

## Manual verification (not automated)

Automated tests mock `suno_client` and `remnawave_client` entirely — they don't exercise a real Suno account, 2Captcha balance, or Remnawave panel. After deploying:

1. Set `SUNO_API_BASE_URL` in the real `.env` to your deployed suno-api instance.
2. From an account with an active Remnawave subscription, send `/song весёлая песня про лето` to the bot.
3. Confirm the "🎵 Генерирую..." message appears, followed within a few minutes by two audio messages.
4. From an account without an active subscription, confirm `/song <prompt>` replies with the subscription-required message and does not call suno-api (check suno-api logs / your Suno account's generation history to be sure).
