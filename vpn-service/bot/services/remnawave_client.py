"""
Client for the Remnawave panel API.

IMPORTANT: endpoint paths and field names below are best-effort based on
Remnawave's public architecture (REST API, Bearer token auth via
JWT_API_TOKENS_SECRET). They are NOT yet verified against a live instance.

Once the panel is reachable, set IS_DOCS_ENABLED=true in its .env, open
https://<panel-domain>/docs (Swagger) or /scalar, and cross-check the
methods below against the real /api/users endpoints. Adjust field names
here — everything Remnawave-specific is isolated in this one file, nothing
else in the bot depends on the exact shape.
"""

from datetime import datetime, timedelta, timezone

import httpx

from bot.config import config
from bot.db import db as db_module

_client = httpx.AsyncClient(
    base_url=config.remnawave_base_url,
    headers={"Authorization": f"Bearer {config.remnawave_api_token}"},
    timeout=30.0,
)


async def create_user(username: str, months: int) -> dict:
    expire_at = datetime.now(timezone.utc) + timedelta(days=30 * months)
    response = await _client.post(
        "/api/users",
        json={
            "username": username,
            "expireAt": expire_at.isoformat(),
            "status": "ACTIVE",
        },
    )
    response.raise_for_status()
    return response.json()["response"]


async def extend_user(remnawave_uuid: str, months: int) -> dict:
    user = await get_user(remnawave_uuid)
    current_expire = datetime.fromisoformat(user["expireAt"].replace("Z", "+00:00"))
    base = max(current_expire, datetime.now(timezone.utc))
    new_expire = base + timedelta(days=30 * months)

    response = await _client.patch(
        f"/api/users/{remnawave_uuid}",
        json={"expireAt": new_expire.isoformat(), "status": "ACTIVE"},
    )
    response.raise_for_status()
    return response.json()["response"]


async def get_user(remnawave_uuid: str) -> dict:
    response = await _client.get(f"/api/users/{remnawave_uuid}")
    response.raise_for_status()
    return response.json()["response"]


async def get_subscription_url(user: dict) -> str:
    short_uuid = user.get("shortUuid") or user["uuid"]
    return f"{config.remnawave_base_url}/api/sub/{short_uuid}"


async def is_subscription_active(telegram_id: int) -> bool:
    user_row = await db_module.get_user(telegram_id)
    if user_row is None or not user_row["remnawave_uuid"]:
        return False

    remnawave_user = await get_user(user_row["remnawave_uuid"])
    if remnawave_user.get("status") != "ACTIVE":
        return False

    expire_at = datetime.fromisoformat(remnawave_user["expireAt"].replace("Z", "+00:00"))
    return expire_at > datetime.now(timezone.utc)
