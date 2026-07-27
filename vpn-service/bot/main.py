import asyncio
import logging

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import config
from bot.db.db import init_db
from bot.handlers import user
from bot.webhook_server import create_webhook_app

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    if not config.bot_token:
        raise RuntimeError("BOT_TOKEN is not set. Fill it in .env")

    await init_db()

    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(user.router)

    app = create_webhook_app(bot)
    server_config = uvicorn.Config(
        app, host=config.webhook_host, port=config.webhook_port, log_level="info", loop="asyncio"
    )
    server = uvicorn.Server(server_config)
    asyncio.create_task(server.serve())

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
