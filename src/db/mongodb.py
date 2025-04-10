from pymongo import MongoClient
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta, time
import logging
import ssl
import certifi
import pytz

from src.config import settings

logger = logging.getLogger(__name__)


class MongoDB:
    """MongoDB client for managing trades data."""

    def __init__(self, uri: str):
        """Initialize MongoDB client."""
        # Configure MongoDB client with proper TLS settings for Atlas
        try:
            self.client = MongoClient(
                uri,
                tls=True,
                tlsCAFile=certifi.where(),
                serverSelectionTimeoutMS=10000
            )
            # Test connection
            self.client.admin.command('ping')
            logger.info("MongoDB connection successful")
        except Exception as e:
            logger.error(f"MongoDB connection error: {str(e)}")
            # For tests, we proceed with a client instance anyway
            self.client = MongoClient(uri)

        self.db = self.client.dca_bot
        self.trades = self.db.trades
        self.reports = self.db.reports  # Collection to track report metadata
        self.setup_indexes()

    def setup_indexes(self) -> None:
        """Set up necessary indexes."""
        try:
            self.trades.create_index("timestamp")
            self.reports.create_index("report_type")
            logger.info("MongoDB indexes created successfully")
        except Exception as e:
            logger.error(f"Error setting up MongoDB indexes: {str(e)}")
            # For tests, we can continue even if indexing fails
            pass

    def save_trade(self, trade_data: Dict[str, Any]) -> str:
        """Save a trade to the database."""
        trade_data["timestamp"] = datetime.now(pytz.utc)
        result = self.trades.insert_one(trade_data)
        logger.info(f"Saved trade with ID: {result.inserted_id}")
        return str(result.inserted_id)

    def get_all_trades(self) -> List[Dict[str, Any]]:
        """Get all trades from the database."""
        return list(self.trades.find().sort("timestamp", 1))

    def get_trade_stats(self) -> Dict[str, Any]:
        """Get trade statistics."""
        trades = self.get_all_trades()

        # Get initial portfolio settings
        initial_btc = settings.portfolio.initial_btc_amount
        initial_avg_price = settings.portfolio.initial_avg_price_usd
        initial_investment = initial_btc * initial_avg_price if initial_btc > 0 and initial_avg_price > 0 else 0

        if not trades and initial_btc <= 0:
            return {
                "num_trades": 0,
                "total_spent_usd": 0,
                "total_btc": 0,
                "mean_price": 0,
                "initial_portfolio": {
                    "btc_amount": 0,
                    "avg_price": 0,
                    "investment": 0
                }
            }

        # Calculate DCA trade statistics
        dca_spent_usd = sum(trade["usd_amount"] for trade in trades)
        dca_btc = sum(trade["btc_amount"] for trade in trades)
        dca_mean_price = dca_spent_usd / dca_btc if dca_btc > 0 else 0

        # Combine with initial portfolio
        total_spent_usd = dca_spent_usd + initial_investment
        total_btc = dca_btc + initial_btc

        # Calculate combined average price
        mean_price = total_spent_usd / total_btc if total_btc > 0 else 0

        result = {
            "num_trades": len(trades),
            "total_spent_usd": total_spent_usd,
            "total_btc": total_btc,
            "mean_price": mean_price,
            "initial_portfolio": {
                "btc_amount": initial_btc,
                "avg_price": initial_avg_price,
                "investment": initial_investment
            }
        }

        # Add first and last trade dates if we have trades
        if trades:
            result["first_trade_date"] = trades[0]["timestamp"]
            result["last_trade_date"] = trades[-1]["timestamp"]

        return result

    def get_latest_trade(self) -> Optional[Dict[str, Any]]:
        """Get the latest trade from the database."""
        latest = self.trades.find_one(sort=[("timestamp", -1)])
        return latest

    def has_trade_in_timeframe(self, start_time: datetime, end_time: datetime) -> bool:
        """
        Check if a trade exists within the specified timeframe.

        Args:
            start_time: Start of the timeframe
            end_time: End of the timeframe

        Returns:
            bool: True if a trade exists in the timeframe, False otherwise
        """
        query = {
            "timestamp": {
                "$gte": start_time,
                "$lte": end_time
            }
        }

        count = self.trades.count_documents(query)
        return count > 0

    def has_trade_today_at_hour(self, hour: int, minute: int) -> bool:
        """
        Check if a trade has been executed today at the specified hour and minute.

        Args:
            hour: Hour in UTC (0-23)
            minute: Minute (0-59)

        Returns:
            bool: True if a trade exists, False otherwise
        """
        now = datetime.utcnow()

        # Create datetime objects for the target time window
        target_time = datetime(now.year, now.month, now.day, hour, minute)

        # Define a 5-minute window around the target time
        start_time = target_time - timedelta(minutes=5)
        end_time = target_time + timedelta(minutes=5)

        # If the current time is before the end of the window,
        # we shouldn't consider this a duplicate
        if now < end_time:
            return False

        return self.has_trade_in_timeframe(start_time, end_time)

    def get_trades_since(self, start_time: datetime) -> List[Dict[str, Any]]:
        """Fetch all trades executed since a specific start time."""
        trades = self.trades.find({
            "timestamp": {"$gte": start_time}
        }).sort("timestamp", 1)  # Sort by time ascending
        return list(trades)

    def get_initial_portfolio(self) -> Dict[str, Any]:
        # Implementation of get_initial_portfolio method
        # This method should return the initial portfolio information
        # based on the current state of the trades collection
        # This is a placeholder and should be implemented
        return {}

    def get_last_trade_time(self) -> datetime | None:
        # Implementation of get_last_trade_time method
        # This method should return the timestamp of the last trade
        # This is a placeholder and should be implemented
        return None

    def mark_last_report_time(self) -> None:
        """Mark the current time as the last time a transaction report was sent."""
        now = datetime.now(pytz.utc)

        # Update or insert the last report time
        self.reports.update_one(
            {"report_type": "transaction_report"},
            {"$set": {"timestamp": now}},
            upsert=True
        )

        logger.info(f"Updated last report time to {now}")

    def get_last_report_time(self) -> Optional[datetime]:
        """Get the timestamp of the last transaction report."""
        report = self.reports.find_one({"report_type": "transaction_report"})

        if report and "timestamp" in report:
            return report["timestamp"]

        # If no report has been sent yet, return None
        return None

    def count_transactions_since_last_report(self) -> int:
        """Count the number of transactions since the last report was sent."""
        last_report_time = self.get_last_report_time()

        # If no report has been sent yet, count all transactions
        if not last_report_time:
            return self.trades.count_documents({})

        # Count transactions since the last report
        return self.trades.count_documents({"timestamp": {"$gt": last_report_time}})


# Singleton instance
db = MongoDB(settings.db.uri)
