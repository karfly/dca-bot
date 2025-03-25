#!/usr/bin/env python3
"""
Production environment tests.
Run these tests to verify basic functionality in the production environment.
"""

import logging
import sys
import time
import datetime
import random
import pytest
import certifi
from pymongo import MongoClient
from pydantic import BaseModel
import ccxt

from src.config import settings
from src.exchange.okx import okx
from src.bot.telegram import telegram_bot
from src.db.mongodb import db

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


class TestOKX:
    """Tests for OKX exchange integration"""

    @pytest.mark.skipif(settings.dry_run, reason="Skipping actual trade test in dry run mode")
    def test_btc_buy_sell(self):
        """Test buying Bitcoin for $1 and selling the received amount"""
        logger.info("\n=== Starting OKX Buy/Sell Test ===")
        test_amount_usd = 1.0
        logger.info(f"Test parameters: Buy amount = {test_amount_usd} USDT")

        # Get current price
        current_price = okx.get_current_price()
        logger.info(f"Current BTC price: {current_price} USDT")
        expected_btc_amount = round(test_amount_usd / current_price, 8)
        logger.info(f"Expected BTC amount (without fees): ~{expected_btc_amount}")

        # Get BTC balance before
        balances_before = okx.get_account_balance()
        btc_before = balances_before.get('BTC', 0)
        usdt_before = balances_before.get('USDT', 0)
        logger.info(f"Initial balances: BTC={btc_before:.8f}, USDT={usdt_before:.2f}")

        try:
            # Buy BTC with $1
            logger.info("\n--- Executing Buy Order ---")
            buy_result = okx.buy_bitcoin(test_amount_usd)
            logger.info(f"Buy order details:")
            logger.info(f"- Order ID: {buy_result['order_id']}")
            logger.info(f"- BTC amount: {buy_result['btc_amount']:.8f}")
            logger.info(f"- USDT spent: {buy_result['usd_amount']:.2f}")
            logger.info(f"- Execution price: {buy_result['price']:.2f} USDT/BTC")

            # Wait for order to settle
            logger.info("\nWaiting for order to settle...")
            time.sleep(5)

            # Get BTC balance after buy to verify the trade worked
            balances_after_buy = okx.get_account_balance()
            btc_after_buy = balances_after_buy.get('BTC', 0)
            usdt_after_buy = balances_after_buy.get('USDT', 0)
            btc_amount = btc_after_buy - btc_before
            usdt_spent = usdt_before - usdt_after_buy

            logger.info("\nPost-buy balances and changes:")
            logger.info(f"- BTC balance: {btc_after_buy:.8f} (Δ: {btc_amount:+.8f})")
            logger.info(f"- USDT balance: {usdt_after_buy:.2f} (Δ: {-usdt_spent:+.2f})")

            assert btc_amount > 0, f"BTC amount should have increased after purchase (Δ: {btc_amount:.8f})"
            assert abs(usdt_spent - test_amount_usd) < 0.1, f"USDT spent should be close to test amount (spent: {usdt_spent:.2f}, expected: {test_amount_usd})"

            # Sell the BTC back
            logger.info("\n--- Executing Sell Order ---")
            btc_amount = round(btc_amount, 8)  # Format to OKX precision
            logger.info(f"Selling BTC amount: {btc_amount:.8f}")

            sell_order = okx.exchange.create_market_sell_order(okx.symbol, btc_amount)
            logger.info(f"Sell order placed:")
            logger.info(f"- Order ID: {sell_order['id']}")
            logger.info(f"- Amount: {sell_order.get('amount', 'N/A')}")
            logger.info(f"- Price: {sell_order.get('price', 'N/A')}")

            # Wait for order to settle
            logger.info("\nWaiting for order to settle...")
            time.sleep(5)

            # Get balance after sell
            balances_after_sell = okx.get_account_balance()
            btc_after_sell = balances_after_sell.get('BTC', 0)
            usdt_after_sell = balances_after_sell.get('USDT', 0)
            btc_change = btc_after_sell - btc_before
            usdt_change = usdt_after_sell - usdt_before

            logger.info("\nFinal balances and changes from initial state:")
            logger.info(f"- BTC: {btc_after_sell:.8f} (Δ: {btc_change:+.8f})")
            logger.info(f"- USDT: {usdt_after_sell:.2f} (Δ: {usdt_change:+.2f})")

            # The final BTC balance should be close to the original
            btc_diff = abs(btc_after_sell - btc_before)
            assert btc_diff < 0.00001, f"Final BTC balance should be close to original (diff: {btc_diff:.8f})"

            # Calculate total fees paid in USDT
            total_fee_usdt = abs(usdt_change)
            logger.info(f"\nTotal fees paid: ~{total_fee_usdt:.4f} USDT")

            logger.info("\n=== OKX Buy/Sell Test Completed Successfully ===")

        except ccxt.PermissionDenied as e:
            logger.error("\n❌ Test failed: Permission denied")
            logger.error(f"Error details: {str(e)}")
            logger.error("Please check that your API key has trading permissions enabled")
            raise pytest.fail("Test failed: API key doesn't have required permissions")
        except ccxt.InsufficientFunds as e:
            logger.error("\n❌ Test failed: Insufficient funds")
            logger.error(f"Error details: {str(e)}")
            logger.error(f"Required: {test_amount_usd} USDT, Available: {usdt_before} USDT")
            raise pytest.fail("Test failed: Insufficient funds for trade")
        except ccxt.ExchangeError as e:
            logger.error("\n❌ Test failed: Exchange error")
            logger.error(f"Error details: {str(e)}")
            raise pytest.fail(f"Test failed: Exchange error - {str(e)}")
        except Exception as e:
            logger.error("\n❌ Test failed: Unexpected error")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error details: {str(e)}")
            raise pytest.fail(f"Test failed: Unexpected error - {str(e)}")


