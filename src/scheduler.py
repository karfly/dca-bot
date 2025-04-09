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


class DCAScheduler:
    """Scheduler for Bitcoin DCA purchases."""

    def __init__(self):
        """Initialize the scheduler."""
        self.dca_time = settings.dca.time_utc
        self.dca_period = settings.dca.period
        self.running = False
        self.task = None
        logger.info(f"DCA Scheduler initialized (period: {self.dca_period}, time: {self.dca_time.strftime('%H:%M')} UTC)")

    async def execute_dca(self) -> None:
        """Execute the DCA strategy."""
        logger.info("Executing DCA strategy")

        try:
            # Check if we already made a purchase at this time today (only for daily DCA)
            if self.dca_period == "1_day" and self._is_duplicate_execution():
                logger.info("Skipping DCA execution: already executed for this time window today")
                return

            # Check if we already made a purchase within this hour (only for hourly DCA)
            # Note: Currently, duplicate check is only for daily. Hourly/Minute runs can overlap if restart happens.
            # Consider adding more robust duplicate checks if needed based on last execution time for hourly/minute.

            # Check if there's enough balance
            balances = exchange.get_account_balance()
            usdt_balance = balances["USDT"]
            dca_amount = settings.dca.amount_usd

            if usdt_balance < dca_amount:
                logger.warning(
                    f"Insufficient USDT balance: {usdt_balance} < {dca_amount}"
                )

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
                parse_mode="HTML",
                disable_notification=not settings.telegram.notification_sound
            )
        except Exception as e:
            logger.error(f"Error sending insufficient balance notification: {str(e)}")

    def schedule_daily_dca(self) -> None:
        """Schedule the DCA execution."""
        if self.dca_period == "1_day":
            time_str = f"{self.dca_time.hour:02d}:{self.dca_time.minute:02d}"
            logger.info(f"Scheduling daily DCA at {time_str} UTC")
            schedule.every().day.at(time_str, "UTC").do(lambda: asyncio.create_task(self.execute_dca()))
        else:  # 1_minute
            logger.info("Scheduling DCA every minute")
            schedule.every().minute.do(lambda: asyncio.create_task(self.execute_dca()))

    def schedule_dca(self) -> None:  # Renamed from schedule_daily_dca
        """Schedule the DCA execution based on the configured period."""
        schedule.clear() # Clear any previous jobs before scheduling anew
        if self.dca_period == "1_day":
            time_str = f"{self.dca_time.hour:02d}:{self.dca_time.minute:02d}"
            logger.info(f"Scheduling daily DCA at {time_str} UTC")
            schedule.every().day.at(time_str, "UTC").do(lambda: asyncio.create_task(self.execute_dca()))
        elif self.dca_period == "1_hour":
            # Schedule to run at the top of the hour (minute 00)
            minute_str = ":00"
            logger.info(f"Scheduling hourly DCA every hour at minute {minute_str} (on the hour)")
            # Note: The minute specified in DCA_TIME_UTC is ignored for the hourly schedule.
            schedule.every().hour.at(minute_str).do(lambda: asyncio.create_task(self.execute_dca()))
        elif self.dca_period == "1_minute":
            # Restore the original logic for 1_minute scheduling
            logger.info("Scheduling DCA every minute")
            schedule.every().minute.do(lambda: asyncio.create_task(self.execute_dca()))
        else:
            logger.error(f"Unsupported DCA period: {self.dca_period}. No jobs scheduled.")

    async def _run_scheduler(self) -> None:
        """Run the scheduler in a loop."""
        self.running = True

        while self.running:
            schedule.run_pending()
            await asyncio.sleep(1)

    async def start(self, run_immediately: bool = False) -> None:
        """Start the scheduler."""
        self.schedule_daily_dca()

        if run_immediately or self.dca_period == "1_minute":
            logger.info("Running DCA immediately")
            # For 1_minute period, we don't check for duplicate execution
            if self.dca_period == "1_day" and not self._is_duplicate_execution():
                await self.execute_dca()
            elif self.dca_period == "1_minute":
                await self.execute_dca()
            else:
                logger.info("Skipping immediate execution: already executed for this time window today")

        # Calculate time until next run (only for daily DCA)
        if self.dca_period == "1_day":
            next_run = schedule.next_run()
            if next_run:
                time_diff = next_run - datetime.now()
                hours, remainder = divmod(time_diff.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                logger.info(f"Next DCA execution in {hours} hours and {minutes} minutes")
        else:
            logger.info("DCA will execute every minute")
        self.schedule_dca()  # Call the renamed and updated method

        # Handle immediate execution request or default for frequent periods
        if run_immediately:
            logger.info("Running DCA immediately based on run_immediately flag")
            await self.execute_dca()
        elif self.dca_period == "1_minute": # Changed from ["1_minute", "1_hour"]
            # Execute immediately only for minute period on first start (unless run_immediately=True)
            logger.info(f"Running initial DCA for {self.dca_period} period")
            await self.execute_dca()
        elif self.dca_period in ["1_hour", "1_day"]:
             # For hourly and daily, only run immediately if explicitly requested (handled by run_immediately flag)
             # Otherwise, wait for the scheduled time.
             pass # No immediate run unless run_immediately=True

        # Calculate and log time until next run
        next_run = schedule.next_run()
        if next_run:
            now = datetime.now() # Use local time for diff calculation unless job is UTC
            # Adjust 'now' to UTC if the job is explicitly scheduled in UTC (only daily job currently)
            # A more robust approach would involve timezone handling throughout
            is_utc_job = any(job.at_time is not None and job.unit == 'days' for job in schedule.get_jobs())
            if is_utc_job:
                now = datetime.utcnow()

            time_diff = next_run - now
            if time_diff.total_seconds() < 0:
                # If next run is in the past, it might be due to clock sync or schedule lib issues.
                # Re-calculating or estimating is complex; log warning and approximate.
                logger.warning(f"Calculated next run ({next_run}) is in the past compared to now ({now}). Approximating time diff.")
                if self.dca_period == "1_hour":
                    # Approximate based on the schedule interval
                    time_diff = timedelta(hours=1) - timedelta(seconds=now.minute*60 + now.second - self.dca_time.minute*60)
                    if time_diff.total_seconds() < 0: time_diff += timedelta(hours=1)
                elif self.dca_period == "1_minute":
                    time_diff = timedelta(minutes=1) - timedelta(seconds=now.second)
                    if time_diff.total_seconds() < 0: time_diff += timedelta(minutes=1)
                else: # Daily
                     # Fallback for daily if calculation seems off
                     time_diff = timedelta(days=1)

            days = time_diff.days
            hours, remainder = divmod(time_diff.seconds, 3600)
            minutes, _ = divmod(remainder, 60)

            time_parts = []
            if days > 0:
                time_parts.append(f"{days} days")
            if hours > 0:
                time_parts.append(f"{hours} hours")
            if minutes > 0 or (days == 0 and hours == 0): # Show minutes if it's the only unit or with hours
                time_parts.append(f"{minutes} minutes")

            if not time_parts:
                time_parts.append("less than a minute")

            logger.info(f"Next DCA execution scheduled in {' and '.join(time_parts)}")
        else:
            logger.warning("Could not determine next run time from scheduler.")

        # Start the scheduler in a separate task
        self.task = asyncio.create_task(self._run_scheduler())
        logger.info(f"DCA Scheduler started (period: {self.dca_period})")

    async def stop(self) -> None:
        """Stop the scheduler."""
        self.running = False
        if self.task:
            await self.task
        logger.info("DCA Scheduler stopped")

    def get_time_until_next_trade(self) -> tuple:
        """
        Calculate the time until the next scheduled trade.

        Returns:
            tuple: (hours, minutes) until the next trade
        """
        # Handle minute period early
        if self.dca_period == "1_minute":
            return (0, 1)

        # Get the next scheduled run time
        next_run = schedule.next_run()

        if next_run:
            now = datetime.now() # Use local time unless job is UTC
            is_utc_job = any(job.at_time is not None and job.unit == 'days' for job in schedule.get_jobs())
            if is_utc_job:
                now = datetime.utcnow()

            time_diff = next_run - now

            # Handle case where calculated next run is in the past
            if time_diff.total_seconds() < 0:
                logger.warning("get_time_until_next_trade: Next run time is in the past, returning estimate.")
                if self.dca_period == "1_day": return (23, 59) # Approx 24h
                if self.dca_period == "1_hour": return (0, 59) # Approx 1h
                # Should not happen for 1_minute due to early return
                return (0, 0)

            # Calculate hours and minutes based on period
            if self.dca_period == "1_day":
                hours, remainder = divmod(time_diff.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                total_hours = time_diff.days * 24 + hours
                return (total_hours, minutes)

            elif self.dca_period == "1_hour":
                # If diff is very small (just executed), return estimate for the next hour
                if time_diff.total_seconds() < 60:
                    return (0, 59)
                # Otherwise, calculate actual time until next :00
                hours, remainder = divmod(time_diff.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                return (hours, minutes)

        # Fallback if scheduler has no next run (shouldn't normally happen if running)
        logger.warning("get_time_until_next_trade: Could not determine next run time from scheduler. Returning estimate.")
        if self.dca_period == "1_day": return (23, 59)
        if self.dca_period == "1_hour": return (0, 59)
        # Minute case handled above
        return (0, 0) # Default fallback


# Create singleton instance
dca_scheduler = DCAScheduler()

# --- NEW Trade Summary Job ---
def trade_summary_job(summary_start_time: datetime, summary_end_time: datetime):
    """Job to trigger the sending of a trade summary message."""
    logger.info(f"Executing scheduled trade summary job for period: {summary_start_time} - {summary_end_time}")
    try:
        asyncio.run(telegram_bot.send_trade_summary(summary_start_time, summary_end_time))
    except Exception as e:
        logger.error(f"Error during scheduled trade summary job: {e}", exc_info=True)

# --- Schedule Definition ---
def setup_schedule(schedule_settings: dict):
    """Sets up the recurring jobs based on config."""
    dca_scheduler.clear() # Clear existing jobs before setting up new ones
    logger.info(f"Setting up schedule with settings: {schedule_settings}")

    # -- Schedule DCA Job (existing) --
    interval = schedule_settings['interval']
    unit = schedule_settings['unit']

    if unit == 'minutes':
        dca_scheduler.every(interval).minutes.do(dca_job)
    elif unit == 'hours':
        dca_scheduler.every(interval).hours.do(dca_job)
    elif unit == 'days':
        dca_scheduler.every(interval).days.at("00:00").do(dca_job) # Example: run daily at midnight
    elif unit == 'weeks':
        dca_scheduler.every(interval).weeks.do(dca_job) # Day of week might need specification
    else:
        logger.error(f"Unsupported schedule unit: {unit}")
        return # Don't schedule anything if config is wrong

    logger.info(f"Scheduled DCA trades every {interval} {unit}.")

    # -- Schedule Trade Summary Jobs --
    # Define target times in UTC
    moscow_tz = pytz.timezone('Europe/Moscow')
    noon_msk = dt_time(12, 1, 0) # Changed from 12:00
    midnight_msk = dt_time(0, 1, 0) # Changed from 00:00

    # Convert target MSK times to UTC for scheduling
    # For the noon summary (approx 09:01 UTC), we summarize trades since midnight summary (approx 21:01 UTC prev day)
    # For the midnight summary (approx 21:01 UTC), we summarize trades since noon summary (approx 09:01 UTC same day)
    noon_utc_schedule_time = moscow_tz.localize(datetime.combine(datetime.now(moscow_tz).date(), noon_msk)).astimezone(pytz.utc).strftime("%H:%M")
    midnight_utc_schedule_time = moscow_tz.localize(datetime.combine(datetime.now(moscow_tz).date(), midnight_msk)).astimezone(pytz.utc).strftime("%H:%M")

    # Schedule the noon MSK (approx 09:01 UTC) summary
    dca_scheduler.every().day.at(noon_utc_schedule_time, pytz.utc).do(
        lambda: trade_summary_job(
            # Summarize the 12 hours leading up to the scheduled time (approx 09:01 UTC)
            summary_end_time=datetime.now(pytz.utc).replace(hour=int(noon_utc_schedule_time[:2]), minute=int(noon_utc_schedule_time[3:]), second=0, microsecond=0, tzinfo=pytz.utc),
            summary_start_time=datetime.now(pytz.utc).replace(hour=int(noon_utc_schedule_time[:2]), minute=int(noon_utc_schedule_time[3:]), second=0, microsecond=0, tzinfo=pytz.utc) - timedelta(hours=12)
        )
    )
    logger.info(f"Scheduled daily trade summary at 12:01 MSK ({noon_utc_schedule_time} UTC).") # Updated log message

    # Schedule the midnight MSK (approx 21:01 UTC) summary
    dca_scheduler.every().day.at(midnight_utc_schedule_time, pytz.utc).do(
        lambda: trade_summary_job(
            # Summarize the 12 hours leading up to the scheduled time (approx 21:01 UTC)
            summary_end_time=datetime.now(pytz.utc).replace(hour=int(midnight_utc_schedule_time[:2]), minute=int(midnight_utc_schedule_time[3:]), second=0, microsecond=0, tzinfo=pytz.utc),
            summary_start_time=datetime.now(pytz.utc).replace(hour=int(midnight_utc_schedule_time[:2]), minute=int(midnight_utc_schedule_time[3:]), second=0, microsecond=0, tzinfo=pytz.utc) - timedelta(hours=12)
        )
    )
    logger.info(f"Scheduled daily trade summary at 00:01 MSK ({midnight_utc_schedule_time} UTC).") # Updated log message

# --- Run Schedule Loop ---
def run_schedule():
    """Runs the scheduler loop indefinitely."""
    logger.info("Starting scheduler loop...")
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            # Catch errors within the loop to prevent the thread from crashing
            logger.error(f"Error during schedule.run_pending(): {e}", exc_info=True)
        time.sleep(1) # Check every second
