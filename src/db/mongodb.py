from pymongo import MongoClient
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import logging

from src.config import settings

logger = logging.getLogger(__name__)


class MongoDB:
    """MongoDB client for managing trades data."""

    def __init__(self, uri: str):
        """Initialize MongoDB client."""
        self.client = MongoClient(uri)
        self.db = self.client.dca_bot
        self.trades = self.db.trades
        self.setup_indexes()

    def setup_indexes(self) -> None:
        """Set up necessary indexes."""
        self.trades.create_index("timestamp")

    def save_trade(self, trade_data: Dict[str, Any]) -> str:
        """Save a trade to the database."""
        trade_data["timestamp"] = datetime.utcnow()
        result = self.trades.insert_one(trade_data)
        logger.info(f"Saved trade with ID: {result.inserted_id}")
        return str(result.inserted_id)

    def get_all_trades(self) -> List[Dict[str, Any]]:
        """Get all trades from the database."""
        return list(self.trades.find().sort("timestamp", 1))

    def get_trade_stats(self) -> Dict[str, Any]:
        """Get trade statistics."""
        trades = self.get_all_trades()

        if not trades:
            return {
                "num_trades": 0,
                "total_spent_usd": 0,
                "total_btc": 0,
                "mean_price": 0,
            }

        total_spent_usd = sum(trade["usd_amount"] for trade in trades)
        total_btc = sum(trade["btc_amount"] for trade in trades)
        mean_price = total_spent_usd / total_btc if total_btc > 0 else 0

        return {
            "num_trades": len(trades),
            "total_spent_usd": total_spent_usd,
            "total_btc": total_btc,
            "mean_price": mean_price,
            "first_trade_date": trades[0]["timestamp"],
            "last_trade_date": trades[-1]["timestamp"],
        }

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


# Singleton instance
db = MongoDB(settings.db.uri)
