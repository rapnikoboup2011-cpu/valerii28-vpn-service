from __future__ import annotations

import time
import uuid

import aiosqlite

from bot.config import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    remnawave_uuid TEXT,
    remnawave_username TEXT,
    subscription_url TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    telegram_id INTEGER NOT NULL,
    tariff_code TEXT NOT NULL,
    months INTEGER NOT NULL,
    amount_stars INTEGER NOT NULL,
    telegram_payment_charge_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at INTEGER NOT NULL,
    paid_at INTEGER
);
"""


async def init_db() -> None:
    async with aiosqlite.connect(config.database_path) as db:
        cursor = await db.execute("PRAGMA table_info(orders)")
        columns = {row[1] for row in await cursor.fetchall()}
        if columns and ("amount_rub" in columns or "yookassa_payment_id" in columns):
            # Pre-existing DB from the YooKassa era: no production data has ever
            # existed under this schema, so it's safe to drop and recreate.
            await db.execute("DROP TABLE orders")
        await db.executescript(_SCHEMA)
        await db.commit()


async def get_user(telegram_id: int) -> aiosqlite.Row | None:
    async with aiosqlite.connect(config.database_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        return await cursor.fetchone()


async def upsert_user(
    telegram_id: int,
    remnawave_uuid: str | None = None,
    remnawave_username: str | None = None,
    subscription_url: str | None = None,
) -> None:
    async with aiosqlite.connect(config.database_path) as db:
        existing = await db.execute("SELECT 1 FROM users WHERE telegram_id = ?", (telegram_id,))
        row = await existing.fetchone()
        if row is None:
            await db.execute(
                """INSERT INTO users (telegram_id, remnawave_uuid, remnawave_username, subscription_url, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (telegram_id, remnawave_uuid, remnawave_username, subscription_url, int(time.time())),
            )
        else:
            await db.execute(
                """UPDATE users SET
                       remnawave_uuid = COALESCE(?, remnawave_uuid),
                       remnawave_username = COALESCE(?, remnawave_username),
                       subscription_url = COALESCE(?, subscription_url)
                   WHERE telegram_id = ?""",
                (remnawave_uuid, remnawave_username, subscription_url, telegram_id),
            )
        await db.commit()


async def create_order(telegram_id: int, tariff_code: str, months: int, amount_stars: int) -> str:
    order_id = str(uuid.uuid4())
    async with aiosqlite.connect(config.database_path) as db:
        await db.execute(
            """INSERT INTO orders (order_id, telegram_id, tariff_code, months, amount_stars, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
            (order_id, telegram_id, tariff_code, months, amount_stars, int(time.time())),
        )
        await db.commit()
    return order_id


async def get_order(order_id: str) -> aiosqlite.Row | None:
    async with aiosqlite.connect(config.database_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
        return await cursor.fetchone()


async def mark_order_paid(order_id: str, telegram_payment_charge_id: str) -> None:
    async with aiosqlite.connect(config.database_path) as db:
        await db.execute(
            """UPDATE orders SET status = 'paid', telegram_payment_charge_id = ?, paid_at = ?
               WHERE order_id = ?""",
            (telegram_payment_charge_id, int(time.time()), order_id),
        )
        await db.commit()
