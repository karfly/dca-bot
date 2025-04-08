from typing import Dict, Any, Tuple
from datetime import datetime, timedelta
import locale

# Set locale for currency formatting
try:
    locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'C.UTF-8') # Fallback for some systems
    except locale.Error:
        locale.setlocale(locale.LC_ALL, '') # System default as last resort


def format_money(amount: float, decimals: int = 2) -> str:
    """Format money amount with comma as thousands separator."""
    return locale.format_string(f"%.{decimals}f", amount, grouping=True)


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
    remaining_duration: Tuple[int, str, float, str], # (value, unit, amount_per_unit, unit_name)
    next_trade_time: Tuple[int, int]
) -> str:
    """
    Format trade notification message in HTML.

    Args:
        trade: Trade details
        stats: Trading statistics
        current_price: Current BTC price
        usdt_balance: USDT balance
        remaining_duration: Tuple (value, unit, amount_per_unit, unit_name)
        next_trade_time: Tuple of (hours, minutes) until next trade

    Returns:
        str: Formatted HTML message
    """
    # Calculate PnL
    pnl = 0
    pnl_percent = 0

    if stats["mean_price"] > 0:
        pnl = (current_price - stats["mean_price"]) * stats["total_btc"]
        pnl_percent = (current_price / stats["mean_price"] - 1) * 100

    # Unpack remaining duration
    remaining_value, unit, amount_per_unit, unit_name = remaining_duration
    unit_plural = unit_name + ("s" if remaining_value != 1 else "")

    # Estimate end date based on the actual unit
    end_date = datetime.now() + timedelta(**{unit: remaining_value})

    # Get time until next trade
    hours, minutes = next_trade_time
    next_trade_info = f"• Next Trade: <code>in {hours} hours {minutes} minutes</code>"

    # Include portfolio information for details block
    portfolio_info_details = ""
    if stats["initial_portfolio"]["btc_amount"] > 0:
        initial_btc = stats["initial_portfolio"]["btc_amount"]
        dca_btc = stats["total_btc"] - initial_btc
        portfolio_info_details = f"• DCA BTC: <code>{format_btc(dca_btc)}</code> (+ initial {format_btc(initial_btc)})"
    else:
        portfolio_info_details = f"• Total BTC: <code>{format_btc(stats['total_btc'])}</code>"

    message = f"""
<b>🎉 New Bitcoin Purchase Completed!</b>

<b>Trade Details:</b>
• Amount: <code>${format_money(trade['usd_amount'])}</code>
• BTC Received: <code>{format_btc(trade['btc_amount'])}</code>
• Price: <code>${format_money(trade['price'])}</code>

<b>Schedule:</b>
{next_trade_info}

<b>Overall Performance:</b>
• PnL: <code>${format_money(pnl, 2)}</code> ({format_percentage(pnl_percent)})

<blockquote expandable>
<b>Portfolio Summary:</b>
• Total Invested: <code>${format_money(stats['total_spent_usd'])}</code>
{portfolio_info_details}
• Average Price: <code>${format_money(stats['mean_price'], 2)}</code>
• Current Price: <code>${format_money(current_price, 2)}</code>
• Total Trades: <code>{stats['num_trades']}</code>
</blockquote >

<b>Balance:</b>
• USDT Remaining: <code>${format_money(usdt_balance, 2)}</code>
• {unit_plural.capitalize()} Left: <code>{remaining_value}</code> (at ${format_money(amount_per_unit)}/{unit_name})
• Estimated End Date: <code>{end_date.strftime('%Y-%m-%d %H:%M')}</code>
"""
    return message


