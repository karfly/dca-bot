import ccxt
import logging
from typing import Dict, Any, Tuple, Optional
import time

from src.config import settings
from src.exchange.base import Exchange

logger = logging.getLogger(__name__)


class OKXExchange(Exchange):
    """OKX Exchange integration."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        api_passphrase: str,
        subaccount_name: str = None,
        symbol: str = 'BTC/USDT',
        dry_run: bool = False
    ):
        """Initialize OKX exchange client."""
        super().__init__(api_key, api_secret, symbol, dry_run)

        self.exchange = ccxt.okx({
            'apiKey': api_key,
            'secret': api_secret,
            'password': api_passphrase,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
                'broker': 'dca-bot'
            }
        })

        if subaccount_name:
            self.exchange.headers.update({'x-simulated-trading': '0'})
            self.exchange.options['account'] = 'trading'

        logger.info(f"OKX client initialized (dry_run: {dry_run})")

    def get_ticker(self) -> Dict[str, Any]:
        """Get current ticker for BTC/USDT."""
        return self.exchange.fetch_ticker(self.symbol)

    def get_account_balance(self) -> Dict[str, float]:
        """Get account balance."""
        balances = self.exchange.fetch_balance()
        return {
            'BTC': float(balances.get('BTC', {}).get('free', 0)),
            'USDT': float(balances.get('USDT', {}).get('free', 0))
        }

    def buy_bitcoin(self, usd_amount: float) -> Dict[str, Any]:
        """Buy Bitcoin with specified USD amount."""
        # Get current price and calculate BTC amount
        ticker = self.get_ticker()
        current_price = ticker['last']
        btc_amount = usd_amount / current_price

        # Format BTC amount according to OKX precision (typically 8 decimal places)
        btc_amount = round(btc_amount, 8)

        logger.info(f"Placing market buy order for {usd_amount} USDT (approximately {btc_amount} BTC at {current_price} USDT/BTC)")

        if self.dry_run:
            logger.info("DRY RUN: Order not actually placed")
            return {
                'success': True,
                'btc_amount': btc_amount,
                'usd_amount': usd_amount,
                'price': current_price,
                'dry_run': True
            }

        try:
            # Create market buy order with calculated BTC amount
            order = self.exchange.create_market_order(
                symbol=self.symbol,
                side='buy',
                amount=btc_amount,  # Amount in base currency (BTC)
                params={'tdMode': 'cash'}  # Spot trading
            )

            logger.info(f"Raw order response: {order}")

            # Wait for order to be filled and fetch its details
            time.sleep(2)  # Give some time for the order to be processed
            order_details = self.exchange.fetch_order(order['id'], self.symbol)

            if not order_details:
                raise ccxt.ExchangeError(f"Could not fetch order details for order ID: {order['id']}")

            # Get actual executed amounts from the order details
            filled_btc = float(order_details['filled'])
            cost = float(order_details['cost'])
            actual_price = float(order_details['price'])

            if not filled_btc or not cost or not actual_price:
                raise ccxt.ExchangeError(f"Order details incomplete: {order_details}")

            logger.info(f"Order executed: spent {cost} USDT to buy {filled_btc} BTC at {actual_price} USDT/BTC")

            return {
                'success': True,
                'order_id': order_details['id'],
                'btc_amount': filled_btc,
                'usd_amount': cost,
                'price': actual_price
            }

        except ccxt.InsufficientFunds as e:
            logger.error(f"Insufficient funds for order: {str(e)}")
            raise
        except ccxt.PermissionDenied as e:
            logger.error(f"Permission denied: {str(e)}")
            raise
        except ccxt.ExchangeError as e:
            logger.error(f"Exchange error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error placing order: {str(e)}")
            raise

    def calculate_remaining_duration(self) -> Tuple[int, str, float, str]:
        """Calculate how many periods (days/hours/minutes) of DCA are left."""
        balance = self.get_account_balance()
        usdt_balance = balance.get('USDT', 0.0)
        amount_per_period = settings.dca.amount_usd
        period = settings.dca.period

        remaining_value = 0
        unit = "unknown"
        unit_name = "period"

        if amount_per_period > 0:
            if period == "1_day":
                remaining_value = int(usdt_balance / amount_per_period)
                unit = "days"
                unit_name = "day"
            elif period == "1_hour":
                remaining_value = int(usdt_balance / amount_per_period)
                unit = "hours"
                unit_name = "hour"
            elif period == "1_minute":
                remaining_value = int(usdt_balance / amount_per_period)
                unit = "minutes"
                unit_name = "minute"
        else:
             logger.warning("DCA amount is zero, cannot calculate remaining duration.")

        return remaining_value, unit, amount_per_period, unit_name

    def calculate_remaining_days(self) -> Tuple[int, float, str]:
        """Calculate approximate days left and return original period info."""
        balance = self.get_account_balance()
        usdt_balance = balance.get('USDT', 0.0)
        amount_per_original_unit = settings.dca.amount_usd
        period = settings.dca.period

        days_left = 0
        original_unit_name = "period"

        if amount_per_original_unit > 0:
            if period == "1_day":
                days_left = int(usdt_balance / amount_per_original_unit)
                original_unit_name = "day"
            elif period == "1_hour":
                # Calculate total hours, then convert to days
                hours_left = usdt_balance / amount_per_original_unit
                days_left = int(hours_left / 24)
                original_unit_name = "hour"
            elif period == "1_minute":
                # Calculate total minutes, then convert to days
                minutes_left = usdt_balance / amount_per_original_unit
                days_left = int(minutes_left / (24 * 60))
                original_unit_name = "minute"
        else:
            logger.warning("DCA amount is zero, cannot calculate remaining days.")

        return days_left, amount_per_original_unit, original_unit_name

    def get_current_price(self) -> float:
        """Get current BTC price in USDT."""
        ticker = self.get_ticker()
        return ticker['last']

    def create_market_sell_order(self, symbol: str, amount: float) -> Dict[str, Any]:
        """Create a market sell order.

        Args:
            symbol: The trading pair symbol (e.g. 'BTC/USDT')
            amount: The amount of the base currency to sell

        Returns:
            The order details
        """
        if self.dry_run:
            logger.info(f"DRY RUN: Would sell {amount} of {symbol}")
            return {
                'id': 'dry-run-sell',
                'symbol': symbol,
                'amount': amount,
                'price': self.get_current_price(),
                'side': 'sell',
                'type': 'market',
                'dry_run': True
            }

        return self.exchange.create_market_sell_order(symbol, amount, {'tdMode': 'cash'})


# Singleton instance
okx = OKXExchange(
    api_key=settings.okx.api_key,
    api_secret=settings.okx.api_secret,
    api_passphrase=settings.okx.api_passphrase,
    subaccount_name=settings.okx.subaccount_name,
    dry_run=settings.dry_run
)
