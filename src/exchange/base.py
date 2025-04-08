import ccxt
import logging
from typing import Dict, Any, Tuple, Optional, List
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class Exchange(ABC):
    """Base abstract class for exchange integrations."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        symbol: str = 'BTC/USDT',
        dry_run: bool = False
    ):
        """Initialize exchange client."""
        self.api_key = api_key
        self.api_secret = api_secret
        self.dry_run = dry_run
        self.symbol = symbol

    @abstractmethod
    def get_ticker(self) -> Dict[str, Any]:
        """Get current ticker for the trading pair."""
        pass

    @abstractmethod
    def get_account_balance(self) -> Dict[str, float]:
        """Get account balance."""
        pass

    @abstractmethod
    def buy_bitcoin(self, usd_amount: float) -> Dict[str, Any]:
        """Buy Bitcoin with specified USD amount."""
        pass

    @abstractmethod
    def calculate_remaining_duration(self) -> Tuple[int, str, float, str]:
        """Calculate how many periods (days/hours/minutes) of DCA are left."""

    @abstractmethod
    def calculate_remaining_days(self) -> Tuple[int, float, str]:
        """Calculate approximate days left and return original period info."""

    @abstractmethod
    def get_current_price(self) -> float:
        """Get current BTC price in USDT."""
        pass

    @abstractmethod
    def create_market_sell_order(self, symbol: str, amount: float) -> Dict[str, Any]:
        """Create a market sell order.

        Args:
            symbol: The trading pair symbol (e.g. 'BTC/USDT')
            amount: The amount of the base currency to sell

        Returns:
            The order details
        """
        pass

    @classmethod
    def get_supported_exchanges(cls) -> List[str]:
        """Get list of supported exchanges by CCXT."""
        return ccxt.exchanges