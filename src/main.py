import asyncio
import logging
import sys
import signal
import os
import dotenv

# Load environment variables before other imports
dotenv.load_dotenv()

from src.config import settings
from src.exchange import exchange
from src.bot.telegram import telegram_bot
from src.scheduler import dca_scheduler
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
