from typing import Dict, Any, Tuple, Optional

from src.config import settings
from src.exchange.base import Exchange


def get_exchange(exchange_id: str = None):
    """Factory function to get the appropriate exchange instance.

    Args:
        exchange_id: The exchange identifier (e.g., 'okx', 'binance')
                    If None, uses the value from settings.

    Returns:
        An exchange instance

    Raises:
        ValueError: If the exchange_id is not supported
    """
    import logging
    logger = logging.getLogger(__name__)

    if exchange_id is None:
        exchange_id = settings.exchange.id.lower()

    if exchange_id == 'okx':
        from src.exchange.okx import okx
        return okx
    else:
        supported_exchanges = Exchange.get_supported_exchanges()
        if exchange_id in supported_exchanges:
            logger.warning(f"Exchange {exchange_id} is supported by CCXT but not fully integrated in this application. "
                          f"Using OKX as fallback. Only OKX is fully tested and supported at this time.")
            from src.exchange.okx import okx
            return okx
        else:
            raise ValueError(f"Exchange {exchange_id} is not supported by CCXT. "
                            f"Please choose from: {', '.join(supported_exchanges[:10])}...")

# Default exchange instance based on configuration
exchange = get_exchange()
