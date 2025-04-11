import os
import logging
from datetime import time as dt_time, datetime
from typing import Optional, List

from pydantic import (Field, BaseModel, ConfigDict, field_validator,
                      model_validator, ValidationError)
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class OkxSettings(BaseModel):
    """OKX API settings."""
    api_key: str
    api_secret: str
    api_passphrase: str
    subaccount_name: Optional[str] = None


class ExchangeSettings(BaseModel):
    """Exchange settings."""
    id: str = "okx"

    @field_validator("id")
    @classmethod
    def validate_exchange_id(cls, v: str) -> str:
        supported_exchanges = ["okx"]
        if v.lower() not in supported_exchanges:
            logger.warning(f"Exchange '{v}' is not officially supported/tested. Using it at your own risk. Only 'okx' is fully tested.")
        return v.lower()


class TelegramSettings(BaseModel):
    """Telegram bot settings."""
    bot_token: str
    user_id: int
    notification_sound: bool = True


class DCASettings(BaseModel):
    """DCA specific settings."""
    amount_usd: float = Field(..., gt=0)
    period: str = "1_day"
    start_time_utc: Optional[dt_time] = None
    # run_immediately is no longer part of this model, handled in AppSettings

    @field_validator("period")
    @classmethod
    def validate_period(cls, v: str) -> str:
        if v not in ["1_day", "1_minute", "1_hour"]:
            raise ValueError('period must be either "1_day", "1_minute", or "1_hour"')
        return v


class PortfolioSettings(BaseModel):
    """Portfolio settings for existing holdings."""
    initial_btc_amount: float = 0.0
    initial_avg_price_usd: float = 0.0


class ReportSettings(BaseModel):
    """Report schedule settings."""
    times_utc: List[dt_time] = []
    lookback_hours: int = 12


class AppSettings(BaseSettings):
    """Main application settings, loaded via get_settings function."""
    # Nested models
    okx: OkxSettings
    exchange: ExchangeSettings
    telegram: TelegramSettings
    dca: DCASettings
    portfolio: PortfolioSettings
    report: ReportSettings

    # Direct settings
    mongo_uri: str
    send_trade_notifications: bool = False
    dry_run: bool = False
    log_level: str = "INFO"
    test_mode: bool = False
    # Derived flag, set during get_settings logic
    run_dca_immediately: bool = False

    model_config = ConfigDict(
        # BaseSettings will read .env automatically if python-dotenv is installed
        # We handle explicit loading in get_settings for clarity
        extra="ignore",
        arbitrary_types_allowed=True
    )

# --- Helper to load env var or raise ---
def _get_required_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None:
        msg = f"CRITICAL: Required environment variable '{name}' is not set."
        logger.error(msg)
        raise ValueError(msg)
    return value

# --- Settings Loading Function ---
def get_settings() -> AppSettings:
    """Load settings from environment variables, parse, validate, and return AppSettings."""
    logger.info("Loading and validating application settings...")

    # --- Parse Report Times ---
    report_times_str = os.environ.get("REPORT_TIMES_UTC", "")
    parsed_report_times = []
    if report_times_str:
        try:
            parsed_report_times = [
                dt_time.fromisoformat(t.strip())
                for t in report_times_str.split(",") if t.strip()
            ]
            logger.info(f"Parsed REPORT_TIMES_UTC: {parsed_report_times}")
        except ValueError as e:
            logger.error(f"Invalid format in REPORT_TIMES_UTC '{report_times_str}'. Error: {e}. Reports disabled.")
            parsed_report_times = [] # Reset

    # --- Parse DCA Start Time & Determine Immediate Run ---
    dca_period_val = os.environ.get("DCA_PERIOD", "1_day")
    dca_start_str = os.environ.get("DCA_START_TIME_UTC")
    parsed_dca_start_time = None
    run_immediately_flag = False

    if dca_start_str:
        if dca_start_str.lower() == "now":
            run_immediately_flag = True
            logger.info("DCA_START_TIME_UTC='now' detected.")
        else:
            try:
                parsed_dca_start_time = dt_time.fromisoformat(dca_start_str)
                logger.info(f"Parsed DCA_START_TIME_UTC: {parsed_dca_start_time.strftime('%H:%M:%S')}")
            except ValueError:
                logger.warning(f"Invalid DCA_START_TIME_UTC format: '{dca_start_str}'. Expected HH:MM or 'now'. Specific start time ignored.")
                # Keep parsed_dca_start_time as None

    # --- Validate DCA Settings Combination ---
    if dca_period_val == "1_day" and not parsed_dca_start_time:
        error_msg = "DCA_PERIOD='1_day' requires DCA_START_TIME_UTC to be set to a specific time (HH:MM format), not 'now' or empty/invalid."
        logger.error(error_msg)
        raise ValueError(error_msg)

    # --- Load Remaining Settings & Instantiate ---
    try:
        settings_data = {
            "okx": {
                "api_key": _get_required_env("OKX_API_KEY"),
                "api_secret": _get_required_env("OKX_API_SECRET"),
                "api_passphrase": _get_required_env("OKX_API_PASSPHRASE"),
                "subaccount_name": os.environ.get("OKX_SUBACCOUNT_NAME")
            },
            "exchange": {
                "id": os.environ.get("EXCHANGE_ID", "okx")
            },
            "telegram": {
                "bot_token": _get_required_env("TELEGRAM_BOT_TOKEN"),
                "user_id": int(_get_required_env("TELEGRAM_USER_ID")),
                "notification_sound": os.environ.get("TELEGRAM_NOTIFICATION_SOUND", "true").lower() == "true"
            },
            "dca": {
                "amount_usd": float(os.environ.get("DCA_AMOUNT_USD", "1.0")),
                "period": dca_period_val,
                "start_time_utc": parsed_dca_start_time
            },
            "portfolio": {
                "initial_btc_amount": float(os.environ.get("PORTFOLIO_INITIAL_BTC", "0.0")),
                "initial_avg_price_usd": float(os.environ.get("PORTFOLIO_INITIAL_AVG_PRICE", "0.0"))
            },
            "report": {
                "times_utc": parsed_report_times,
                "lookback_hours": int(os.environ.get("REPORT_LOOKBACK_HOURS", "12"))
            },
            "mongo_uri": _get_required_env("MONGODB_URI"),
            "send_trade_notifications": os.environ.get("SEND_TRADE_NOTIFICATIONS", "false").lower() == "true",
            "dry_run": os.environ.get("DRY_RUN", "false").lower() == "true",
            "log_level": os.environ.get("LOG_LEVEL", "INFO"),
            "test_mode": os.environ.get("TEST_MODE", "false").lower() == "true",
            "run_dca_immediately": run_immediately_flag
        }

        app_settings = AppSettings(**settings_data)
        logger.info("Application settings loaded and validated successfully.")
        return app_settings

    except (ValueError, ValidationError) as e:
        logger.exception(f"CRITICAL: Failed to load or validate application settings: {e}")
        raise SystemExit(f"CRITICAL: Failed to load or validate application settings: {e}")

# --- Singleton Instance ---
settings = get_settings()
