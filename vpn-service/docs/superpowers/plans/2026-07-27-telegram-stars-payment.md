# Telegram Stars Payment Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the YooKassa payment integration with Telegram Stars (`XTR`) so the bot can sell VPN subscriptions without a merchant/webhook, since YooKassa declined the registration.

**Architecture:** Drop the external payment provider and its webhook entirely. `on_buy` sends a native Telegram invoice (`currency="XTR"`); Telegram delivers `pre_checkout_query` and `successful_payment` updates directly to the bot's existing long-polling connection — no FastAPI/uvicorn/nginx needed anymore. Orders move `pending` → `paid` inside the `successful_payment` handler, which also drives Remnawave provisioning and notifies the admin if provisioning fails after the Stars were already captured.

**Tech Stack:** Python 3.12, aiogram 3.15, aiosqlite, pytest + pytest-asyncio (new dev dependency).

## Global Constraints

- Stars prices are integers with no decimals: 1 month = 80 ⭐, 3 months = 210 ⭐, 12 months = 680 ⭐ (from `docs/superpowers/specs/2026-07-27-telegram-stars-payment-design.md`).
- `provider_token` must be `""` for Stars invoices — this is not a placeholder, it's required by the Stars API.
- No refund flow in this iteration (`refundStarPayment` is out of scope).
- No data migration needed — there are no real paid orders yet (YooKassa was never approved), so schema changes to `orders` are additive/renaming only, no backfill.
- All new async tests use `pytest-asyncio` in `asyncio_mode = auto` (no per-test `@pytest.mark.asyncio` needed).

All file paths below are relative to `vpn-service/` (the repo root as pushed to `rapnikoboup2011-cpu/valerii28-vpn-service`, branch `claude/ip-list-telegram-vpn-etg84o`).

---

### Task 1: Test tooling + `Tariff.price_stars`

**Files:**
- Create: `requirements-dev.txt`
- Create: `pytest.ini`
- Create: `tests/__init__.py`
- Modify: `bot/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Tariff(code: str, title: str, months: int, price_stars: int)`; `Config.tariffs: list[Tariff]` built from `PRICE_1_MONTH_STARS` (default `"80"`), `PRICE_3_MONTHS_STARS` (default `"210"`), `PRICE_12_MONTHS_STARS` (default `"680"`); `Config.tariff_by_code(code: str) -> Tariff | None` (unchanged signature). `Config` no longer has `yookassa_shop_id`, `yookassa_secret_key`, `webhook_host`, `webhook_port`.

- [ ] **Step 1: Create `requirements-dev.txt`**

```
pytest==8.3.4
pytest-asyncio==0.24.0
```

- [ ] **Step 2: Create `pytest.ini`**

```ini
[pytest]
asyncio_mode = auto
```

- [ ] **Step 3: Create `tests/__init__.py`** (empty file)

- [ ] **Step 4: Install dev dependencies**

Run: `cd vpn-service && pip install -r requirements.txt -r requirements-dev.txt`
Expected: installs succeed, no errors.

- [ ] **Step 5: Write the failing test**

```python
# tests/test_config.py
def test_tariffs_load_stars_prices_from_env(monkeypatch):
    monkeypatch.setenv("PRICE_1_MONTH_STARS", "80")
    monkeypatch.setenv("PRICE_3_MONTHS_STARS", "210")
    monkeypatch.setenv("PRICE_12_MONTHS_STARS", "680")

    from bot.config import Config

    cfg = Config()

    assert cfg.tariff_by_code("1m").price_stars == 80
    assert cfg.tariff_by_code("3m").price_stars == 210
    assert cfg.tariff_by_code("12m").price_stars == 680
    assert cfg.tariff_by_code("nope") is None


def test_tariffs_default_to_spec_prices_without_env(monkeypatch):
    monkeypatch.delenv("PRICE_1_MONTH_STARS", raising=False)
    monkeypatch.delenv("PRICE_3_MONTHS_STARS", raising=False)
    monkeypatch.delenv("PRICE_12_MONTHS_STARS", raising=False)

    from bot.config import Config

    cfg = Config()

    assert cfg.tariff_by_code("1m").price_stars == 80
    assert cfg.tariff_by_code("3m").price_stars == 210
    assert cfg.tariff_by_code("12m").price_stars == 680
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd vpn-service && pytest tests/test_config.py -v`
Expected: FAIL — `AttributeError: 'Tariff' object has no attribute 'price_stars'` (current field is `price_rub`).

