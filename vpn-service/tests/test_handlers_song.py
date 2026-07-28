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
    reply_text = message.answer.call_args.args[0]
    assert "Использование" in reply_text
    assert "<описание" not in reply_text  # must be HTML-escaped, not a bare "<"
    assert "&lt;" in reply_text
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
    message.answer_audio.assert_any_await(audio="https://cdn.example/1.mp3", title="Song 1")
    message.answer_audio.assert_any_await(audio="https://cdn.example/2.mp3", title="Song 2")
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


async def test_cmd_song_notifies_admin_on_subscription_check_failure(monkeypatch):
    monkeypatch.setattr(
        "bot.handlers.song.remnawave_client.is_subscription_active",
        AsyncMock(side_effect=RuntimeError("remnawave down")),
    )
    monkeypatch.setattr("bot.handlers.song.config.admin_telegram_id", 999)

    message = _make_message()

    await cmd_song(message, _command("summer song"))

    message.bot.send_message.assert_awaited_once()
    args, _ = message.bot.send_message.call_args
    assert args[0] == 999
    assert "111" in args[1]
    message.answer.assert_awaited_once()  # only the failure message — "generating..." was never reached
    assert "Не получилось" in message.answer.call_args.args[0]
    message.answer_audio.assert_not_awaited()


async def test_cmd_song_notifies_admin_on_audio_send_failure(monkeypatch):
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
    monkeypatch.setattr("bot.handlers.song.config.admin_telegram_id", 999)

    message = _make_message()
    message.answer_audio = AsyncMock(side_effect=RuntimeError("telegram rejected file"))

    await cmd_song(message, _command("summer song"))

    message.bot.send_message.assert_awaited_once()
    args, _ = message.bot.send_message.call_args
    assert args[0] == 999
    assert "111" in args[1]
    assert message.answer.await_count == 2  # "generating..." + failure message
