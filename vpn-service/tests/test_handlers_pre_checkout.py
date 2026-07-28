from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.handlers.user import on_pre_checkout


async def test_pre_checkout_accepts_pending_order(monkeypatch):
    order = {"status": "pending"}
    monkeypatch.setattr("bot.handlers.user.db.get_order", AsyncMock(return_value=order))

    query = SimpleNamespace(invoice_payload="order-123", answer=AsyncMock())

    await on_pre_checkout(query)

    query.answer.assert_awaited_once_with(ok=True)


async def test_pre_checkout_rejects_missing_order(monkeypatch):
    monkeypatch.setattr("bot.handlers.user.db.get_order", AsyncMock(return_value=None))

    query = SimpleNamespace(invoice_payload="order-404", answer=AsyncMock())

    await on_pre_checkout(query)

    _, kwargs = query.answer.call_args
    assert kwargs["ok"] is False
    assert kwargs["error_message"] == "Заказ не найден, попробуйте оформить заново через /start."


async def test_pre_checkout_rejects_already_paid_order(monkeypatch):
    order = {"status": "paid"}
    monkeypatch.setattr("bot.handlers.user.db.get_order", AsyncMock(return_value=order))

    query = SimpleNamespace(invoice_payload="order-123", answer=AsyncMock())

    await on_pre_checkout(query)

    _, kwargs = query.answer.call_args
    assert kwargs["ok"] is False
    assert kwargs["error_message"] == "Этот заказ уже оплачен."
