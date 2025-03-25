import schedule
import time
import logging
import threading
from datetime import datetime, timedelta

from src.config import settings
from src.exchange.okx import okx
from src.db.mongodb import db
from src.bot.telegram import telegram_bot

logger = logging.getLogger(__name__)


class DCAScheduler:
    """Scheduler for daily Bitcoin DCA purchases."""

    def __init__(self):
        """Initialize the scheduler."""
        self.dca_time = settings.dca.time_utc
        self.running = False
        self.thread = None
        logger.info(f"DCA Scheduler initialized (time: {self.dca_time.strftime('%H:%M')} UTC)")

    def execute_dca(self) -> None:
        """Execute the DCA strategy."""
        logger.info("Executing DCA strategy")

        try:
            # Check if we already made a purchase at this time today
            if self._is_duplicate_execution():
                logger.info("Skipping DCA execution: already executed for this time window today")
                return

            # Check if there's enough balance
            balances = okx.get_account_balance()
            usdt_balance = balances["USDT"]
            dca_amount = settings.dca.amount_usd

            if usdt_balance < dca_amount:
                logger.warning(
                    f"Insufficient USDT balance: {usdt_balance} < {dca_amount}"
                )

                # Notify the user
                self._notify_insufficient_balance(usdt_balance, dca_amount)
                return

            # Execute the buy
            trade_result = okx.buy_bitcoin(dca_amount)

            if not trade_result["success"]:
                logger.error(f"DCA execution failed: {trade_result.get('error')}")
                return

            # Save the trade to the database
            trade_data = {
                "btc_amount": trade_result["btc_amount"],
                "usd_amount": trade_result["usd_amount"],
                "price": trade_result["price"],
                "order_id": trade_result.get("order_id", "dry-run"),
                "dry_run": settings.dry_run
            }

            db.save_trade(trade_data)
            logger.info(f"DCA executed and saved: {trade_data}")

            # Send notification
            self._notify_trade_executed(trade_data)

        except Exception as e:
            logger.error(f"Error executing DCA strategy: {str(e)}")

    def _is_duplicate_execution(self) -> bool:
        """
        Check if we've already executed a trade for this time window today.

        Returns:
            bool: True if a trade already exists for this time window, False otherwise
        """
        return db.has_trade_today_at_hour(
            hour=self.dca_time.hour,
            minute=self.dca_time.minute
        )

    async def _notify_trade_executed(self, trade: dict) -> None:
        """Notify the user about the executed trade."""
        try:
            await telegram_bot.send_trade_notification(trade)
        except Exception as e:
            logger.error(f"Error sending trade notification: {str(e)}")

    async def _notify_insufficient_balance(self, balance: float, required: float) -> None:
        """Notify the user about insufficient balance."""
        try:
            message = f"""
<b>⚠️ Insufficient Balance</b>

Your USDT balance is too low to execute DCA:
• Available: <code>${balance:.2f}</code>
• Required: <code>${required:.2f}</code>

Please deposit more funds to continue your DCA strategy.
"""
            await telegram_bot.application.bot.send_message(
                chat_id=settings.telegram.user_id,
                text=message,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Error sending insufficient balance notification: {str(e)}")

    def schedule_daily_dca(self) -> None:
        """Schedule the daily DCA execution."""
        time_str = f"{self.dca_time.hour:02d}:{self.dca_time.minute:02d}"
        logger.info(f"Scheduling daily DCA at {time_str} UTC")

        schedule.every().day.at(time_str, "UTC").do(self.execute_dca)

    def _run_scheduler(self) -> None:
        """Run the scheduler in a loop."""
        self.running = True

        while self.running:
            schedule.run_pending()
            time.sleep(1)

    def start(self, run_immediately: bool = False) -> None:
        """Start the scheduler."""
        self.schedule_daily_dca()

        if run_immediately:
            logger.info("Running DCA immediately")
            # Check if we've already made a purchase at this time today
            if not self._is_duplicate_execution():
                self.execute_dca()
            else:
                logger.info("Skipping immediate execution: already executed for this time window today")

        # Calculate time until next run
        next_run = schedule.next_run()
        if next_run:
            time_diff = next_run - datetime.now()
            hours, remainder = divmod(time_diff.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            logger.info(f"Next DCA execution in {hours} hours and {minutes} minutes")

        # Start the scheduler in a separate thread
        self.thread = threading.Thread(target=self._run_scheduler)
        self.thread.daemon = True
        self.thread.start()
        logger.info("DCA Scheduler started")

    def stop(self) -> None:
        """Stop the scheduler."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)
        logger.info("DCA Scheduler stopped")


# Singleton instance
dca_scheduler = DCAScheduler()
