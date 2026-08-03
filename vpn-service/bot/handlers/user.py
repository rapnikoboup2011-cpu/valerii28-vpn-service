from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from bot.config import config
from bot.db import db
from bot.services import remnawave_client

router = Router()


def _tariffs_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{t.title} — {t.price_stars} ⭐",
                callback_data=f"buy:{t.code}",
            )
        ]
        for t in config.tariffs
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await db.upsert_user(message.from_user.id)
    user = await db.get_user(message.from_user.id)

    if user and user["subscription_url"]:
        await message.answer(
            f"С возвращением! Ваша подписка активна.\n\nСсылка на подписку:\n{user['subscription_url']}\n\n"
            "Хотите продлить или сменить тариф?",
            reply_markup=_tariffs_keyboard(),
        )
        return

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
    order_id = await db.create_order(telegram_id, tariff.code, tariff.months, tariff.price_stars)

    await callback.message.answer_invoice(
        title=f"VPN подписка — {tariff.title}",
        description=f"Подписка VPN на {tariff.months} мес.",
        payload=order_id,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=tariff.title, amount=tariff.price_stars)],
    )
    await callback.answer()


@router.pre_checkout_query()
async def on_pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
    order = await db.get_order(pre_checkout_query.invoice_payload)
    if order is None:
        await pre_checkout_query.answer(
            ok=False, error_message="Заказ не найден, попробуйте оформить заново через /start."
        )
        return
    if order["status"] == "paid":
        await pre_checkout_query.answer(ok=False, error_message="Этот заказ уже оплачен.")
        return
    if order["telegram_id"] != pre_checkout_query.from_user.id:
        await pre_checkout_query.answer(
            ok=False, error_message="Этот заказ оформлен на другого пользователя."
        )
        return
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message) -> None:
    payment = message.successful_payment
    order_id = payment.invoice_payload
    order = await db.get_order(order_id)
    if order is None or order["status"] == "paid":
        return

    await db.mark_order_paid(order_id, payment.telegram_payment_charge_id)

    try:
        subscription_url, raw_config = await deliver_subscription(order["telegram_id"], order["months"])
    except Exception as exc:  # noqa: BLE001 - payment already captured, admin must be told regardless of cause
        try:
            await message.bot.send_message(
                config.admin_telegram_id,
                f"⚠️ Оплата прошла (order_id={order_id}), но выдача подписки упала: {exc}",
            )
        except Exception:  # noqa: BLE001 - admin alert failing must not swallow the user notice
            pass
        await message.answer(
            "Оплата получена, но выдача подписки временно недоступна. "
            "Мы уже разбираемся, скоро вернёмся с доступом."
        )
        return

    await message.bot.send_message(
        order["telegram_id"],
        f"Оплата получена! Ваша ссылка подписки:\n{subscription_url}\n\n"
        "Вставьте её в приложение (Happ, v2rayNG и т.п.) в качестве подписки.\n\n"
        f"Если страница подписки не открывается, добавьте сервер вручную по этой строке:\n{raw_config}",
    )


async def deliver_subscription(telegram_id: int, months: int) -> tuple[str, str]:
    """Creates or extends the Remnawave user for telegram_id.

    Returns (subscription_url, raw_config) — the raw config is a plain-text
    fallback (e.g. an ss:// link) for clients that can't load the subscription page.
    """
    user_row = await db.get_user(telegram_id)

    if user_row and user_row["remnawave_uuid"]:
        remnawave_user = await remnawave_client.extend_user(user_row["remnawave_uuid"], months)
    else:
        username = f"tg{telegram_id}"
        remnawave_user = await remnawave_client.create_user(username, months)

    subscription_url = await remnawave_client.get_subscription_url(remnawave_user)
    raw_config = await remnawave_client.get_raw_config(remnawave_user)
    await db.upsert_user(
        telegram_id,
        remnawave_uuid=remnawave_user["uuid"],
        remnawave_username=remnawave_user.get("username"),
        subscription_url=subscription_url,
    )
    return subscription_url, raw_config
