import schedule
import asyncio
import logging
from datetime import datetime, timedelta, time as dt_time
import pytz
import time

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
            try:
                schedule.run_pending()
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Error in {self.name} loop: {e}", exc_info=True)
                await asyncio.sleep(5) # Avoid tight loop on continuous error

    async def start(self) -> None:
        """Start the scheduler."""
        if not self.running:
            self.task = asyncio.create_task(self._run_scheduler())
            logger.info(f"{self.name} started")
        else:
            logger.warning(f"{self.name} already running.")

    async def stop(self) -> None:
        """Stop the scheduler."""
        if self.running:
            self.running = False
            if self.task:
                try:
                    self.task.cancel() # Request cancellation
                    await self.task
                except asyncio.CancelledError:
                    logger.info(f"{self.name} task cancelled.")
                except Exception as e:
                    logger.error(f"Error stopping {self.name}: {e}", exc_info=True)
            logger.info(f"{self.name} stopped")
        else:
            logger.info(f"{self.name} was not running.")

    def clear(self):
        """Clear all scheduled jobs for this scheduler instance."""
        # Note: schedule.clear() clears ALL jobs globally.
        # If multiple schedulers use 'schedule', we need finer control.
        # For now, assuming only one part of the app schedules jobs per type.
        schedule.clear(self.name) # Use tag to clear specific jobs if possible
        logger.info(f"Cleared scheduled jobs for {self.name}")


