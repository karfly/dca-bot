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
from telegram import InputFile
from datetime import datetime, timedelta
import pytz

from src.config import settings
from src.exchange import exchange
from src.db.mongodb import db
from src.utils.formatters import format_stats_message, format_trade_notification, format_money, format_trade_summary_notification

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

        usdt_balance = balances.get('USDT', 0.0)
        remaining_duration = exchange.calculate_remaining_duration()
        remaining_value, unit, amount_per_unit, unit_name = remaining_duration
        unit_plural = unit_name + ("s" if remaining_value != 1 else "")

        message = f"""
<b>💰 Account Balance</b>

• BTC: <code>{balances['BTC']:.8f}</code>
• USDT: <code>${format_money(usdt_balance)}</code>
• {unit_plural.capitalize()} Left: <code>{remaining_value}</code> (at ${format_money(amount_per_unit)}/{unit_name})
"""

        await update.message.reply_text(
            message,
            parse_mode=ParseMode.HTML,
            disable_notification=not settings.telegram.notification_sound
        )

    async def text_message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming text messages."""
        # For now, just respond with help
        await update.message.reply_text(
            "Available commands:\n"
            "/start - Show your DCA statistics\n"
            "/balance - Show your account balance",
            disable_notification=not settings.telegram.notification_sound
        )

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors in updates."""
        logger.error(f"Update {update} caused error: {context.error}")

    async def send_stats(self, update: Update) -> None:
        """Send statistics message to the user."""
        # await update.message.reply_chat_action('upload_photo') # Removed image generation action

        try:
            stats = db.get_trade_stats()
            current_price = exchange.get_current_price()
            usdt_balance = exchange.get_account_balance().get('USDT', 0.0)
            # Get days left info instead
            days_left, amount_per_original_unit, original_unit_name = exchange.calculate_remaining_days()

            from src.scheduler import dca_scheduler
            next_trade_time = dca_scheduler.get_time_until_next_trade() # hours, minutes

            # Format the text message - pass days_left info
            message = format_stats_message(
                stats=stats,
                current_price=current_price,
                usdt_balance=usdt_balance,
                # remaining_duration=remaining_duration, # Removed
                days_left=days_left,
                amount_per_original_unit=amount_per_original_unit,
                original_unit_name=original_unit_name,
                next_trade_time=next_trade_time
            )

            await update.message.reply_text(
                message,
                parse_mode=ParseMode.HTML,
                disable_notification=not settings.telegram.notification_sound
            )

        except Exception as e:
            logger.error(f"Error fetching or formatting stats: {e}", exc_info=True)
            await update.message.reply_text(
                "❌ An error occurred while fetching or generating statistics.",
                disable_notification=not settings.telegram.notification_sound
            )

    async def send_trade_summary(self, period_start: datetime, period_end: datetime) -> None:
        """Fetches trades in a period and sends a summary notification."""
        logger.info(f"Generating trade summary for period: {period_start} to {period_end}")
        try:
            trades_from_db = db.get_trades_since(period_start)

            # Filter trades strictly within the end time, handling mixed timezone awareness
            trades = []
            for t in trades_from_db:
                timestamp = t['timestamp']
                # If timestamp from DB is naive, assume it's UTC and make it aware
                if timestamp.tzinfo is None or timestamp.tzinfo.utcoffset(timestamp) is None:
                    timestamp = pytz.utc.localize(timestamp)
                    # Or use timestamp = timestamp.replace(tzinfo=pytz.utc)

                # Now compare aware timestamp with aware period_end
                if timestamp < period_end:
                    trades.append(t)

            if not trades:
                logger.info("No trades in the period to summarize.")
                # Optionally send a "no trades" message?
                # For now, we let the formatter handle the "no trades" message content.
                # return # Can return early if we don't want "no trade" messages

            # Fetch current data needed for the summary message
            stats = db.get_trade_stats()
            current_price = exchange.get_current_price()
            usdt_balance = exchange.get_account_balance().get('USDT', 0.0)
            from src.scheduler import dca_scheduler # Import here to avoid circular dependency at module level
            next_trade_time = dca_scheduler.get_time_until_next_trade()

            # Format the summary message
            message = format_trade_summary_notification(
                trades=trades,
                period_start=period_start,
                period_end=period_end,
                stats=stats,
                current_price=current_price,
                usdt_balance=usdt_balance,
                next_trade_time=next_trade_time
            )

            # Send the message
            await self.application.bot.send_message(
                chat_id=self.allowed_user_id,
                text=message,
                parse_mode=ParseMode.HTML,
                disable_notification=not settings.telegram.notification_sound # Keep sound off for summaries?
            )
            logger.info(f"Sent trade summary for {len(trades)} trades.")

        except Exception as e:
            logger.error(f"Error generating or sending trade summary: {e}", exc_info=True)
            # Optionally send an error message to the user?
            try:
                await self.application.bot.send_message(
                    chat_id=self.allowed_user_id,
                    text="❌ Error generating trade summary report.",
                    disable_notification=True
                )
            except Exception as send_e:
                logger.error(f"Failed to send trade summary error notification: {send_e}")

    async def send_trade_notification(self, trade: dict) -> None:
        """Handles trade completion: logs it, updates stats. (Does NOT send notification anymore)."""
        # This function is called after a trade is successfully executed.
        # We keep it to potentially log trades or update internal stats if needed,
        # but the direct notification sending is removed.
        logger.info(f"Trade completed (notification deferred to summary): {trade.get('order_id')}")

        # Original data fetching (kept in case needed for logging/stats update in future):
        # stats = db.get_trade_stats()
        # current_price = exchange.get_current_price()
        # from src.scheduler import dca_scheduler
        # usdt_balance = exchange.get_account_balance().get('USDT', 0.0)
        # remaining_duration = exchange.calculate_remaining_duration()
        # next_trade_time = dca_scheduler.get_time_until_next_trade()

        # --- MESSAGE SENDING REMOVED ---
        # message = format_trade_notification(...)
        # await self.application.bot.send_message(...)
        # --- --- --- --- --- --- --- ---

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
