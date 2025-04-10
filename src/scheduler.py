import schedule
import asyncio
import logging
from datetime import datetime, timedelta, time as dt_time
import pytz
import time # Import time module

from src.config import settings
from src.exchange import exchange
from src.db.mongodb import db
from src.bot.telegram import telegram_bot

logger = logging.getLogger(__name__)

class SchedulerBase:
    """Base class for schedulers."""

    def __init__(self, name):
        """Initialize base scheduler."""
        self.name = name
        self.running = False
        self.task = None
        logger.info(f"{self.name} initialized")

    async def _run_scheduler(self) -> None:
        """Run the scheduler in a loop."""
        self.running = True

        while self.running:
            schedule.run_pending()
            await asyncio.sleep(1)

    async def start(self) -> None:
        """Start the scheduler."""
        # Start the scheduler in a separate task
        self.task = asyncio.create_task(self._run_scheduler())
        logger.info(f"{self.name} started")

    async def stop(self) -> None:
        """Stop the scheduler."""
        self.running = False
        if self.task:
            await self.task
        logger.info(f"{self.name} stopped")

    def clear(self):
        """Clear all scheduled jobs."""
        schedule.clear()
        logger.info("Cleared all scheduled jobs")


class DCAScheduler(SchedulerBase):
    """Scheduler for Bitcoin DCA purchases."""

    def __init__(self):
        """Initialize the DCA scheduler."""
        super().__init__("DCA Scheduler")
        self.dca_time = settings.dca.time_utc
        self.dca_period = settings.dca.period

    async def execute_dca(self) -> None:
        """Execute the DCA strategy."""
        logger.info("Executing DCA strategy")

        try:
            # Check if we already made a purchase at this time today (only for daily DCA)
            if self.dca_period == "1_day" and self._is_duplicate_execution():
                logger.info("Skipping DCA execution: already executed for this time window today")
                return

            # Check if there's enough balance
            balances = exchange.get_account_balance()
            usdt_balance = balances["USDT"]
            dca_amount = settings.dca.amount_usd

            if usdt_balance < dca_amount:
                logger.warning(f"Insufficient USDT balance: {usdt_balance} < {dca_amount}")
                # Notify the user
                await self._notify_insufficient_balance(usdt_balance, dca_amount)
                return

            # Execute the buy
            trade_result = exchange.buy_bitcoin(dca_amount)

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
            await self._notify_trade_executed(trade_data)

        except Exception as e:
            logger.error(f"Error executing DCA strategy: {str(e)}")

    def _is_duplicate_execution(self) -> bool:
        """Check if we've already executed a trade for this time window today."""
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
                parse_mode="HTML",
                disable_notification=not settings.telegram.notification_sound
            )
        except Exception as e:
            logger.error(f"Error sending insufficient balance notification: {str(e)}")

    def schedule_dca_job(self) -> None:
        """Schedule the DCA execution based on the configured period."""
        schedule.clear()  # Clear any previous jobs

        # Schedule according to period
        if self.dca_period == "1_day":
            time_str = f"{self.dca_time.hour:02d}:{self.dca_time.minute:02d}"
            logger.info(f"Scheduling daily DCA at {time_str} UTC")
            schedule.every().day.at(time_str, "UTC").do(lambda: asyncio.create_task(self.execute_dca()))

        elif self.dca_period == "1_hour":
            logger.info("Scheduling hourly DCA on the hour")
            schedule.every().hour.at(":00").do(lambda: asyncio.create_task(self.execute_dca()))

        elif self.dca_period == "1_minute":
            logger.info("Scheduling DCA every minute")
            schedule.every().minute.do(lambda: asyncio.create_task(self.execute_dca()))

        else:
            logger.error(f"Unsupported DCA period: {self.dca_period}. No jobs scheduled.")

    def get_time_until_next_trade(self) -> tuple:
        """Calculate the time until the next scheduled trade."""
        # Handle minute period early
        if self.dca_period == "1_minute":
            return (0, 1)

        # Get the next scheduled run time
        next_run = schedule.next_run()

        if next_run:
            now = datetime.now() if self.dca_period == "1_hour" else datetime.utcnow()
            time_diff = next_run - now

            # Handle case where calculated next run is in the past
            if time_diff.total_seconds() < 0:
                logger.warning("Next run time is in the past, returning estimate.")
                if self.dca_period == "1_day": return (23, 59)  # Approx 24h
                if self.dca_period == "1_hour": return (0, 59)  # Approx 1h
                return (0, 0)

            # Calculate hours and minutes
            hours, remainder = divmod(time_diff.seconds, 3600)
            minutes, _ = divmod(remainder, 60)

            if self.dca_period == "1_day":
                total_hours = time_diff.days * 24 + hours
                return (total_hours, minutes)

            return (hours, minutes)

        # Fallback
        logger.warning("Could not determine next run time. Returning estimate.")
        if self.dca_period == "1_day": return (23, 59)
        if self.dca_period == "1_hour": return (0, 59)
        return (0, 0)

    async def start(self, run_immediately: bool = False) -> None:
        """Start the DCA scheduler."""
        # Schedule the DCA job
        self.schedule_dca_job()

        # Execute immediately if requested or for 1_minute period
        if run_immediately or self.dca_period == "1_minute":
            logger.info("Running DCA immediately")
            if self.dca_period == "1_day" and not self._is_duplicate_execution():
                await self.execute_dca()
            elif self.dca_period != "1_day":
                await self.execute_dca()
            else:
                logger.info("Skipping immediate execution: already executed for this time window")

        # Log next execution time
        hours, minutes = self.get_time_until_next_trade()
        if hours > 0 or minutes > 0:
            time_str = f"{hours} hours and {minutes} minutes" if hours > 0 else f"{minutes} minutes"
            logger.info(f"Next DCA execution in {time_str}")

        # Start the scheduler loop
        await super().start()


