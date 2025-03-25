import ccxt
import logging
from typing import Dict, Any, Tuple, Optional
import time

from src.config import settings
from src.utils.security import validate_transaction_amount

logger = logging.getLogger(__name__)


class OKXExchange:
    """OKX Exchange integration."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        api_passphrase: str,
        subaccount_name: str,
        dry_run: bool = False
    ):
        """Initialize OKX exchange client."""
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

        self.dry_run = dry_run
        self.symbol = 'BTC/USDT'
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
        # Validate amount
        validate_transaction_amount(usd_amount, settings.dca.max_transaction_limit)

        ticker = self.get_ticker()
        current_price = ticker['last']
        btc_amount = usd_amount / current_price

        # Format BTC amount according to OKX precision (typically 8 decimal places)
        btc_amount = round(btc_amount, 8)

        logger.info(f"Placing order: {btc_amount} BTC at ~{current_price} USDT")

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
            order = self.exchange.create_market_buy_order(self.symbol, btc_amount)
            logger.info(f"Order placed successfully: {order['id']}")

            # Get actual executed amounts from the order
            filled_btc = float(order['filled'])
            cost = float(order['cost'])
            actual_price = cost / filled_btc if filled_btc > 0 else current_price

            return {
                'success': True,
                'order_id': order['id'],
                'btc_amount': filled_btc,
                'usd_amount': cost,
                'price': actual_price
            }

        except Exception as e:
            logger.error(f"Error placing order: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def calculate_days_left(self) -> Tuple[float, int]:
        """Calculate how many days of DCA are left based on USDT balance."""
        balance = self.get_account_balance()
        usdt_balance = balance['USDT']

        daily_amount = settings.dca.amount_usd
        days_left = int(usdt_balance / daily_amount) if daily_amount > 0 else 0

        return usdt_balance, days_left

    def get_current_price(self) -> float:
        """Get current BTC price in USDT."""
        ticker = self.get_ticker()
        return ticker['last']


# Singleton instance
okx = OKXExchange(
    api_key=settings.okx.api_key,
    api_secret=settings.okx.api_secret,
    api_passphrase=settings.okx.api_passphrase,
    subaccount_name=settings.okx.subaccount_name,
    dry_run=settings.dry_run
)
