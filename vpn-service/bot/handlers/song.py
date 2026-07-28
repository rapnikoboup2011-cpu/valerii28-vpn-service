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
