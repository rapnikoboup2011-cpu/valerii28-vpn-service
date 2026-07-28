from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.config import config
from bot.handlers.user import on_buy


async def test_on_buy_sends_stars_invoice(monkeypatch):
    created_order_id = "order-xyz"
    monkeypatch.setattr(
        "bot.handlers.user.db.create_order", AsyncMock(return_value=created_order_id)
    )

    callback = SimpleNamespace(
        data="buy:1m",
        from_user=SimpleNamespace(id=555),
        message=SimpleNamespace(answer_invoice=AsyncMock()),
        answer=AsyncMock(),
    )

    await on_buy(callback)

    callback.message.answer_invoice.assert_awaited_once()
    _, kwargs = callback.message.answer_invoice.call_args
    assert kwargs["currency"] == "XTR"
    assert kwargs["provider_token"] == ""
    assert kwargs["payload"] == created_order_id
    assert kwargs["prices"][0].amount == config.tariff_by_code("1m").price_stars
    callback.answer.assert_awaited_once()


async def test_on_buy_rejects_unknown_tariff(monkeypatch):
    create_order = AsyncMock()
    monkeypatch.setattr("bot.handlers.user.db.create_order", create_order)

    callback = SimpleNamespace(
        data="buy:doesnotexist",
        from_user=SimpleNamespace(id=555),
        message=SimpleNamespace(answer_invoice=AsyncMock()),
        answer=AsyncMock(),
    )

    await on_buy(callback)

    create_order.assert_not_awaited()
    callback.answer.assert_awaited_once_with("Тариф не найден", show_alert=True)
