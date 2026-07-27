import uuid

from yookassa import Configuration, Payment

from bot.config import config

Configuration.account_id = config.yookassa_shop_id
Configuration.secret_key = config.yookassa_secret_key


def create_payment(amount_rub: int, description: str, order_id: str, return_url: str) -> tuple[str, str]:
    """Creates a YooKassa payment and returns (payment_id, confirmation_url)."""
    idempotence_key = str(uuid.uuid4())
    payment = Payment.create(
        {
            "amount": {"value": f"{amount_rub}.00", "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": return_url},
            "capture": True,
            "description": description,
            "metadata": {"order_id": order_id},
        },
        idempotence_key,
    )
    return payment.id, payment.confirmation.confirmation_url


def get_payment(payment_id: str) -> Payment:
    return Payment.find_one(payment_id)
