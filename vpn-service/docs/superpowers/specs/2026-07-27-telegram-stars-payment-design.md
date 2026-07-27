# Telegram Stars payment integration — design

## Context

YooKassa declined the merchant registration (VPN falls in a category their compliance
rejects). We're replacing the YooKassa payment flow with Telegram Stars (currency
`XTR`), Telegram's native in-app payment method. Stars payments don't need an external
payment provider, provider token, or a public webhook — Telegram delivers payment
events directly to the bot via `pre_checkout_query` and `successful_payment` updates
over the same connection the bot already uses for polling.

## Payment flow

1. User taps a tariff button. `on_buy` creates a `pending` order in the DB (unchanged
   behavior) and calls `answer_invoice(currency="XTR", prices=[LabeledPrice(tariff.title,
   tariff.price_stars)], payload=order_id, provider_token="")`. Stars requires an empty
   `provider_token`.
2. Telegram shows the payment sheet to the user, then sends a `pre_checkout_query`
   update to the bot. The handler looks up the order from the query's `invoice_payload`
   (= `order_id`), confirms it exists and is still `pending`, and answers `ok=True`. If
   the order is missing or already paid, it answers `ok=False` with an
   `error_message` so Telegram shows the user an error instead of charging them.
3. On success, Telegram sends a `Message` with a `successful_payment` field (a
   separate update from the checkout query). The handler is idempotent — it checks
   `order.status != 'paid'` before doing anything, in case of a duplicate update. It
   then calls `db.mark_order_paid(order_id, telegram_payment_charge_id)`, then
   `deliver_subscription(...)`, then messages the user their subscription link.
4. If `deliver_subscription` raises (e.g. Remnawave API is down) after the Stars have
   already been captured, the handler still marks the order paid (money changed hands,
   that fact must be recorded) and sends an alert to `ADMIN_TELEGRAM_ID` with the
   `order_id` and the exception, so the admin can resolve it manually. Refunds
   (`refundStarPayment`) are out of scope for this iteration.

## Pricing

Tariffs move from `price_rub` to `price_stars` (integer, Stars have no fractional
amounts). Converted at roughly 1.86–1.9 ₽/Star from the existing RUB prices:

| Tariff    | Old price (RUB) | New price (Stars) |
|-----------|-----------------|--------------------|
| 1 month   | 149 ₽            | 80 ⭐               |
| 3 months  | 399 ₽            | 210 ⭐              |
| 12 months | 1290 ₽           | 680 ⭐              |

Configurable via `PRICE_1_MONTH_STARS`, `PRICE_3_MONTHS_STARS`,
`PRICE_12_MONTHS_STARS` env vars, same pattern as today.

## Components removed

The FastAPI/uvicorn web server existed only to receive the YooKassa webhook. Stars
needs no public HTTP endpoint, so the whole stack goes:

- `bot/services/yookassa_client.py` — deleted.
- `bot/webhook_server.py` — deleted.
- `deploy/nginx-vpn-bot.conf` — deleted.
- `fastapi`, `uvicorn`, `yookassa` — removed from `requirements.txt`.
- `docker-compose.yml` — drop the `ports` mapping; the bot is a pure long-polling
  process with no listening port.
- `bot/config.py` — drop `yookassa_shop_id`, `yookassa_secret_key`, `webhook_host`,
  `webhook_port`.

## Components changed

- **`bot/config.py`** — `Tariff.price_rub` → `Tariff.price_stars: int`; tariffs built
  from the new `PRICE_*_STARS` env vars.
- **`bot/db/db.py`** — `orders` table: `yookassa_payment_id` →
  `telegram_payment_charge_id`, `amount_rub` → `amount_stars`. Replace
  `attach_yookassa_payment` + separate `mark_order_paid` with a single
  `mark_order_paid(order_id, telegram_payment_charge_id)` that sets status, charge id,
  and `paid_at` together (the old two-step dance existed only because YooKassa payment
  IDs were known before confirmation; Stars confirms and pays in the same update, so
  there's nothing to attach ahead of time). Drop `get_order_by_yookassa_payment` (no
  longer needed — the payload already carries `order_id` directly, no lookup-by-external-id
  required).
- **`bot/handlers/user.py`** — `on_buy` sends an invoice instead of creating a
  YooKassa payment; new `pre_checkout_query` and `message(F.successful_payment)`
  handlers (see Payment flow above); `_tariffs_keyboard` renders `⭐` prices.
- **`bot/main.py`** — drop the uvicorn server task and the `create_webhook_app` call;
  `main()` becomes `init_db()` → build `Bot`/`Dispatcher` → `dp.start_polling(bot)`.
- **`README.md`** — rewrite the "Как это работает" and "Настройка" sections for
  Stars; drop the nginx/webhook setup step.

## Error handling

- `pre_checkout_query`: reject (`ok=False`) with a user-facing `error_message` for a
  missing or already-paid order, rather than letting Telegram charge for something
  that can't be fulfilled.
- `successful_payment`: idempotent on order status, so a duplicate Telegram update
  never double-delivers or double-notifies. Delivery failures after payment are
  surfaced to the admin rather than silently swallowed, since there's no refund path
  yet to self-heal.

## Testing

The project has no test suite yet. This change adds focused unit tests for:

- `db.mark_order_paid` — status/charge id/paid_at get set correctly, idempotent on
  re-invocation.
- The `pre_checkout_query` handler — accepts a valid pending order, rejects a
  missing/already-paid one.
- The `successful_payment` handler — happy path calls `deliver_subscription` and
  messages the user; a `deliver_subscription` exception still marks the order paid
  and notifies the admin instead of raising.

`Bot`/`Message`/`PreCheckoutQuery` are mocked; no real Telegram calls in tests. A full
end-to-end check (real Stars test payment via BotFather's test payment mode) happens
manually after deploy — that part isn't automatable from here.

## Out of scope

- Refunds (`refundStarPayment`) — no user- or admin-facing refund flow this round.
- Migrating existing `orders` rows — there are no real orders yet (YooKassa was never
  approved), so no data migration is needed, just a schema change.
