from pydantic import Field, BaseModel

from pydantic_settings import BaseSettings
from typing import Optional
from datetime import time


class OkxSettings(BaseModel):
    """OKX API settings."""
    api_key: str
    api_secret: str
    api_passphrase: str
    subaccount_name: str


class TelegramSettings(BaseModel):
    """Telegram bot settings."""
    bot_token: str
    user_id: int


class DCASettings(BaseModel):
    """DCA trading settings."""
    amount_usd: float
    time_utc: time
    max_transaction_limit: float


class DatabaseSettings(BaseModel):
    """Database settings."""
    uri: str


class AppSettings(BaseSettings):
    """Main application settings."""
    okx: OkxSettings
    telegram: TelegramSettings
    dca: DCASettings
    db: DatabaseSettings
    dry_run: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_nested_delimiter = "__"


def get_settings() -> AppSettings:
    """Get the application settings from environment variables."""
    return AppSettings(
        okx=OkxSettings(
            api_key=get_env("OKX_API_KEY"),
            api_secret=get_env("OKX_API_SECRET"),
            api_passphrase=get_env("OKX_API_PASSPHRASE"),
            subaccount_name=get_env("OKX_SUBACCOUNT_NAME"),
        ),
        telegram=TelegramSettings(
            bot_token=get_env("TELEGRAM_BOT_TOKEN"),
            user_id=int(get_env("TELEGRAM_USER_ID")),
        ),
        dca=DCASettings(
            amount_usd=float(get_env("DCA_AMOUNT_USD")),
            time_utc=parse_time(get_env("DCA_TIME_UTC")),
            max_transaction_limit=float(get_env("MAX_TRANSACTION_LIMIT")),
        ),
        db=DatabaseSettings(
            uri=get_env("MONGODB_URI"),
        ),
        dry_run=get_env("DRY_RUN", "false").lower() == "true",
    )


def get_env(name: str, default: Optional[str] = None) -> str:
    """Get environment variable or raise an error."""
    import os
    value = os.environ.get(name, default)
    if value is None:
        raise ValueError(f"Environment variable {name} not set")
    return value


def parse_time(time_str: str) -> time:
    """Parse time string in HH:MM format."""
    hours, minutes = map(int, time_str.split(":"))
    return time(hour=hours, minute=minutes)


# Singleton instance
settings = get_settings()
