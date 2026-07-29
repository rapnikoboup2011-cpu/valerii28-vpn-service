from __future__ import annotations

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
    remnawave_internal_squad_uuid: str = os.getenv("REMNAWAVE_INTERNAL_SQUAD_UUID", "")

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