- [ ] **Step 7: Update `bot/config.py`**

Replace the full file contents with:

```python
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Tariff:
    code: str
    title: str
    months: int
    price_stars: int


@dataclass
class Config:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    admin_telegram_id: int = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))

    remnawave_base_url: str = os.getenv("REMNAWAVE_BASE_URL", "")
    remnawave_api_token: str = os.getenv("REMNAWAVE_API_TOKEN", "")

    database_path: str = os.getenv("DATABASE_PATH", "./vpn_bot.sqlite3")

    tariffs: list[Tariff] = field(
        default_factory=lambda: [
            Tariff("1m", "1 месяц", 1, int(os.getenv("PRICE_1_MONTH_STARS", "80"))),
            Tariff("3m", "3 месяца", 3, int(os.getenv("PRICE_3_MONTHS_STARS", "210"))),
            Tariff("12m", "12 месяцев", 12, int(os.getenv("PRICE_12_MONTHS_STARS", "680"))),
        ]
    )

    def tariff_by_code(self, code: str) -> Tariff | None:
        return next((t for t in self.tariffs if t.code == code), None)


config = Config()
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd vpn-service && pytest tests/test_config.py -v`
Expected: PASS (2 tests).

- [ ] **Step 9: Commit**

```bash
cd vpn-service
git add requirements-dev.txt pytest.ini tests/__init__.py tests/test_config.py bot/config.py
git commit -m "feat: switch tariff pricing to Telegram Stars"
```

---

### Task 2: `orders` schema + `db.get_order`/`db.mark_order_paid`

**Files:**
- Create: `tests/conftest.py`
- Modify: `bot/db/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `bot.config.config.database_path` (Task 1, unchanged attribute name).
- Produces: `db.create_order(telegram_id: int, tariff_code: str, months: int, amount_stars: int) -> str`; `db.get_order(order_id: str) -> aiosqlite.Row | None`; `db.mark_order_paid(order_id: str, telegram_payment_charge_id: str) -> None`. Removes `db.attach_yookassa_payment` and `db.get_order_by_yookassa_payment`. `orders` table columns: `amount_stars` (was `amount_rub`), `telegram_payment_charge_id` (was `yookassa_payment_id`).

- [ ] **Step 1: Create `tests/conftest.py`**

```python
import os
import tempfile

import pytest

from bot.config import config
from bot.db.db import init_db


@pytest.fixture
async def temp_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    monkeypatch.setattr(config, "database_path", path)
    await init_db()
    yield path
    os.remove(path)
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_db.py
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd vpn-service && pytest tests/test_db.py -v`
Expected: FAIL — `TypeError: create_order() got an unexpected keyword argument 'amount_stars'` (current param is `amount_rub`), and `AttributeError: module 'bot.db.db' has no attribute 'get_order'`.

- [ ] **Step 4: Update `bot/db/db.py`**

Replace the full file contents with:

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd vpn-service && pytest tests/test_db.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
cd vpn-service
git add tests/conftest.py tests/test_db.py bot/db/db.py
git commit -m "feat: rework orders schema for Telegram Stars payments"
```

---

### Task 3: `on_buy` sends a Stars invoice

**Files:**
- Modify: `bot/handlers/user.py` (imports + `_tariffs_keyboard` + `on_buy` only — `pre_checkout_query`/`successful_payment` handlers come in Tasks 4–5)
- Test: `tests/test_handlers_buy.py`

