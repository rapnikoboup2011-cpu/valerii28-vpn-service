# Song generation via Suno API — design

## Context

The bot's owner wants a bonus feature for the VPN bot: subscribers with an active
Remnawave subscription can generate a song from a text prompt, using a self-hosted
instance of [suno-api](https://github.com/gcui-art/suno-api) (an unofficial wrapper
around Suno AI). The suno-api instance is already deployed separately by the owner
(open URL, no auth in front of it) — this design only covers the bot-side integration,
not deploying suno-api itself.

No payment or per-user rate limiting for song generation this round — access is
gated purely on having an active VPN subscription, same as the rest of the bot.

## Generation flow

1. User sends `/song <prompt>` (e.g. `/song upbeat summer road trip song`). If no
   prompt follows the command, the bot replies with a usage hint and stops.
2. The handler checks `remnawave_client.is_subscription_active(telegram_id)`. If
   false, the bot replies asking the user to get a subscription via `/start` and
   stops — no call to suno-api is made.
3. If active, the bot replies "🎵 Генерирую песню, обычно 1–3 минуты..." and calls
   `suno_client.generate_song(prompt)`, which POSTs to `/api/generate` (simple mode —
   Suno writes both lyrics and style from the prompt, `make_instrumental=False`).
   This returns 2 clip ids (Suno always generates a pair).
4. The handler polls `suno_client.wait_for_clips(ids)`, which calls
   `GET /api/get?ids=<id1>,<id2>` on an interval until every clip has a non-empty
   `audio_url` (or reaches a timeout).
5. As each clip becomes ready, the bot sends it with
   `message.answer_audio(audio=audio_url, title=clip_title)` — the URL is passed as a
   plain string. Telegram fetches the file from the URL server-side — the bot never
   downloads it to disk (unlike `URLInputFile`, which would proxy the download through
   the bot process).
6. If suno-api returns an error (HTTP error, account/captcha/credits exhausted) or
   polling times out, the user gets a neutral "не получилось сгенерировать песню,
   попробуйте позже" and the admin gets the exception detail via DM — same pattern as
   the existing `deliver_subscription` failure handling in `handlers/user.py`.

## Components added

- **`bot/services/suno_client.py`** — httpx wrapper around the deployed suno-api
  instance. Knows nothing about Telegram. Two functions:
  - `generate_song(prompt: str) -> list[str]` — POST `/api/generate`, returns clip ids.
  - `wait_for_clips(ids: list[str], timeout: float = 240, interval: float = 8) -> list[dict]`
    — polls `/api/get?ids=...` until every clip has `audio_url` set or the timeout
    elapses (raises `TimeoutError` on timeout).
- **`bot/handlers/song.py`** — new router, isolated from `handlers/user.py` (payment/
  VPN provisioning stays untouched). Registers the `/song` command handler described
  above.

## Components changed

- **`bot/config.py`** — add `suno_api_base_url: str = os.getenv("SUNO_API_BASE_URL", "")`.
- **`bot/services/remnawave_client.py`** — add
  `is_subscription_active(telegram_id: int) -> bool`: looks up the local user row via
  `db.get_user` for `remnawave_uuid` (returns `False` if the user or uuid is missing),
  then calls the existing `get_user(remnawave_uuid)` and checks
  `status == "ACTIVE"` and `expireAt` is in the future. Remnawave is treated as the
  source of truth for subscription state — the local SQLite `users` table has no
  expiry column to check against.
- **`bot/main.py`** — `dp.include_router(song.router)` alongside the existing
  `user.router`.
- **`.env.example`** — add `SUNO_API_BASE_URL`.
- **`README.md`** — document the `/song` command and the `SUNO_API_BASE_URL` setting.

## Error handling

- Missing/empty prompt after `/song`: handled before any network call, just a usage
  reply.
- Inactive subscription: handled before any network call, no suno-api credits spent
  on users who aren't entitled to the feature.
- suno-api HTTP errors and polling timeouts: caught in the handler, user gets a
  generic failure message, admin gets the exception via DM (mirrors the existing
  `on_successful_payment` → `deliver_subscription` failure path).

## Out of scope

- Rate limiting per user — explicitly deferred; can be added later if Suno/2Captcha
  usage becomes a problem.
- Persisting song requests/history — nothing depends on it yet (no limit to enforce,
  no history to show), so no new DB table.
- Custom mode (separate lyrics/style/title inputs) — simple single-prompt mode only.
- Any changes to how suno-api itself is deployed, authenticated, or scaled — it's
  already running and reachable at a fixed URL.

## Testing

- `is_subscription_active` — active user (future `expireAt`, `ACTIVE` status),
  expired user, `ACTIVE` status but past `expireAt`, and no local user row at all —
  four cases, `remnawave_client.get_user`/`db.get_user` mocked.
- `suno_client.generate_song` / `wait_for_clips` — mocked httpx responses: happy path
  (both clips ready on first poll), clips ready after a few polls, and the timeout
  path.
- `/song` handler — mocked `Message`/`is_subscription_active`/`suno_client`: no
  prompt, inactive subscription, and the happy path sending two audio messages.

`Bot`/`Message` are mocked, same as the existing test suite — no real Telegram or
suno-api calls in tests.