class TradeReportScheduler(SchedulerBase):
    """Scheduler for trade summary reports."""

    def __init__(self):
        """Initialize the trade report scheduler."""
        super().__init__("Trade Report Scheduler")
        self.dca_period = settings.dca.period
        self.dca_time = settings.dca.time_utc if hasattr(settings.dca, 'time_utc') else None
        self.report_times = settings.report.times_utc
        self.lookback_hours = settings.report.lookback_hours

        logger.info(f"Report scheduler initialized with {len(self.report_times)} report times and {self.lookback_hours} hour lookback")

    async def send_trade_summary(self) -> None:
        """Send a trade summary for the lookback period."""
        try:
            # Skip sending report if DCA_PERIOD is "1_day" and current time matches DCA time
            if self.dca_period == "1_day" and self._is_dca_execution_time():
                logger.info("Skipping trade report during DCA execution time")
                return

            # Calculate the lookback period
            end_time = datetime.now(pytz.utc)
            start_time = end_time - timedelta(hours=self.lookback_hours)

            logger.info(f"Sending trade summary for period: {start_time} - {end_time} (lookback: {self.lookback_hours} hours)")
            await telegram_bot.send_trade_summary(start_time, end_time)
        except Exception as e:
            logger.error(f"Error sending trade summary: {e}", exc_info=True)

    def _is_dca_execution_time(self) -> bool:
        """Check if current time matches DCA execution time."""
        if not self.dca_time:
            return False

        now = datetime.utcnow().time()
        return now.hour == self.dca_time.hour and now.minute == self.dca_time.minute

    def schedule_regular_reports(self) -> None:
        """Schedule regular trade summary reports."""
        schedule.clear()  # Clear any previous jobs

        if not self.report_times:
            logger.warning("No report times specified in settings. No regular reports will be scheduled.")
            return

        # Schedule a report at each configured time
        for report_time in self.report_times:
            time_str = f"{report_time.hour:02d}:{report_time.minute:02d}"

            schedule.every().day.at(time_str, pytz.utc).do(
                lambda: asyncio.create_task(self.send_trade_summary())
            )
            logger.info(f"Scheduled daily trade summary at {time_str} UTC with {self.lookback_hours} hour lookback")

        logger.info(f"Total scheduled reports: {len(self.report_times)}")

    async def start(self) -> None:
        """Start the trade report scheduler."""
        # Schedule reports
        self.schedule_regular_reports()

        # Start the scheduler loop
        await super().start()

    async def send_startup_summary(self) -> None:
        """Send a trade summary for the last lookback hours on startup."""
        try:
            # Calculate the lookback period
            end_time = datetime.now(pytz.utc)
            start_time = end_time - timedelta(hours=self.lookback_hours)

            logger.info(f"Sending startup trade summary for period: {start_time} - {end_time} (lookback: {self.lookback_hours} hours)")
            await telegram_bot.send_trade_summary(start_time, end_time)
        except Exception as e:
            logger.error(f"Failed to send startup trade summary: {e}", exc_info=True)


# Create singleton instances
dca_scheduler = DCAScheduler()
trade_report_scheduler = TradeReportScheduler()


def setup_schedule(schedule_settings: dict) -> None:
    """Setup all schedules based on configuration."""
    # Clear any existing schedules
    schedule.clear()

    # Start DCA scheduler with appropriate settings
    asyncio.create_task(dca_scheduler.start(run_immediately=False))

    # Start trade report scheduler
    asyncio.create_task(trade_report_scheduler.start())

    logger.info(f"All schedulers started with settings: {schedule_settings}")


def run_schedule():
    """Run the schedule loop indefinitely."""
    logger.info("Starting scheduler loop...")
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            logger.error(f"Error during schedule.run_pending(): {e}", exc_info=True)
        time.sleep(1)  # Check every second
