from __future__ import annotations

from bot.db import db as db_module


async def test_create_order_defaults_to_pending(temp_db):
    order_id = await db_module.create_order(
        telegram_id=111, tariff_code="1m", months=1, amount_stars=80
    )

    order = await db_module.get_order(order_id)

    assert order["status"] == "pending"
    assert order["amount_stars"] == 80
    assert order["telegram_payment_charge_id"] is None


async def test_mark_order_paid_sets_status_and_charge_id(temp_db):
    order_id = await db_module.create_order(
        telegram_id=111, tariff_code="1m", months=1, amount_stars=80
    )

    await db_module.mark_order_paid(order_id, "charge_abc")
    order = await db_module.get_order(order_id)

    assert order["status"] == "paid"
    assert order["telegram_payment_charge_id"] == "charge_abc"
    assert order["paid_at"] is not None


async def test_get_order_returns_none_for_unknown_id(temp_db):
    order = await db_module.get_order("does-not-exist")

    assert order is None