class DCAScheduler(SchedulerBase):
    """Scheduler for Bitcoin DCA purchases."""

    def __init__(self):
        """Initialize the DCA scheduler."""
        super().__init__("DCA Scheduler")
        # Store settings locally for easier access
        self.dca_start_time = settings.dca.start_time_utc # Can be None
        self.dca_period = settings.dca.period
        self.send_notifications_globally = settings.send_trade_notifications # Renamed global flag

    async def execute_dca(self) -> None: # Removed send_notification parameter
        """Execute the DCA strategy."""
        logger.info(f"Attempting DCA execution (Global Notification Setting: {self.send_notifications_globally})...")

        try:
            # Check balance
            balances = exchange.get_account_balance()
            usdt_balance = balances.get("USDT", 0.0) # Use .get for safety
            dca_amount = settings.dca.amount_usd

            if usdt_balance < dca_amount:
                logger.warning(f"Insufficient balance for DCA: Have ${usdt_balance:.2f}, Need ${dca_amount:.2f}")
                await self._notify_insufficient_balance(usdt_balance, dca_amount)
                return

            # Execute buy
            trade_result = exchange.buy_bitcoin(dca_amount)

            if not trade_result.get("success"):
                error_msg = trade_result.get('error', 'Unknown error')
                logger.error(f"DCA execution failed: {error_msg}")
                # Consider sending a failure notification here if needed
                return

            # Save trade
            trade_data = {
                "btc_amount": trade_result["btc_amount"],
                "usd_amount": trade_result["usd_amount"],
                "price": trade_result["price"],
                "order_id": trade_result.get("order_id", "dry-run"),
                "dry_run": settings.dry_run
            }
            db.save_trade(trade_data)
            logger.info(f"DCA executed successfully. Order ID: {trade_data['order_id']}, Amount: ${trade_data['usd_amount']:.2f}")

            # Always call the notification handler after saving trade
            await self._notify_trade_executed(trade_data)

        except Exception as e:
            logger.error(f"Unexpected error during DCA execution: {e}", exc_info=True)

    async def _notify_trade_executed(self, trade: dict) -> None:
        """Notify the user about the executed trade via Telegram if globally enabled."""
        # Check the global setting here before calling the bot
        if self.send_notifications_globally:
            try:
                # Gather necessary data for the notification message
                logger.debug("Gathering data for trade notification...")
                stats = db.get_trade_stats()
                current_price = exchange.get_current_price()
                usdt_balance = exchange.get_account_balance().get("USDT", 0.0)
                # Import dca_scheduler locally if needed or pass self?
                # Let's get it directly from the instance method
                next_trade_time_tuple = self.get_time_until_next_trade()
                logger.debug("Data gathered, calling telegram bot.")

                # Call the bot method with all required data
                await telegram_bot.send_trade_notification(
                    trade=trade,
                    stats=stats,
                    current_price=current_price,
                    usdt_balance=usdt_balance,
                    next_trade_time=next_trade_time_tuple
                    # Note: remaining_duration is not readily available here,
                    # the formatter might need adjustment if it strictly requires it.
                )
            except Exception as e:
                logger.error(f"Failed to send trade notification: {e}", exc_info=True)
        else:
            logger.info(f"Trade notification skipped for order {trade.get('order_id', 'N/A')} due to global setting.")

    async def _notify_insufficient_balance(self, balance: float, required: float) -> None:
        """Notify the user about insufficient balance via Telegram."""
        try:
            await telegram_bot.send_insufficient_balance_notification(balance, required)
        except Exception as e:
            logger.error(f"Failed to send insufficient balance notification: {e}", exc_info=True)

    def schedule_dca_job(self) -> None:
        """Schedule the DCA execution based on the configured period."""
        schedule.clear("dca_job")

        # Use the global notification setting for the job action
        job_action = lambda: asyncio.create_task(self.execute_dca())
        job_tag = "dca_job"

        if self.dca_period == "1_day":
            # Daily period *requires* start_time, checked during config loading
            if not self.dca_start_time:
                logger.error("DCA start time is required for daily period but missing. Job not scheduled.")
                return
            time_str = self.dca_start_time.strftime("%H:%M") # Format HH:MM
            logger.info(f"Scheduling daily DCA at {time_str} UTC")
            schedule.every().day.at(time_str, "UTC").do(job_action).tag(job_tag)

        elif self.dca_period == "1_hour":
            # Hourly jobs run at the start of the hour
            logger.info("Scheduling hourly DCA (at minute 00)")
            schedule.every().hour.at(":00").do(job_action).tag(job_tag)

        elif self.dca_period == "1_minute":
            # Minute jobs run at the start of the minute
            logger.info("Scheduling DCA every minute (at second 00)")
            schedule.every().minute.at(":00").do(job_action).tag(job_tag)

        else:
            logger.error(f"Unsupported DCA period: {self.dca_period}. No DCA jobs scheduled.")
            return # Explicit return if no job scheduled

        # Log the next run time after scheduling
        next_run_time = schedule.next_run() # Actually call the function
        if next_run_time:
             # Use %Z for timezone, handle potential naive datetime if tz not available
             time_format = '%Y-%m-%d %H:%M:%S %Z' if next_run_time.tzinfo else '%Y-%m-%d %H:%M:%S (Naive)'
             logger.info(f"Next DCA run scheduled at: {next_run_time.strftime(time_format)}")
        else:
             logger.warning("Could not determine the next DCA run time after scheduling.")

    def get_time_until_next_trade(self) -> tuple[int, int]:
        """Calculate the approximate time (hours, minutes) until the next scheduled DCA trade."""
        next_run = schedule.get_jobs("dca_job") # Get only DCA jobs
        if not next_run:
             logger.warning("No active DCA job found to calculate next run time.")
             return (0, 0) # Indicate unknown

        next_run_time = next_run[0].next_run # Assuming only one DCA job exists

        if not next_run_time:
             logger.warning("Active DCA job found, but next run time is not available.")
             return (0, 0) # Indicate unknown

        # Determine current time based on job's timezone awareness
        if next_run_time.tzinfo:
            now = datetime.now(next_run_time.tzinfo)
        else:
            # If job time is naive, assume UTC as per scheduling logic for daily
            # For hourly/minutely, it uses local time implicitly by `schedule`.
            # This inconsistency in `schedule` library makes precise calculation hard.
            # Let's assume UTC for daily and server's local for others.
            # A better approach might involve storing tz explicitly with the job.
            now = datetime.utcnow() if self.dca_period == "1_day" else datetime.now()


        time_diff = next_run_time - now

        if time_diff.total_seconds() < 0:
            # This might happen briefly after a job runs before schedule recalculates.
            # Or if the calculation logic has timezone issues.
            logger.warning(f"Calculated next run time ({next_run_time}) is in the past compared to 'now' ({now}). Returning estimate.")
            # Return estimates based on period
            if self.dca_period == "1_day": return (24, 0)
            if self.dca_period == "1_hour": return (1, 0)
            if self.dca_period == "1_minute": return (0, 1)
            return (0, 0) # Default fallback

        # Calculate remaining hours and minutes
        total_seconds = int(time_diff.total_seconds())
        days = time_diff.days
        hours = (total_seconds // 3600) % 24
        minutes = (total_seconds // 60) % 60

        total_hours = days * 24 + hours

        return (total_hours, minutes)


    async def start(self) -> None:
        """Start the DCA scheduler: schedule job and start the runner."""
        self.schedule_dca_job()

        # Log next execution time only if a job was scheduled
        if schedule.get_jobs("dca_job"):
            hours, minutes = self.get_time_until_next_trade()
            if hours > 0 or minutes > 0:
                time_str = f"{hours}h {minutes}m"
                logger.info(f"Estimated time until next DCA execution: {time_str}")
            elif hours == 0 and minutes == 1 and self.dca_period == "1_minute":
                 logger.info("Next DCA execution expected within the next minute.")
            # else: Don't log if time is (0,0) or calculation failed

        # Start the base scheduler loop (runs schedule.run_pending())
        await super().start()


class TradeReportScheduler(SchedulerBase):
    """Scheduler for sending periodic trade summary reports."""

    def __init__(self):
        """Initialize the trade report scheduler."""
        super().__init__("Trade Report Scheduler")
        # Store relevant settings locally for clarity
        self.report_times = settings.report.times_utc or []
        self.lookback_hours = settings.report.lookback_hours
        # Needed to check if report time coincides with daily DCA time
        self.dca_period = settings.dca.period
        self.dca_time = settings.dca.start_time_utc

        if not self.report_times:
            logger.warning("No report times configured (REPORT_TIMES_UTC). Report scheduler initialized but inactive.")
        else:
             logger.info(f"Report scheduler initialized: {len(self.report_times)} daily reports, {self.lookback_hours}h lookback.")

    async def send_trade_summary(self) -> None:
        """Generate and send a trade summary for the configured lookback period."""
        # Avoid sending report if it coincides exactly with daily DCA execution time
        if self.dca_period == "1_day" and self._is_dca_execution_time():
            logger.info("Skipping trade report generation as it coincides with daily DCA time.")
            return

        try:
            end_time = datetime.now(pytz.utc)
            start_time = end_time - timedelta(hours=self.lookback_hours)
            logger.info(f"Generating trade summary report for period: {start_time.strftime('%Y-%m-%d %H:%M')} to {end_time.strftime('%Y-%m-%d %H:%M')} UTC")
            await telegram_bot.send_trade_summary(start_time, end_time)
        except Exception as e:
            logger.error(f"Failed to send trade summary report: {e}", exc_info=True)

    def _is_dca_execution_time(self) -> bool:
        """Check if the current UTC time matches the configured daily DCA execution time."""
        if not self.dca_time or self.dca_period != "1_day":
            return False # Only relevant for daily DCA

        now_utc = datetime.now(pytz.utc).time()
        # Compare only hour and minute
        return now_utc.hour == self.dca_time.hour and now_utc.minute == self.dca_time.minute

    def schedule_regular_reports(self) -> None:
        """Schedule the trade summary reports based on configured times."""
        schedule.clear("report_job") # Clear existing report jobs

        if not self.report_times:
            return # Nothing to schedule

        job_action = lambda: asyncio.create_task(self.send_trade_summary())
        job_tag = "report_job"

        for report_time in self.report_times:
            time_str = f"{report_time.hour:02d}:{report_time.minute:02d}"
            try:
                schedule.every().day.at(time_str, pytz.utc).do(job_action).tag(job_tag)
                logger.info(f"Scheduled daily trade summary at {time_str} UTC (tag: {job_tag})")
            except Exception as e:
                 logger.error(f"Failed to schedule report at {time_str} UTC: {e}")

        logger.info(f"Total reports scheduled: {len(schedule.get_jobs(job_tag))}")

    async def start(self) -> None:
        """Start the trade report scheduler: schedule jobs and start runner."""
        self.schedule_regular_reports()
        # Start the base scheduler loop only if reports are scheduled
        if schedule.get_jobs("report_job"):
            await super().start()
        else:
            logger.info("No reports scheduled, trade report scheduler loop will not start.")


    async def send_startup_summary(self) -> None:
        """Send a trade summary on application startup (optional)."""
        if not self.report_times:
             logger.info("Skipping startup summary: No report times configured.")
             return # Don't send if reports are disabled

        try:
            end_time = datetime.now(pytz.utc)
            start_time = end_time - timedelta(hours=self.lookback_hours)
            logger.info(f"Sending startup trade summary (last {self.lookback_hours} hours)...")
            await telegram_bot.send_trade_summary(start_time, end_time)
        except Exception as e:
            logger.error(f"Failed to send startup trade summary: {e}", exc_info=True)


# --- Singleton Instances ---
dca_scheduler = DCAScheduler()
trade_report_scheduler = TradeReportScheduler()


# --- Global Scheduler Control ---

async def setup_and_start_schedulers() -> None:
    """Initialize and start all required schedulers."""
    logger.info("Setting up and starting schedulers...")
    # Log key settings relevant to scheduling
    logger.info(f"DCA Period: {settings.dca.period}")
    if settings.dca.period == "1_day":
        # Ensure start_time_utc exists before formatting (validated during config load)
        time_str = settings.dca.start_time_utc.strftime('%H:%M') if settings.dca.start_time_utc else "N/A"
        logger.info(f"DCA Daily Start Time: {time_str} UTC")
    logger.info(f"Report Times: {', '.join(t.strftime('%H:%M') for t in settings.report.times_utc) if settings.report.times_utc else 'None'}")
    logger.info(f"Report Lookback: {settings.report.lookback_hours} hours")
    logger.info(f"Send Trade Notifications: {settings.send_trade_notifications}")

    # Start scheduler loops concurrently
    scheduler_start_tasks = [
        dca_scheduler.start(),
        trade_report_scheduler.start()
    ]
    await asyncio.gather(*scheduler_start_tasks)

    logger.info("All schedulers initialized and started.")

