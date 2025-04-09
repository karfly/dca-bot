import asyncio
import logging
import sys
import signal
import os
import dotenv
import threading
from datetime import datetime, timedelta
import pytz

# Load environment variables before other imports
dotenv.load_dotenv()

from src.config import settings
from src.exchange import exchange
from src.bot.telegram import telegram_bot
from src.scheduler import dca_scheduler, setup_schedule, run_schedule
from src.db.mongodb import db


# Configure logging
def setup_logging() -> None:
    """Set up application logging."""
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("dca_bot.log")
        ]
    )

    # Reduce logging for some modules
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("schedule").setLevel(logging.WARNING)


def handle_exit(signum, frame) -> None:
    """Handle exit signals."""
    logging.info("Shutdown signal received, stopping application...")
    # We can't directly await in a signal handler, so we need to use a different approach
    loop = asyncio.get_event_loop()
    if loop.is_running():
        loop.create_task(shutdown_gracefully())
    sys.exit(0)


async def shutdown_gracefully() -> None:
    """Gracefully shutdown the application."""
    await dca_scheduler.stop()
    await telegram_bot.application.stop()
    logging.info("Application shut down gracefully")


async def send_startup_summary():
    """Send a trade summary for the last 12 hours on startup."""
    try:
        end_time = datetime.now(pytz.utc)
        start_time = end_time - timedelta(hours=12)
        logging.info(f"Sending startup trade summary for last 12 hours ({start_time} to {end_time})")
        await telegram_bot.send_trade_summary(start_time, end_time)
    except Exception as e:
        logging.error(f"Failed to send startup trade summary: {e}", exc_info=True)


async def run_app() -> None:
    """Run the main application."""
    # Register signal handlers
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    logging.info("Starting Bitcoin DCA bot")

    try:
        # Log configuration
        logging.info(f"DCA amount: ${settings.dca.amount_usd}")
        logging.info(f"DCA period: {settings.dca.period}")
        logging.info(f"DCA time: {settings.dca.time_utc.strftime('%H:%M')} UTC")
        logging.info(f"Dry run mode: {settings.dry_run}")

        # Check OKX API connectivity
        logging.info("Testing OKX API connectivity...")
        ticker = exchange.get_ticker()
        logging.info(f"Current BTC price: ${ticker['last']:.2f}")

        # Check account balance
        balances = exchange.get_account_balance()
        logging.info(f"USDT balance: ${balances['USDT']:.2f}")

        if balances['USDT'] < settings.dca.amount_usd:
            logging.warning(
                f"USDT balance (${balances['USDT']:.2f}) is below DCA amount "
                f"(${settings.dca.amount_usd:.2f})"
            )

        # Start scheduler
        run_immediately = os.environ.get("RUN_IMMEDIATELY", "false").lower() == "true"
        await dca_scheduler.start(run_immediately=run_immediately)

        # Start the scheduler in a separate thread
        schedule_thread = threading.Thread(target=run_schedule, daemon=True)
        schedule_thread.start()

        # Send startup summary (run async in the main thread's event loop)
        # This assumes run_webhook/run_polling starts or uses an asyncio loop
        # If using run_polling, it blocks, so we might need to run this before polling starts
        # If using run_webhook (async), this should work.
        # Let's assume an async context is available (like when using run_webhook or if run_polling is adapted)
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(send_startup_summary())
            # If loop isn't running yet, need loop.run_until_complete(send_startup_summary())
            # but that might conflict with the bot's own loop handling.
            # A simple create_task is often sufficient if the loop starts soon.
        except RuntimeError:
            # Fallback if no event loop is running yet
            asyncio.run(send_startup_summary())

        # Start Telegram bot
        await telegram_bot.application.initialize()
        await telegram_bot.application.start()
        await telegram_bot.application.updater.start_polling()

        logging.info("Application started successfully")

        # Keep the application running
        while True:
            await asyncio.sleep(1)

    except Exception as e:
        logging.error(f"Error running application: {str(e)}")
        await dca_scheduler.stop()
        await telegram_bot.application.stop()
        sys.exit(1)


if __name__ == "__main__":
    setup_logging()
    asyncio.run(run_app())