**Interfaces:**
- Consumes: `db.create_order(...)` (Task 2); `config.tariff_by_code(code) -> Tariff | None`, `Tariff.price_stars` (Task 1).
- Produces: `on_buy(callback: CallbackQuery) -> None` (same signature as before) — now calls `callback.message.answer_invoice(title, description, payload, provider_token, currency, prices)` instead of creating a YooKassa payment.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_handlers_buy.py
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.config import config
from bot.handlers.user import on_buy


async def test_on_buy_sends_stars_invoice(monkeypatch):
    created_order_id = "order-xyz"
    monkeypatch.setattr(
        "bot.handlers.user.db.create_order", AsyncMock(return_value=created_order_id)
    )

    callback = SimpleNamespace(
        data="buy:1m",
        from_user=SimpleNamespace(id=555),
        message=SimpleNamespace(answer_invoice=AsyncMock()),
        answer=AsyncMock(),
    )

    await on_buy(callback)

    callback.message.answer_invoice.assert_awaited_once()
    _, kwargs = callback.message.answer_invoice.call_args
    assert kwargs["currency"] == "XTR"
    assert kwargs["provider_token"] == ""
    assert kwargs["payload"] == created_order_id
    assert kwargs["prices"][0].amount == config.tariff_by_code("1m").price_stars
    callback.answer.assert_awaited_once()


