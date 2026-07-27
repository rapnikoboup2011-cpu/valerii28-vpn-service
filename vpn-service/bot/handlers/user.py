from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import config
from bot.db import db
from bot.services import remnawave_client, yookassa_client

router = Router()


def _tariffs_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{t.title} — {t.price_rub}₽",
                callback_data=f"buy:{t.code}",
            )
        ]
        for t in config.tariffs
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await db.upsert_user(message.from_user.id)
    await message.answer(
        "Добро пожаловать! Выберите тариф для подключения VPN:",
        reply_markup=_tariffs_keyboard(),
    )


@router.message(F.text == "/status")
async def cmd_status(message: Message) -> None:
    user = await db.get_user(message.from_user.id)
    if user is None or user["subscription_url"] is None:
        await message.answer("У вас пока нет активной подписки. Наберите /start, чтобы выбрать тариф.")
        return
    await message.answer(f"Ваша ссылка подписки:\n{user['subscription_url']}")


@router.callback_query(F.data.startswith("buy:"))
async def on_buy(callback: CallbackQuery) -> None:
    tariff_code = callback.data.split(":", 1)[1]
    tariff = config.tariff_by_code(tariff_code)
    if tariff is None:
        await callback.answer("Тариф не найден", show_alert=True)
        return

    telegram_id = callback.from_user.id
    order_id = await db.create_order(telegram_id, tariff.code, tariff.months, tariff.price_rub)

    return_url = f"https://t.me/{(await callback.bot.get_me()).username}"
    payment_id, confirmation_url = yookassa_client.create_payment(
        amount_rub=tariff.price_rub,
        description=f"Подписка VPN на {tariff.months} мес.",
        order_id=order_id,
        return_url=return_url,
    )
    await db.attach_yookassa_payment(order_id, payment_id)

    await callback.message.answer(
        f"Тариф «{tariff.title}» — {tariff.price_rub}₽\n\n"
        f"Оплатите по ссылке, после оплаты доступ подключится автоматически:\n{confirmation_url}"
    )
    await callback.answer()


async def deliver_subscription(telegram_id: int, months: int) -> str:
    """Creates or extends the Remnawave user for telegram_id, returns subscription URL."""
    user_row = await db.get_user(telegram_id)

    if user_row and user_row["remnawave_uuid"]:
        remnawave_user = await remnawave_client.extend_user(user_row["remnawave_uuid"], months)
    else:
        username = f"tg{telegram_id}"
        remnawave_user = await remnawave_client.create_user(username, months)

    subscription_url = await remnawave_client.get_subscription_url(remnawave_user)
    await db.upsert_user(
        telegram_id,
        remnawave_uuid=remnawave_user["uuid"],
        remnawave_username=remnawave_user.get("username"),
        subscription_url=subscription_url,
    )
    return subscription_url
