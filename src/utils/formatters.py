from typing import Dict, Any
from datetime import datetime, timedelta
import locale
from decimal import Decimal, ROUND_DOWN

# Set locale for currency formatting
locale.setlocale(locale.LC_ALL, '')


def format_money(amount: float, decimals: int = 2) -> str:
    """Format money amount with comma as thousands separator."""
    return f"{amount:,.{decimals}f}"


def format_btc(amount: float) -> str:
    """Format BTC amount with 8 decimal places."""
    return f"{amount:.8f}"


def format_percentage(value: float) -> str:
    """Format percentage value."""
    return f"{value:.2f}%"


def format_trade_notification(
    trade: Dict[str, Any],
    stats: Dict[str, Any],
    current_price: float,
    usdt_balance: float,
    days_left: int
) -> str:
    """
    Format trade notification message in HTML.

    Args:
        trade: Trade details
        stats: Trading statistics
        current_price: Current BTC price
        usdt_balance: USDT balance
        days_left: Days left based on balance

    Returns:
        str: Formatted HTML message
    """
    # Calculate PnL
    pnl = 0
    pnl_percent = 0

    if stats["mean_price"] > 0:
        pnl = (current_price - stats["mean_price"]) * stats["total_btc"]
        pnl_percent = (current_price / stats["mean_price"] - 1) * 100

    # Estimate end date
    end_date = datetime.now() + timedelta(days=days_left)

    message = f"""
<b>🎉 New Bitcoin Purchase Completed!</b>

<b>Trade Details:</b>
• Amount: <code>${format_money(trade['usd_amount'])}</code>
• BTC Received: <code>{format_btc(trade['btc_amount'])}</code>
• Price: <code>${format_money(trade['price'])}</code>

<b>Portfolio Summary:</b>
• Total Invested: <code>${format_money(stats['total_spent_usd'])}</code>
• Total BTC: <code>{format_btc(stats['total_btc'])}</code>
• Average Price: <code>${format_money(stats['mean_price'], 2)}</code>
• Current Price: <code>${format_money(current_price, 2)}</code>
• Total Trades: <code>{stats['num_trades']}</code>

<b>Performance:</b>
• PnL: <code>${format_money(pnl, 2)}</code> ({format_percentage(pnl_percent)})

<b>Balance:</b>
• USDT Remaining: <code>${format_money(usdt_balance, 2)}</code>
• Days Left: <code>{days_left}</code>
• Estimated End Date: <code>{end_date.strftime('%Y-%m-%d')}</code>
"""
    return message


def format_stats_message(
    stats: Dict[str, Any],
    current_price: float,
    usdt_balance: float,
    days_left: int
) -> str:
    """
    Format statistics message in HTML.

    Args:
        stats: Trading statistics
        current_price: Current BTC price
        usdt_balance: USDT balance
        days_left: Days left based on balance

    Returns:
        str: Formatted HTML message
    """
    if stats["num_trades"] == 0:
        return "<b>No trades yet.</b> Start your DCA journey!"

    # Calculate PnL
    pnl = (current_price - stats["mean_price"]) * stats["total_btc"]
    pnl_percent = (current_price / stats["mean_price"] - 1) * 100

    # Estimate end date
    end_date = datetime.now() + timedelta(days=days_left)

    # Calculate days since first trade
    days_since_start = (datetime.now() - stats["first_trade_date"]).days

    # Calculate DCA frequency (trades per week on average)
    weeks = max(1, days_since_start / 7)
    trades_per_week = stats["num_trades"] / weeks

    message = f"""
<b>📊 Your Bitcoin DCA Statistics</b>

<b>Overall:</b>
• Total Invested: <code>${format_money(stats['total_spent_usd'])}</code>
• Total BTC: <code>{format_btc(stats['total_btc'])}</code>
• Average Price: <code>${format_money(stats['mean_price'], 2)}</code>
• Current Price: <code>${format_money(current_price, 2)}</code>

<b>Trading Activity:</b>
• First Trade: <code>{stats['first_trade_date'].strftime('%Y-%m-%d')}</code>
• Latest Trade: <code>{stats['last_trade_date'].strftime('%Y-%m-%d')}</code>
• Total Trades: <code>{stats['num_trades']}</code>
• Average Frequency: <code>{trades_per_week:.1f}</code> trades/week

<b>Performance:</b>
• Current Value: <code>${format_money(stats['total_btc'] * current_price, 2)}</code>
• PnL: <code>${format_money(pnl, 2)}</code> ({format_percentage(pnl_percent)})

<b>Balance:</b>
• USDT Remaining: <code>${format_money(usdt_balance, 2)}</code>
• Days Left: <code>{days_left}</code>
• Estimated End Date: <code>{end_date.strftime('%Y-%m-%d')}</code>
"""
    return message
