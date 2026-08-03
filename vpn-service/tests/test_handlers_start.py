from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.handlers.user import cmd_start


async def test_start_prompts_tariff_choice_for_new_user(monkeypatch):
    monkeypatch.setattr("bot.handlers.user.db.upsert_user", AsyncMock())
    monkeypatch.setattr("bot.handlers.user.db.get_user", AsyncMock(return_value=None))

    message = SimpleNamespace(from_user=SimpleNamespace(id=111), answer=AsyncMock())

    await cmd_start(message)

    message.answer.assert_awaited_once()
    text = message.answer.call_args.args[0]
    assert "Выберите тариф" in text


async def test_start_shows_active_subscription_instead_of_tariff_prompt(monkeypatch):
    monkeypatch.setattr("bot.handlers.user.db.upsert_user", AsyncMock())
    monkeypatch.setattr(
        "bot.handlers.user.db.get_user",
        AsyncMock(return_value={"subscription_url": "https://sub.valerii28.ru/abc123"}),
    )

    message = SimpleNamespace(from_user=SimpleNamespace(id=111), answer=AsyncMock())

    await cmd_start(message)

    message.answer.assert_awaited_once()
    text = message.answer.call_args.args[0]
    assert "https://sub.valerii28.ru/abc123" in text
    assert "Выберите тариф" not in text