class TestTelegram:
    """Tests for Telegram integration"""

    @pytest.mark.asyncio
    async def test_telegram_notification(self):
        """Test sending a notification to Telegram"""
        logger.info("\n=== Starting Telegram Notification Test ===")

        # Create test message
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        test_message = f"""
<b>🧪 Test Notification</b>

This is a test message from the Bitcoin DCA Bot.
Time: {timestamp}
Environment: Production
        """
        logger.info("Prepared test message:")
        logger.info(test_message)

        try:
            # Send message
            logger.info("\nSending message to Telegram...")
            await telegram_bot.application.bot.send_message(
                chat_id=settings.telegram.user_id,
                text=test_message,
                parse_mode="HTML"
            )

            logger.info("✅ Message sent successfully")
            logger.info(f"- Chat ID: {settings.telegram.user_id}")
            logger.info("\n=== Telegram Test Completed Successfully ===")
            assert True, "Message sent successfully"

        except Exception as e:
            logger.error("\n❌ Telegram test failed")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error details: {str(e)}")
            raise


class TestDatabase:
    """Tests for MongoDB integration"""

    def test_db_operations(self):
        """Test database connection and operations"""
        logger.info("\n=== Starting Database Operations Test ===")
        test_collection_name = f"test_{int(time.time())}"
        logger.info(f"Using test collection: {test_collection_name}")

        # Create test document
        test_doc = {
            "test_id": random.randint(1000, 9999),
            "timestamp": datetime.datetime.utcnow(),
            "message": "This is a test document",
            "is_test": True
        }
        logger.info("\nPrepared test document:")
        logger.info(f"- Test ID: {test_doc['test_id']}")
        logger.info(f"- Timestamp: {test_doc['timestamp']}")

        try:
            # Connect to the database
            logger.info("\nConnecting to MongoDB...")
            client = MongoClient(
                settings.db.uri,
                tls=True,
                tlsCAFile=certifi.where(),
                serverSelectionTimeoutMS=10000
            )

            # Test connection
            try:
                client.admin.command('ping')
                logger.info("✅ MongoDB connection successful")
            except Exception as e:
                logger.error("\n❌ MongoDB connection failed")
                logger.error(f"Error details: {str(e)}")
                pytest.skip(f"Skipping due to MongoDB connection issue: {str(e)}")

            test_db = client.dca_bot
            test_collection = test_db[test_collection_name]
            logger.info(f"Created test collection: {test_collection_name}")

            # Insert test document
            logger.info("\nInserting test document...")
            insert_result = test_collection.insert_one(test_doc)
            doc_id = insert_result.inserted_id
            logger.info(f"✅ Document inserted successfully")
            logger.info(f"- Document ID: {doc_id}")

            assert doc_id is not None, "Document ID should not be None"

            # Retrieve the document
            logger.info("\nRetrieving test document...")
            retrieved_doc = test_collection.find_one({"test_id": test_doc["test_id"]})
            assert retrieved_doc is not None, "Retrieved document should not be None"
            assert retrieved_doc["test_id"] == test_doc["test_id"], "Test IDs should match"

            logger.info("✅ Document retrieved successfully")
            logger.info(f"- Retrieved test_id: {retrieved_doc['test_id']}")
            logger.info(f"- Retrieved timestamp: {retrieved_doc['timestamp']}")

            # Clean up
            logger.info("\nCleaning up...")
            test_db.drop_collection(test_collection_name)
            logger.info(f"✅ Test collection dropped: {test_collection_name}")

            logger.info("\n=== Database Test Completed Successfully ===")

        except Exception as e:
            logger.error("\n❌ Database test failed")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error details: {str(e)}")
            pytest.skip(f"Skipping database test due to error: {str(e)}")


if __name__ == "__main__":
    sys.exit(pytest.main(["-v", __file__]))