async def test_on_buy_rejects_unknown_tariff(monkeypatch):
    create_order = AsyncMock()
    monkeypatch.setattr("bot.handlers.user.db.create_order", create_order)

    callback = SimpleNamespace(
        data="buy:doesnotexist",
        from_user=SimpleNamespace(id=555),
        message=SimpleNamespace(answer_invoice=AsyncMock()),
        answer=AsyncMock(),
    )

    await on_buy(callback)

    create_order.assert_not_awaited()
    callback.answer.assert_awaited_once_with("Тариф не найден", show_alert=True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd vpn-service && pytest tests/test_handlers_buy.py -v`
Expected: FAIL — `AttributeError` (`SimpleNamespace` has no `answer_invoice` being called, because current `on_buy` calls `yookassa_client.create_payment` and never touches `answer_invoice`), or `ModuleNotFoundError` if `yookassa_client` import breaks first.

- [ ] **Step 3: Update `bot/handlers/user.py` imports and `_tariffs_keyboard`/`on_buy`**

Replace the top of the file (imports through the end of `on_buy`) with:

```python
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
```

Leave the rest of the file (`deliver_subscription`) untouched for now — Tasks 4 and 5 add the two new handlers between `on_buy` and `deliver_subscription`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd vpn-service && pytest tests/test_handlers_buy.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
cd vpn-service
git add bot/handlers/user.py tests/test_handlers_buy.py
git commit -m "feat: send Telegram Stars invoice on tariff purchase"
```

---

### Task 4: `pre_checkout_query` handler

**Files:**
- Modify: `bot/handlers/user.py` (insert new handler after `on_buy`, before `deliver_subscription`)
- Test: `tests/test_handlers_pre_checkout.py`

**Interfaces:**
- Consumes: `db.get_order(order_id) -> aiosqlite.Row | None` (Task 2).
- Produces: `on_pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None`, registered via `@router.pre_checkout_query()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_handlers_pre_checkout.py
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.handlers.user import on_pre_checkout


async def test_pre_checkout_accepts_pending_order(monkeypatch):
    order = {"status": "pending"}
    monkeypatch.setattr("bot.handlers.user.db.get_order", AsyncMock(return_value=order))

    query = SimpleNamespace(invoice_payload="order-123", answer=AsyncMock())

    await on_pre_checkout(query)

    query.answer.assert_awaited_once_with(ok=True)


async def test_pre_checkout_rejects_missing_order(monkeypatch):
    monkeypatch.setattr("bot.handlers.user.db.get_order", AsyncMock(return_value=None))

    query = SimpleNamespace(invoice_payload="order-404", answer=AsyncMock())

    await on_pre_checkout(query)

    _, kwargs = query.answer.call_args
    assert kwargs["ok"] is False


async def test_pre_checkout_rejects_already_paid_order(monkeypatch):
    order = {"status": "paid"}
    monkeypatch.setattr("bot.handlers.user.db.get_order", AsyncMock(return_value=order))

    query = SimpleNamespace(invoice_payload="order-123", answer=AsyncMock())

    await on_pre_checkout(query)

    _, kwargs = query.answer.call_args
    assert kwargs["ok"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd vpn-service && pytest tests/test_handlers_pre_checkout.py -v`
Expected: FAIL — `ImportError: cannot import name 'on_pre_checkout' from 'bot.handlers.user'`.

- [ ] **Step 3: Insert the handler into `bot/handlers/user.py`**

Insert immediately after the `on_buy` function (before `deliver_subscription`):

```python
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
    await pre_checkout_query.answer(ok=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd vpn-service && pytest tests/test_handlers_pre_checkout.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
cd vpn-service
git add bot/handlers/user.py tests/test_handlers_pre_checkout.py
git commit -m "feat: validate orders in pre_checkout_query handler"
```

---

### Task 5: `successful_payment` handler

**Files:**
- Modify: `bot/handlers/user.py` (insert new handler after `on_pre_checkout`, before `deliver_subscription`)
- Test: `tests/test_handlers_successful_payment.py`

**Interfaces:**
- Consumes: `db.get_order(order_id)`, `db.mark_order_paid(order_id, charge_id)` (Task 2); `deliver_subscription(telegram_id, months) -> str` (existing, unchanged); `config.admin_telegram_id` (Task 1).
- Produces: `on_successful_payment(message: Message) -> None`, registered via `@router.message(F.successful_payment)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_handlers_successful_payment.py
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.handlers.user import on_successful_payment


def _make_message(order_id: str, charge_id: str = "charge_1"):
    successful_payment = SimpleNamespace(invoice_payload=order_id, telegram_payment_charge_id=charge_id)
    bot = SimpleNamespace(send_message=AsyncMock())
    return SimpleNamespace(successful_payment=successful_payment, bot=bot, answer=AsyncMock())


async def test_successful_payment_delivers_subscription(monkeypatch):
    order = {"status": "pending", "telegram_id": 111, "months": 1}
    monkeypatch.setattr("bot.handlers.user.db.get_order", AsyncMock(return_value=order))
    mark_paid = AsyncMock()
    monkeypatch.setattr("bot.handlers.user.db.mark_order_paid", mark_paid)
    monkeypatch.setattr(
        "bot.handlers.user.deliver_subscription", AsyncMock(return_value="https://sub.example/abc")
    )

    message = _make_message("order-1")

    await on_successful_payment(message)

    mark_paid.assert_awaited_once_with("order-1", "charge_1")
    message.answer.assert_awaited_once()
    assert "https://sub.example/abc" in message.answer.call_args.args[0]


async def test_successful_payment_ignores_already_paid_order(monkeypatch):
    order = {"status": "paid", "telegram_id": 111, "months": 1}
    monkeypatch.setattr("bot.handlers.user.db.get_order", AsyncMock(return_value=order))
    mark_paid = AsyncMock()
    monkeypatch.setattr("bot.handlers.user.db.mark_order_paid", mark_paid)

    message = _make_message("order-1")

    await on_successful_payment(message)

    mark_paid.assert_not_awaited()
    message.answer.assert_not_awaited()


async def test_successful_payment_notifies_admin_on_delivery_failure(monkeypatch):
    order = {"status": "pending", "telegram_id": 111, "months": 1}
    monkeypatch.setattr("bot.handlers.user.db.get_order", AsyncMock(return_value=order))
    monkeypatch.setattr("bot.handlers.user.db.mark_order_paid", AsyncMock())
    monkeypatch.setattr(
        "bot.handlers.user.deliver_subscription",
        AsyncMock(side_effect=RuntimeError("remnawave down")),
    )
    monkeypatch.setattr("bot.handlers.user.config.admin_telegram_id", 999)

    message = _make_message("order-1")

    await on_successful_payment(message)

    message.bot.send_message.assert_awaited_once()
    args, _ = message.bot.send_message.call_args
    assert args[0] == 999
    assert "order-1" in args[1]
    message.answer.assert_not_awaited()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd vpn-service && pytest tests/test_handlers_successful_payment.py -v`
Expected: FAIL — `ImportError: cannot import name 'on_successful_payment' from 'bot.handlers.user'`.

- [ ] **Step 3: Insert the handler into `bot/handlers/user.py`**

Insert immediately after `on_pre_checkout` (before `deliver_subscription`):

```python
@router.message(F.successful_payment)
async def on_successful_payment(message: Message) -> None:
    payment = message.successful_payment
    order_id = payment.invoice_payload
    order = await db.get_order(order_id)
    if order is None or order["status"] == "paid":
        return

    await db.mark_order_paid(order_id, payment.telegram_payment_charge_id)

    try:
        subscription_url = await deliver_subscription(order["telegram_id"], order["months"])
    except Exception as exc:  # noqa: BLE001 - payment already captured, admin must be told regardless of cause
        await message.bot.send_message(
            config.admin_telegram_id,
            f"⚠️ Оплата прошла (order_id={order_id}), но выдача подписки упала: {exc}",
        )
        return

    await message.answer(
        f"Оплата получена! Ваша ссылка подписки:\n{subscription_url}\n\n"
        "Вставьте её в приложение (Happ, v2rayNG и т.п.) в качестве подписки."
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd vpn-service && pytest tests/test_handlers_successful_payment.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
cd vpn-service
git add bot/handlers/user.py tests/test_handlers_successful_payment.py
git commit -m "feat: deliver subscription on successful Stars payment"
```

---

### Task 6: Remove the YooKassa client and webhook server

**Files:**
- Delete: `bot/services/yookassa_client.py`
- Delete: `bot/webhook_server.py`
- Delete: `deploy/nginx-vpn-bot.conf`
- Modify: `bot/main.py`

**Interfaces:**
- Consumes: `bot.handlers.user.router` (unchanged), `bot.db.db.init_db` (unchanged), `bot.config.config` (Task 1).
- Produces: `main() -> None` with no web server — just DB init, bot/dispatcher setup, and polling.

- [ ] **Step 1: Delete the obsolete files**

```bash
cd vpn-service
git rm bot/services/yookassa_client.py bot/webhook_server.py deploy/nginx-vpn-bot.conf
```

- [ ] **Step 2: Replace `bot/main.py`**

```python
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import config
from bot.db.db import init_db
from bot.handlers import user

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    if not config.bot_token:
        raise RuntimeError("BOT_TOKEN is not set. Fill it in .env")

    await init_db()

    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(user.router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: Verify no leftover imports of the deleted modules**

Run: `cd vpn-service && grep -rn "yookassa_client\|webhook_server" bot/`
Expected: no output (empty).

- [ ] **Step 4: Verify the package still imports cleanly**

Run: `cd vpn-service && python -c "import bot.main"`
Expected: no output, exit code 0 (import succeeds — this doesn't run `main()`, just checks there are no import-time errors like a dangling `from bot.webhook_server import create_webhook_app`).

- [ ] **Step 5: Run the full test suite**

Run: `cd vpn-service && pytest -v`
Expected: PASS (all tests from Tasks 1–5, no collection errors).

- [ ] **Step 6: Commit**

```bash
cd vpn-service
git add bot/main.py
git commit -m "refactor: drop FastAPI/uvicorn webhook server, poll only"
```

---

### Task 7: Update dependencies and `docker-compose.yml`

**Files:**
- Modify: `requirements.txt`
- Modify: `docker-compose.yml`

**Interfaces:**
- Consumes: none (dependency/deploy config only).
- Produces: `requirements.txt` without `yookassa`/`fastapi`/`uvicorn`; `docker-compose.yml` without a `ports` mapping.

- [ ] **Step 1: Replace `requirements.txt`**

```
aiogram==3.15.0
httpx==0.27.2
aiosqlite==0.20.0
python-dotenv==1.0.1
```

- [ ] **Step 2: Replace `docker-compose.yml`**

```yaml
services:
    vpn-bot:
        build: .
        container_name: vpn-bot
        restart: always
        env_file:
            - .env
        volumes:
            - vpn-bot-data:/app/data

volumes:
    vpn-bot-data:
        driver: local
```

- [ ] **Step 3: Verify docker-compose config parses**

Run: `cd vpn-service && docker compose config -q`
Expected: exit code 0, no errors. (If `docker` isn't available in this environment, skip this step and note it in the task handoff — YAML syntax was already hand-verified against the block above.)

- [ ] **Step 4: Reinstall from the trimmed requirements to confirm nothing still imports the removed packages**

Run: `cd vpn-service && pip install -r requirements.txt -r requirements-dev.txt && pytest -v`
Expected: PASS (all tests), confirming the test suite doesn't secretly depend on `fastapi`/`uvicorn`/`yookassa`.

- [ ] **Step 5: Commit**

```bash
cd vpn-service
git add requirements.txt docker-compose.yml
git commit -m "chore: drop yookassa/fastapi/uvicorn dependencies and webhook port"
```

---

### Task 8: Update `.env.example` and `README.md`

**Files:**
- Modify: `.env.example`
- Modify: `README.md`

**Interfaces:**
- Consumes: env var names from Task 1 (`PRICE_1_MONTH_STARS`, `PRICE_3_MONTHS_STARS`, `PRICE_12_MONTHS_STARS`) and existing `BOT_TOKEN`, `ADMIN_TELEGRAM_ID`, `REMNAWAVE_BASE_URL`, `REMNAWAVE_API_TOKEN`, `DATABASE_PATH`.
- Produces: none consumed by later tasks — this is the last content task.

- [ ] **Step 1: Replace `.env.example`**

```
# --- Telegram ---
BOT_TOKEN=change_me
ADMIN_TELEGRAM_ID=112243659

# --- Remnawave panel ---
REMNAWAVE_BASE_URL=https://panel.valerii28.ru
REMNAWAVE_API_TOKEN=change_me

# --- Tariffs (price in Telegram Stars) ---
PRICE_1_MONTH_STARS=80
PRICE_3_MONTHS_STARS=210
PRICE_12_MONTHS_STARS=680

# --- Database ---
# Use /app/data/vpn_bot.sqlite3 when running via docker-compose.yml (matches the mounted volume)
DATABASE_PATH=./vpn_bot.sqlite3
```

- [ ] **Step 2: Replace `README.md`**

```markdown
# VPN Service Bot

Telegram-бот для продажи подписок на VPN (панель Remnawave) с оплатой через Telegram Stars.

## Как это работает

1. Пользователь пишет `/start`, выбирает тариф (1/3/12 месяцев).
2. Бот присылает нативный Telegram-инвойс в звёздах (⭐, валюта `XTR`).
3. Telegram присылает боту `pre_checkout_query` — бот подтверждает, что заказ существует и ещё не оплачен.
4. После оплаты Telegram присылает боту `successful_payment` — бот создаёт/продлевает пользователя в Remnawave и присылает клиенту ссылку подписки. Никакого внешнего вебхука или публичного порта не требуется — всё приходит через long-polling соединение бота.

## Настройка

1. Скопируйте `.env.example` в `.env` и заполните:
   - `BOT_TOKEN`, `ADMIN_TELEGRAM_ID` — от @BotFather / @userinfobot
   - `REMNAWAVE_BASE_URL`, `REMNAWAVE_API_TOKEN` — домен панели и API-токен (создаётся в самой панели Remnawave)
   - Цены тарифов в звёздах при необходимости

2. Запуск через Docker:
   ```bash
   docker compose up -d --build
   ```

## Важно: сверить Remnawave API

`bot/services/remnawave_client.py` написан по документированной структуре API Remnawave,
но не проверен на реальной панели. Как только панель поднимется:
1. Включите `IS_DOCS_ENABLED=true` в `.env` панели
2. Откройте `https://<panel-domain>/docs` (Swagger)
3. Сверьте пути/поля в `remnawave_client.py` с реальным API, поправьте при расхождениях

## Структура

```
bot/
  config.py           — тарифы (в звёздах) и переменные окружения
  db/db.py             — sqlite: пользователи и заказы
  services/
    remnawave_client.py — создание/продление пользователей VPN
  handlers/user.py     — /start, выбор тарифа, инвойс, pre_checkout_query, successful_payment
  main.py              — точка входа (long-polling бота)
```

## Тесты

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -v
```
```

- [ ] **Step 3: Commit**

```bash
cd vpn-service
git add .env.example README.md
git commit -m "docs: document Telegram Stars setup and drop webhook instructions"
```

---

### Task 9: Final verification

**Files:** none (verification only).

**Interfaces:** none — this task only checks the work of Tasks 1–8.

- [ ] **Step 1: Confirm no YooKassa/webhook references remain outside historical docs**

Run: `cd vpn-service && grep -rli "yookassa\|webhook" --include="*.py" --include="*.txt" --include="*.yml" --include="*.example" --include="Dockerfile" --include="*.conf" --include="*.md" . | grep -v docs/superpowers/specs`
Expected: no output (empty). (The design spec under `docs/superpowers/specs/` is allowed to mention YooKassa/webhooks as historical context — it's excluded from this check on purpose.)

- [ ] **Step 2: Run the full test suite one more time**

Run: `cd vpn-service && pytest -v`
Expected: PASS, 13 tests total (2 config + 3 db + 2 buy + 3 pre_checkout + 3 successful_payment — recount against actual test files if any were added/removed during implementation).

- [ ] **Step 3: Confirm the bot process still boots far enough to reach polling**

Run: `cd vpn-service && BOT_TOKEN=dummy_token_for_import_check python -c "
import asyncio
from bot.main import main

async def run():
    try:
        await asyncio.wait_for(main(), timeout=2)
    except asyncio.TimeoutError:
        print('OK: reached polling loop without crashing (timed out waiting, as expected)')
    except Exception as e:
        print(f'Reached main() and failed at runtime with {type(e).__name__}: {e}')

asyncio.run(run())
"`
Expected: one of two acceptable outcomes — either the timeout-OK line, or a runtime failure naming a Telegram-auth-related exception type (e.g. `TelegramUnauthorizedError`) raised once polling actually tries to talk to Telegram with the dummy token. Both mean `init_db()`, config loading, and `Bot`/`Dispatcher` construction all succeeded. An import error, `AttributeError`, or a `RuntimeError` about `BOT_TOKEN` being unset are NOT acceptable — those mean something upstream of polling (config, db init) is still broken; read the traceback.

- [ ] **Step 4: Note the manual end-to-end check for the human operator**

No command to run here — record in the handoff to the user that a real Stars payment (via BotFather's test payment mode, or real Stars in production) must be exercised manually against the deployed bot, since it requires actual Telegram infrastructure this plan's tests can't reach.

- [ ] **Step 5: Push the branch**

Run: `cd vpn-service && git push origin claude/ip-list-telegram-vpn-etg84o`
Expected: push succeeds, branch updated on `rapnikoboup2011-cpu/valerii28-vpn-service`.
