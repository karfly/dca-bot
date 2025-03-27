import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.constants import ParseMode

from src.config import settings
from src.exchange import exchange
from src.db.mongodb import db
from src.utils.formatters import format_stats_message, format_trade_notification

logger = logging.getLogger(__name__)


class TelegramBot:
    """Telegram bot for user interaction and notifications."""

    def __init__(self, token: str, allowed_user_id: int):
        """Initialize Telegram bot."""
        # Configure application
        self.application = (
            Application.builder()
            .token(token)
            .build()
        )
        self.allowed_user_id = allowed_user_id
        self._setup_handlers()
        logger.info(f"Telegram bot initialized (user_id: {allowed_user_id})")

    def _setup_handlers(self) -> None:
        """Set up command handlers."""
        # Create a filter to only allow messages from the allowed user ID
        allowed_user_filter = filters.User(user_id=self.allowed_user_id)

        # Add handlers with the filter
        self.application.add_handler(CommandHandler("start", self.start_command, filters=allowed_user_filter))
        self.application.add_handler(CommandHandler("stats", self.stats_command, filters=allowed_user_filter))
        self.application.add_handler(CommandHandler("balance", self.balance_command, filters=allowed_user_filter))
        self.application.add_handler(MessageHandler(filters.TEXT & allowed_user_filter, self.text_message_handler))
        self.application.add_error_handler(self.error_handler)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        # Just send stats without welcome message
        await self.send_stats(update)

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /stats command."""
        await self.send_stats(update)

    async def balance_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /balance command."""
        balances = exchange.get_account_balance()
        usdt_balance, days_left = exchange.calculate_days_left()

        message = f"""
<b>💰 Account Balance</b>

• BTC: <code>{balances['BTC']:.8f}</code>
• USDT: <code>${usdt_balance:.2f}</code>
• Days Left: <code>{days_left}</code> (at ${settings.dca.amount_usd:.2f}/day)
"""

        await update.message.reply_text(
            message,
            parse_mode=ParseMode.HTML
        )

    async def text_message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming text messages."""
        # For now, just respond with help
        await update.message.reply_text(
            "Available commands:\n"
            "/start - Show your DCA statistics\n"
            "/stats - Show your DCA statistics\n"
            "/balance - Show your account balance"
        )

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors in updates."""
        logger.error(f"Update {update} caused error: {context.error}")

    async def send_stats(self, update: Update) -> None:
        """Send statistics to the user."""
        stats = db.get_trade_stats()
        current_price = exchange.get_current_price()
        usdt_balance, days_left = exchange.calculate_days_left()

        # Calculate time until next trade from the scheduler
        from src.scheduler import dca_scheduler
        next_trade_time = dca_scheduler.get_time_until_next_trade()

        message = format_stats_message(stats, current_price, usdt_balance, days_left, next_trade_time)

        await update.message.reply_text(
            message,
            parse_mode=ParseMode.HTML
        )

    async def send_trade_notification(self, trade: dict) -> None:
        """Send trade notification to the user."""
        stats = db.get_trade_stats()
        current_price = exchange.get_current_price()
        usdt_balance, days_left = exchange.calculate_days_left()

        # Calculate time until next trade from the scheduler
        from src.scheduler import dca_scheduler
        next_trade_time = dca_scheduler.get_time_until_next_trade()

        message = format_trade_notification(
            trade, stats, current_price, usdt_balance, days_left, next_trade_time
        )

        await self.application.bot.send_message(
            chat_id=self.allowed_user_id,
            text=message,
            parse_mode=ParseMode.HTML
        )

    def start(self) -> None:
        """Start the bot."""
        logger.info("Starting Telegram bot")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

    def run_webhook(self, webhook_url: str, port: int) -> None:
        """Run the bot with a webhook."""
        logger.info(f"Starting Telegram bot with webhook on port {port}")
        self.application.run_webhook(
            listen="0.0.0.0",
            port=port,
            webhook_url=webhook_url
        )


# Singleton instance
telegram_bot = TelegramBot(
    token=settings.telegram.bot_token,
    allowed_user_id=settings.telegram.user_id
)
