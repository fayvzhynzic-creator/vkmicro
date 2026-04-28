from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    vk_group_token: str = os.getenv("VK_GROUP_TOKEN", "")
    vk_confirmation_token: str = os.getenv("VK_CONFIRMATION_TOKEN", "")
    vk_secret: str = os.getenv("VK_SECRET", "")
    vk_group_id: int | None = int(os.getenv("VK_GROUP_ID")) if os.getenv("VK_GROUP_ID", "").isdigit() else None
    vk_api_version: str = os.getenv("VK_API_VERSION", "5.199")

    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./bot.sqlite3")
    port: int = int(os.getenv("PORT", "10000"))
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "")

    bot_name: str = os.getenv("BOT_NAME", "Мелкодел")
    default_timezone: str = os.getenv("DEFAULT_TIMEZONE", "Europe/Moscow")
    default_daily_time: str = os.getenv("DEFAULT_DAILY_TIME", "09:00")
    default_reminder_time: str = os.getenv("DEFAULT_REMINDER_TIME", "20:00")
    enable_internal_scheduler: bool = _get_bool("ENABLE_INTERNAL_SCHEDULER", True)

    admin_token: str = os.getenv("ADMIN_TOKEN", "")
    cron_secret: str = os.getenv("CRON_SECRET", "")

    def sqlalchemy_url(self) -> str:
        # Some providers still expose postgres:// URLs; SQLAlchemy expects postgresql://.
        if self.database_url.startswith("postgres://"):
            return "postgresql://" + self.database_url[len("postgres://") :]
        return self.database_url


settings = Settings()
