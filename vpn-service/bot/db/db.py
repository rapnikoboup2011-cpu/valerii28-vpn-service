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
    amount_rub INTEGER NOT NULL,
    yookassa_payment_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at INTEGER NOT NULL,
    paid_at INTEGER
);
"""


async def init_db() -> None:
    async with aiosqlite.connect(config.database_path) as db:
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


async def create_order(telegram_id: int, tariff_code: str, months: int, amount_rub: int) -> str:
    order_id = str(uuid.uuid4())
    async with aiosqlite.connect(config.database_path) as db:
        await db.execute(
            """INSERT INTO orders (order_id, telegram_id, tariff_code, months, amount_rub, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
            (order_id, telegram_id, tariff_code, months, amount_rub, int(time.time())),
        )
        await db.commit()
    return order_id


async def attach_yookassa_payment(order_id: str, yookassa_payment_id: str) -> None:
    async with aiosqlite.connect(config.database_path) as db:
        await db.execute(
            "UPDATE orders SET yookassa_payment_id = ? WHERE order_id = ?",
            (yookassa_payment_id, order_id),
        )
        await db.commit()


async def get_order_by_yookassa_payment(yookassa_payment_id: str) -> aiosqlite.Row | None:
    async with aiosqlite.connect(config.database_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM orders WHERE yookassa_payment_id = ?", (yookassa_payment_id,)
        )
        return await cursor.fetchone()


async def mark_order_paid(order_id: str) -> None:
    async with aiosqlite.connect(config.database_path) as db:
        await db.execute(
            "UPDATE orders SET status = 'paid', paid_at = ? WHERE order_id = ?",
            (int(time.time()), order_id),
        )
        await db.commit()
