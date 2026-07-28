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
