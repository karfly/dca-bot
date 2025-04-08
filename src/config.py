from pydantic import Field, BaseModel, ConfigDict
import os
from pydantic_settings import BaseSettings
from typing import Optional
from datetime import time
from pydantic import field_validator


class OkxSettings(BaseModel):
    """OKX API settings."""
    api_key: str
    api_secret: str
    api_passphrase: str
    subaccount_name: str


class ExchangeSettings(BaseModel):
    """Exchange settings."""
    id: str = "okx"  # Default to OKX

    @field_validator("id")
    @classmethod
    def validate_exchange_id(cls, v):
        # Currently only OKX is fully tested and supported
        supported_exchanges = ["okx", "binance", "coinbase", "kucoin", "bybit"]
        if v.lower() not in supported_exchanges:
            raise ValueError(f"Exchange {v} is not supported yet. Supported exchanges: {', '.join(supported_exchanges)}")
        return v.lower()


class TelegramSettings(BaseModel):
    """Telegram bot settings."""
    bot_token: str
    user_id: int
    notification_sound: bool = True


class DCASettings(BaseModel):
    """DCA trading settings."""
    amount_usd: float
    time_utc: time
    max_transaction_limit: float
    period: str = "1_day"  # "1_day", "1_minute", or "1_hour"

    @field_validator("period")
    @classmethod
    def validate_period(cls, v):
        if v not in ["1_day", "1_minute", "1_hour"]:
            raise ValueError('period must be either "1_day", "1_minute", or "1_hour"')
        return v


class PortfolioSettings(BaseModel):
    """Portfolio settings for existing holdings."""
    initial_btc_amount: float = 0.0
    initial_avg_price_usd: float = 0.0


class DatabaseSettings(BaseModel):
    """Database settings."""
    uri: str


class AppSettings(BaseSettings):
    """Main application settings."""
    okx: OkxSettings
    exchange: ExchangeSettings
    telegram: TelegramSettings
    dca: DCASettings
    db: DatabaseSettings
    portfolio: PortfolioSettings
    dry_run: bool = False
    log_level: str = "INFO"
    run_immediately: bool = False

    model_config = ConfigDict(
        env_file = ".env",
        env_file_encoding = "utf-8",
        env_file_nested_delimiter = "__",
        extra = "allow"
    )


def get_settings() -> AppSettings:
    """Get the application settings from environment variables."""
    return AppSettings(
        okx=OkxSettings(
            api_key=get_env("OKX_API_KEY"),
            api_secret=get_env("OKX_API_SECRET"),
            api_passphrase=get_env("OKX_API_PASSPHRASE"),
            subaccount_name=get_env("OKX_SUBACCOUNT_NAME"),
        ),
        exchange=ExchangeSettings(
            id=get_env("EXCHANGE_ID", "okx"),
        ),
        telegram=TelegramSettings(
            bot_token=get_env("TELEGRAM_BOT_TOKEN"),
            user_id=int(get_env("TELEGRAM_USER_ID")),
            notification_sound=get_env("TELEGRAM_NOTIFICATION_SOUND", "true").lower() == "true",
        ),
        dca=DCASettings(
            amount_usd=float(get_env("DCA_AMOUNT_USD")),
            time_utc=parse_time(get_env("DCA_TIME_UTC")),
            max_transaction_limit=float(get_env("MAX_TRANSACTION_LIMIT")),
            period=get_env("DCA_PERIOD", "1_day"),
        ),
        portfolio=PortfolioSettings(
            initial_btc_amount=float(get_env("PORTFOLIO_INITIAL_BTC", "0.0")),
            initial_avg_price_usd=float(get_env("PORTFOLIO_INITIAL_AVG_PRICE", "0.0")),
        ),
        db=DatabaseSettings(
            uri=get_env("MONGODB_URI"),
        ),
        dry_run=get_env("DRY_RUN", "false").lower() == "true",
        log_level=get_env("LOG_LEVEL", "INFO"),
        run_immediately=get_env("RUN_IMMEDIATELY", "false").lower() == "true",
    )


def get_env(name: str, default: Optional[str] = None) -> str:
    """Get environment variable or raise an error."""
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
