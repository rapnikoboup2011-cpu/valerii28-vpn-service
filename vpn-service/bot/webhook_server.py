import logging

from aiogram import Bot
from fastapi import FastAPI, Request

from bot.db import db
from bot.handlers.user import deliver_subscription
from bot.services import yookassa_client

logger = logging.getLogger(__name__)


def create_webhook_app(bot: Bot) -> FastAPI:
    app = FastAPI()

    @app.post("/yookassa/webhook")
    async def yookassa_webhook(request: Request) -> dict:
        body = await request.json()
        payment_id = body.get("object", {}).get("id")
        if not payment_id:
            return {"ok": False}

        # Never trust the webhook body's status directly — re-fetch the
        # payment from YooKassa's API to confirm it actually succeeded.
        payment = yookassa_client.get_payment(payment_id)
        if payment.status != "succeeded":
            return {"ok": True}

        order = await db.get_order_by_yookassa_payment(payment_id)
        if order is None:
            logger.warning("Payment %s succeeded but no matching order found", payment_id)
            return {"ok": True}

        if order["status"] == "paid":
            return {"ok": True}

        await db.mark_order_paid(order["order_id"])

        subscription_url = await deliver_subscription(order["telegram_id"], order["months"])
        await bot.send_message(
            order["telegram_id"],
            f"Оплата получена! Ваша ссылка подписки:\n{subscription_url}\n\n"
            "Вставьте её в приложение (Happ, v2rayNG и т.п.) в качестве подписки.",
        )
        return {"ok": True}

    return app
