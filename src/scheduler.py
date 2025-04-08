import schedule
import asyncio
import logging
from datetime import datetime, timedelta

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
        if self.dca_period == "1_minute":
            return (0, 1)  # Always 1 minute for minute-based DCA

        next_run = schedule.next_run()
        if self.dca_period in ["1_minute", "1_hour"]:
            # For minute/hour, the next run is roughly the interval duration
            if self.dca_period == "1_minute":
                return (0, 1)
            elif self.dca_period == "1_hour":
                # Calculate based on next run time vs now
                now = datetime.now()
                if next_run:
                    diff = next_run - now
                    if diff.total_seconds() < 0: diff = timedelta(hours=1) # Approximate if past
                    h, rem = divmod(diff.seconds, 3600)
                    m, _ = divmod(rem, 60)
                    # Return minutes until next hour mark at specified minute
                    return (h, m + 1) # Add 1 minute buffer for display
                else:
                    return (0, 60) # Fallback estimate

        next_run = schedule.next_run()
        if next_run:
            now = datetime.now() # Use local time unless job is UTC
            is_utc_job = any(job.at_time is not None and job.unit == 'days' for job in schedule.get_jobs())
            if is_utc_job:
                now = datetime.utcnow()

            time_diff = next_run - now
            if time_diff.total_seconds() < 0: # If calculated next run is in the past
                logger.warning("get_time_until_next_trade: Next run time is in the past, returning estimate.")
                # Provide estimate based on period if calculation failed
                if self.dca_period == "1_day": return (23, 59) # Approx 24h
                # Hourly handled above
                else: return (0, 0) # Should not happen

            # Check if it's a daily job and calculate time diff
            if self.dca_period == "1_day":
                 hours, remainder = divmod(time_diff.seconds, 3600)
                 minutes, _ = divmod(remainder, 60)
                 # Add full days if diff is more than a day
                 total_hours = time_diff.days * 24 + hours
                 return (total_hours, minutes)
            # Hourly is handled in the block above
            # Minute is handled at the start

        # Fallback if scheduler has no next run (shouldn't normally happen if running)
        logger.warning("get_time_until_next_trade: Could not determine next run time from scheduler.")
        if self.dca_period == "1_day": return (23, 59) # Estimate
        if self.dca_period == "1_hour": return (0, 59) # Estimate
        return (0, 0)


# Create singleton instance
dca_scheduler = DCAScheduler()
