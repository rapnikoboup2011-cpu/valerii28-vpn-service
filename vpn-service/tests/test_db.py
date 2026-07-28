from __future__ import annotations

import os
import tempfile

import aiosqlite

from bot.config import config
from bot.db import db as db_module


async def test_init_db_migrates_legacy_orders_schema(monkeypatch):
    """A pre-existing DB from the YooKassa era has amount_rub/yookassa_payment_id
    columns instead of amount_stars/telegram_payment_charge_id. init_db() must
    detect the old schema and rebuild the table rather than silently leaving it
    incompatible with the current code."""
    fd, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    try:
        async with aiosqlite.connect(path) as conn:
            await conn.executescript(
                """
                CREATE TABLE orders (
                    order_id TEXT PRIMARY KEY,
                    telegram_id INTEGER NOT NULL,
                    tariff_code TEXT NOT NULL,
                    months INTEGER NOT NULL,
                    amount_rub INTEGER NOT NULL,
                    yookassa_payment_id TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at INTEGER NOT NULL,
                    paid_at INTEGER
                );
                """
            )
            await conn.commit()

        monkeypatch.setattr(config, "database_path", path)
        await db_module.init_db()

        order_id = await db_module.create_order(
            telegram_id=222, tariff_code="1m", months=1, amount_stars=80
        )
        order = await db_module.get_order(order_id)
        assert order["status"] == "pending"
        assert order["amount_stars"] == 80

        await db_module.mark_order_paid(order_id, "charge_xyz")
        order = await db_module.get_order(order_id)
        assert order["status"] == "paid"
        assert order["telegram_payment_charge_id"] == "charge_xyz"
    finally:
        os.remove(path)


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
