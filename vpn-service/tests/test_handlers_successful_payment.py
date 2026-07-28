from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.handlers.user import on_successful_payment


def _make_message(order_id: str, charge_id: str = "charge_1"):
    successful_payment = SimpleNamespace(invoice_payload=order_id, telegram_payment_charge_id=charge_id)
    bot = SimpleNamespace(send_message=AsyncMock())
    return SimpleNamespace(successful_payment=successful_payment, bot=bot, answer=AsyncMock())


async def test_successful_payment_delivers_subscription(monkeypatch):
    order = {"status": "pending", "telegram_id": 111, "months": 1}
    monkeypatch.setattr("bot.handlers.user.db.get_order", AsyncMock(return_value=order))
    mark_paid = AsyncMock()
    monkeypatch.setattr("bot.handlers.user.db.mark_order_paid", mark_paid)
    monkeypatch.setattr(
        "bot.handlers.user.deliver_subscription", AsyncMock(return_value="https://sub.example/abc")
    )

    message = _make_message("order-1")

    await on_successful_payment(message)

    mark_paid.assert_awaited_once_with("order-1", "charge_1")
    message.answer.assert_awaited_once()
    assert "https://sub.example/abc" in message.answer.call_args.args[0]


async def test_successful_payment_ignores_already_paid_order(monkeypatch):
    order = {"status": "paid", "telegram_id": 111, "months": 1}
    monkeypatch.setattr("bot.handlers.user.db.get_order", AsyncMock(return_value=order))
    mark_paid = AsyncMock()
    monkeypatch.setattr("bot.handlers.user.db.mark_order_paid", mark_paid)

    message = _make_message("order-1")

    await on_successful_payment(message)

    mark_paid.assert_not_awaited()
    message.answer.assert_not_awaited()


async def test_successful_payment_notifies_admin_on_delivery_failure(monkeypatch):
    order = {"status": "pending", "telegram_id": 111, "months": 1}
    monkeypatch.setattr("bot.handlers.user.db.get_order", AsyncMock(return_value=order))
    monkeypatch.setattr("bot.handlers.user.db.mark_order_paid", AsyncMock())
    monkeypatch.setattr(
        "bot.handlers.user.deliver_subscription",
        AsyncMock(side_effect=RuntimeError("remnawave down")),
    )
    monkeypatch.setattr("bot.handlers.user.config.admin_telegram_id", 999)

    message = _make_message("order-1")

    await on_successful_payment(message)

    message.bot.send_message.assert_awaited_once()
    args, _ = message.bot.send_message.call_args
    assert args[0] == 999
    assert "order-1" in args[1]
    message.answer.assert_not_awaited()