def format_stats_message(
    stats: Dict[str, Any],
    current_price: float,
    usdt_balance: float,
    remaining_duration: Tuple[int, str, float, str], # (value, unit, amount_per_unit, unit_name)
    next_trade_time: Tuple[int, int]
) -> str:
    """
    Format statistics message in HTML.

    Args:
        stats: Trading statistics
        current_price: Current BTC price
        usdt_balance: USDT balance
        remaining_duration: Tuple (value, unit, amount_per_unit, unit_name)
        next_trade_time: Tuple of (hours, minutes) until next trade

    Returns:
        str: Formatted HTML message
    """
    # Unpack remaining duration
    remaining_value, unit, amount_per_unit, unit_name = remaining_duration
    unit_plural = unit_name + ("s" if remaining_value != 1 else "")

    # Estimate end date based on the actual unit
    end_date = datetime.now() + timedelta(**{unit: remaining_value})

    # Get time until next trade
    hours, minutes = next_trade_time
    next_trade_info = f"• Next Trade: <code>in {hours} hours {minutes} minutes</code>"

    if stats["num_trades"] == 0 and stats["initial_portfolio"]["btc_amount"] <= 0:
        # Even for empty stats, show next trade time
        return f"""<b>No trades yet.</b> Start your DCA journey!

<b>Schedule:</b>
{next_trade_info}"""

    # Calculate Overall PnL
    overall_pnl = (current_price - stats["mean_price"]) * stats["total_btc"]
    overall_pnl_percent = (current_price / stats["mean_price"] - 1) * 100 if stats["mean_price"] > 0 else 0

    # Calculate days since first trade for Trading Activity
    days_since_start = 0
    trades_per_week = 0
    trading_activity = ""
    if stats["num_trades"] > 0 and "first_trade_date" in stats:
        days_since_start = (datetime.now() - stats["first_trade_date"]).days
        weeks = max(1, days_since_start / 7)
        trades_per_week = stats["num_trades"] / weeks
        trading_activity = f"""
<b>Trading Activity:</b>
• First Trade: <code>{stats['first_trade_date'].strftime('%Y-%m-%d')}</code>
• Latest Trade: <code>{stats['last_trade_date'].strftime('%Y-%m-%d')}</code>
• Total Trades: <code>{stats['num_trades']}</code>
• Average Frequency: <code>{trades_per_week:.1f}</code> trades/week
"""

    # Initial portfolio section
    initial_portfolio = stats["initial_portfolio"]
    initial_portfolio_section = ""
    if initial_portfolio["btc_amount"] > 0:
        initial_pnl = (current_price - initial_portfolio["avg_price"]) * initial_portfolio["btc_amount"]
        initial_pnl_percent = (current_price / initial_portfolio["avg_price"] - 1) * 100 if initial_portfolio["avg_price"] > 0 else 0
        initial_portfolio_section = f"""
<b>Initial Portfolio Details:</b>
• BTC Amount: <code>{format_btc(initial_portfolio["btc_amount"])}</code>
• Average Price: <code>${format_money(initial_portfolio["avg_price"], 2)}</code>
• Initial Investment: <code>${format_money(initial_portfolio["investment"], 2)}</code>
• PnL: <code>${format_money(initial_pnl, 2)}</code> ({format_percentage(initial_pnl_percent)})
"""

    # DCA section
    dca_section = ""
    if stats["num_trades"] > 0:
        dca_btc = stats["total_btc"] - initial_portfolio["btc_amount"]
        if dca_btc > 0.00000001: # Check if any BTC was actually bought via DCA
            dca_investment = stats["total_spent_usd"] - initial_portfolio["investment"]
            dca_avg_price = dca_investment / dca_btc if dca_btc > 0 else 0
            dca_pnl = (current_price - dca_avg_price) * dca_btc if dca_btc > 0 else 0
            dca_pnl_percent = (current_price / dca_avg_price - 1) * 100 if dca_avg_price > 0 else 0
            dca_section = f"""
<b>DCA Strategy Details:</b>
• Invested: <code>${format_money(dca_investment)}</code>
• BTC Accumulated: <code>{format_btc(dca_btc)}</code>
• Average Price: <code>${format_money(dca_avg_price, 2)}</code>
• PnL: <code>${format_money(dca_pnl, 2)}</code> ({format_percentage(dca_pnl_percent)})
"""

    # --- Assemble Main Message ---
    message = f"""
<b>📊 Your Bitcoin Portfolio Statistics</b>

<b>Overall Summary:</b>
• Total Investment: <code>${format_money(stats['total_spent_usd'])}</code>
• Total BTC: <code>{format_btc(stats['total_btc'])}</code>
• Average Price: <code>${format_money(stats['mean_price'], 2)}</code>
• Current Price: <code>${format_money(current_price, 2)}</code>
• Current Value: <code>${format_money(stats['total_btc'] * current_price, 2)}</code>
• Total PnL: <code>${format_money(overall_pnl, 2)}</code> ({format_percentage(overall_pnl_percent)})

<b>Schedule:</b>
{next_trade_info}

<blockquote expandable>
{initial_portfolio_section}{dca_section}{trading_activity}
</blockquote >

<b>Balance:</b>
• USDT Remaining: <code>${format_money(usdt_balance, 2)}</code>
• {unit_plural.capitalize()} Left: <code>{remaining_value}</code> (at ${format_money(amount_per_unit)}/{unit_name})
• Estimated End Date: <code>{end_date.strftime('%Y-%m-%d %H:%M')}</code>
"""
    return message
