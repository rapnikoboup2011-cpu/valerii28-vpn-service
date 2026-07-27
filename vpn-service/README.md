# VPN Service Bot

Telegram-бот для продажи подписок на VPN (панель Remnawave) с оплатой через ЮKassa (СБП/карты).

## Как это работает

1. Пользователь пишет `/start`, выбирает тариф (1/3/12 месяцев).
2. Бот создаёт платёж в ЮKassa и присылает ссылку на оплату.
3. ЮKassa шлёт уведомление на `/yookassa/webhook`.
4. Бот сверяет статус платежа напрямую через API ЮKassa (не доверяет телу вебхука напрямую), создаёт/продлевает пользователя в Remnawave и присылает клиенту ссылку подписки.

## Настройка

1. Скопируйте `.env.example` в `.env` и заполните:
   - `BOT_TOKEN`, `ADMIN_TELEGRAM_ID` — от @BotFather / @userinfobot
   - `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY` — из личного кабинета ЮKassa
   - `REMNAWAVE_BASE_URL`, `REMNAWAVE_API_TOKEN` — домен панели и API-токен (создаётся в самой панели Remnawave)
   - Цены тарифов при необходимости

2. Запуск через Docker:
   ```bash
   docker compose up -d --build
   ```

3. Настройте у ЮKassa URL для уведомлений: `https://<ваш-домен>/yookassa/webhook`
   (нужно пробросить через nginx на 127.0.0.1:8080, см. `deploy/nginx-vpn-bot.conf`)

## Важно: сверить Remnawave API

`bot/services/remnawave_client.py` написан по документированной структуре API Remnawave,
но не проверен на реальной панели. Как только панель поднимется:
1. Включите `IS_DOCS_ENABLED=true` в `.env` панели
2. Откройте `https://<panel-domain>/docs` (Swagger)
3. Сверьте пути/поля в `remnawave_client.py` с реальным API, поправьте при расхождениях

## Структура

```
bot/
  config.py           — тарифы и переменные окружения
  db/db.py             — sqlite: пользователи и заказы
  services/
    yookassa_client.py  — создание и проверка платежей
    remnawave_client.py — создание/продление пользователей VPN
  handlers/user.py     — /start, выбор тарифа, оплата
  webhook_server.py    — приём уведомлений от ЮKassa
  main.py              — точка входа (polling бота + веб-сервер)
```
