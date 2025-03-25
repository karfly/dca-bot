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

    # Include portfolio information
    portfolio_info = ""
    if stats["initial_portfolio"]["btc_amount"] > 0:
        initial_btc = stats["initial_portfolio"]["btc_amount"]
        dca_btc = stats["total_btc"] - initial_btc
        portfolio_info = f"• DCA BTC: <code>{format_btc(dca_btc)}</code> (+ initial {format_btc(initial_btc)})"
    else:
        portfolio_info = f"• Total BTC: <code>{format_btc(stats['total_btc'])}</code>"

    message = f"""
<b>🎉 New Bitcoin Purchase Completed!</b>

<b>Trade Details:</b>
• Amount: <code>${format_money(trade['usd_amount'])}</code>
• BTC Received: <code>{format_btc(trade['btc_amount'])}</code>
• Price: <code>${format_money(trade['price'])}</code>

<b>Portfolio Summary:</b>
• Total Invested: <code>${format_money(stats['total_spent_usd'])}</code>
{portfolio_info}
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
    if stats["num_trades"] == 0 and stats["initial_portfolio"]["btc_amount"] <= 0:
        return "<b>No trades yet.</b> Start your DCA journey!"

    # Calculate PnL
    pnl = (current_price - stats["mean_price"]) * stats["total_btc"]
    pnl_percent = (current_price / stats["mean_price"] - 1) * 100 if stats["mean_price"] > 0 else 0

    # Estimate end date
    end_date = datetime.now() + timedelta(days=days_left)

    # Calculate days since first trade
    days_since_start = 0
    trades_per_week = 0

    if stats["num_trades"] > 0 and "first_trade_date" in stats:
        days_since_start = (datetime.now() - stats["first_trade_date"]).days
        # Calculate DCA frequency (trades per week on average)
        weeks = max(1, days_since_start / 7)
        trades_per_week = stats["num_trades"] / weeks

    # Initial portfolio section
    initial_portfolio = stats["initial_portfolio"]
    initial_portfolio_section = ""

    if initial_portfolio["btc_amount"] > 0:
        initial_pnl = (current_price - initial_portfolio["avg_price"]) * initial_portfolio["btc_amount"]
        initial_pnl_percent = (current_price / initial_portfolio["avg_price"] - 1) * 100

        initial_portfolio_section = f"""
<b>Initial Portfolio:</b>
• BTC Amount: <code>{format_btc(initial_portfolio["btc_amount"])}</code>
• Average Price: <code>${format_money(initial_portfolio["avg_price"], 2)}</code>
• Initial Investment: <code>${format_money(initial_portfolio["investment"], 2)}</code>
• PnL: <code>${format_money(initial_pnl, 2)}</code> ({format_percentage(initial_pnl_percent)})
"""

    # DCA section
    dca_section = ""
    if stats["num_trades"] > 0:
        dca_btc = stats["total_btc"] - initial_portfolio["btc_amount"]
        dca_investment = stats["total_spent_usd"] - initial_portfolio["investment"]
        dca_avg_price = dca_investment / dca_btc if dca_btc > 0 else 0
        dca_pnl = (current_price - dca_avg_price) * dca_btc if dca_btc > 0 else 0
        dca_pnl_percent = (current_price / dca_avg_price - 1) * 100 if dca_avg_price > 0 else 0

        dca_section = f"""
<b>DCA Strategy:</b>
• Invested: <code>${format_money(dca_investment)}</code>
• BTC Accumulated: <code>{format_btc(dca_btc)}</code>
• Average Price: <code>${format_money(dca_avg_price, 2)}</code>
• PnL: <code>${format_money(dca_pnl, 2)}</code> ({format_percentage(dca_pnl_percent)})
"""

    # Trading activity section
    trading_activity = ""
    if stats["num_trades"] > 0:
        trading_activity = f"""
<b>Trading Activity:</b>
• First Trade: <code>{stats['first_trade_date'].strftime('%Y-%m-%d')}</code>
• Latest Trade: <code>{stats['last_trade_date'].strftime('%Y-%m-%d')}</code>
• Total Trades: <code>{stats['num_trades']}</code>
• Average Frequency: <code>{trades_per_week:.1f}</code> trades/week
"""

    message = f"""
<b>📊 Your Bitcoin Portfolio Statistics</b>

<b>Overall Summary:</b>
• Total Investment: <code>${format_money(stats['total_spent_usd'])}</code>
• Total BTC: <code>{format_btc(stats['total_btc'])}</code>
• Average Price: <code>${format_money(stats['mean_price'], 2)}</code>
• Current Price: <code>${format_money(current_price, 2)}</code>
• Current Value: <code>${format_money(stats['total_btc'] * current_price, 2)}</code>
• Total PnL: <code>${format_money(pnl, 2)}</code> ({format_percentage(pnl_percent)})
{initial_portfolio_section}{dca_section}{trading_activity}
<b>Balance:</b>
• USDT Remaining: <code>${format_money(usdt_balance, 2)}</code>
• Days Left: <code>{days_left}</code>
• Estimated End Date: <code>{end_date.strftime('%Y-%m-%d')}</code>
"""
    return message
