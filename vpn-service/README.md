# VPN Service Bot

Telegram-бот для продажи подписок на VPN (панель Remnawave) с оплатой через Telegram Stars.

## Как это работает

1. Пользователь пишет `/start`, выбирает тариф (1/3/12 месяцев).
2. Бот присылает нативный Telegram-инвойс в звёздах (⭐, валюта `XTR`).
3. Telegram присылает боту `pre_checkout_query` — бот подтверждает, что заказ существует и ещё не оплачен.
4. После оплаты Telegram присылает боту `successful_payment` — бот создаёт/продлевает пользователя в Remnawave и присылает клиенту ссылку подписки. Никакого внешнего вебхука или публичного порта не требуется — всё приходит через long-polling соединение бота.
5. Подписчики с активной подпиской могут написать `/song <описание песни>` — бот сгенерирует песню через self-hosted [suno-api](https://github.com/gcui-art/suno-api) и пришлёт готовые аудио прямо в чат. Лимита на количество генераций на пользователя нет — все подписчики используют один общий аккаунт Suno/2Captcha, так что при активном использовании баланс может закончиться быстрее, чем ожидается.

## Настройка

1. Скопируйте `.env.example` в `.env` и заполните:
   - `BOT_TOKEN`, `ADMIN_TELEGRAM_ID` — от @BotFather / @userinfobot
   - `REMNAWAVE_BASE_URL`, `REMNAWAVE_API_TOKEN` — домен панели и API-токен (создаётся в самой панели Remnawave)
   - `SUNO_API_BASE_URL` — адрес вашего развёрнутого suno-api (для команды `/song`)
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
    remnawave_client.py — создание/продление пользователей VPN, проверка активной подписки
    suno_client.py       — генерация песни и поллинг готовых клипов через suno-api
  handlers/
    user.py              — /start, выбор тариф, инвойс, pre_checkout_query, successful_payment
    song.py               — /song, генерация песни для подписчиков
  main.py              — точка входа (long-polling бота)
```

## Тесты

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -v
```
