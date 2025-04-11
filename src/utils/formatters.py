from typing import Dict, Any, Tuple, List
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


def format_money(amount: float, decimals: int = 1) -> str:
    """Format money amount with comma as thousands separator and specified decimal places.
       Handles negative sign correctly.
    """
    # Format using f-string with comma separator
    formatted = f"{abs(amount):,.{decimals}f}"
    # Prepend negative sign if needed
    return f"-${formatted}" if amount < 0 else f"${formatted}"


def format_btc(amount: float, decimals: int = 5) -> str:
    """Format BTC amount with specified decimal places (default 5)."""
    return f"{amount:.{decimals}f}"


def format_percentage(value: float, decimals: int = 1) -> str:
    """Format percentage value with 1 decimal place."""
    # Ensure the % sign is appended correctly
    formatted_value = f"{value:.{decimals}f}"
    return f"{formatted_value}%"


def format_trade_notification(
    trade: Dict[str, Any],
    stats: Dict[str, Any],
    current_price: float,
    usdt_balance: float,
    next_trade_time: Tuple[int, int]
) -> str:
    """
    Format trade notification message in HTML.

    Args:
        trade: Trade details
        stats: Trading statistics
        current_price: Current BTC price
        usdt_balance: USDT balance
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
• Amount: <code>{format_money(trade['usd_amount'])}</code>
• BTC Received: <code>{format_btc(trade['btc_amount'])}</code>
• Price: <code>{format_money(trade['price'])}</code>

<b>Schedule:</b>
{next_trade_info}

<b>Overall Performance:</b>
• PnL: <code>{format_money(pnl, 2)}</code> ({format_percentage(pnl_percent)})

<blockquote expandable>
<b>Portfolio Summary:</b>
• Total Invested: <code>{format_money(stats['total_spent_usd'])}</code>
{portfolio_info_details}
• Average Price: <code>{format_money(stats['mean_price'], 2)}</code>
• Current Price: <code>{format_money(current_price, 2)}</code>
• Total Trades: <code>{stats['num_trades']}</code>
</blockquote >

<b>Balance:</b>
• USDT Remaining: <code>{format_money(usdt_balance, 2)}</code>
"""
    return message


def format_stats_message(
    stats: Dict[str, Any],
    current_price: float,
    usdt_balance: float,
    days_left: int,
    amount_per_original_unit: float,
    original_unit_name: str, # Likely 'day'
    next_trade_time: Tuple[int, int]
) -> str:
    """
    Format statistics message in HTML.

    Args:
        stats: Trading statistics
        current_price: Current BTC price
        usdt_balance: USDT balance
        days_left: Total days the schedule can run with current balance.
        amount_per_original_unit: The configured amount per the original schedule unit (e.g., per day).
        original_unit_name: The name of the original schedule unit (e.g., 'day').
        next_trade_time: Tuple of (hours, minutes) until next trade

    Returns:
        str: Formatted HTML message
    """
    # Estimate end date based on days_left
    end_date = datetime.now() + timedelta(days=days_left)

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
• Average Price: <code>{format_money(initial_portfolio["avg_price"], 2)}</code>
• Initial Investment: <code>{format_money(initial_portfolio["investment"], 2)}</code>
• PnL: <code>{format_money(initial_pnl, 2)}</code> ({format_percentage(initial_pnl_percent)})
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
• Invested: <code>{format_money(dca_investment)}</code>
• BTC Accumulated: <code>{format_btc(dca_btc)}</code>
• Average Price: <code>{format_money(dca_avg_price, 2)}</code>
• PnL: <code>{format_money(dca_pnl, 2)}</code> ({format_percentage(dca_pnl_percent)})
"""

    # --- Assemble Main Message ---
    message = f"""
<b>📊 Your Bitcoin Portfolio Statistics</b>

<b>Overall Summary:</b>
• Total Investment: <code>{format_money(stats['total_spent_usd'])}</code>
• Total BTC: <code>{format_btc(stats['total_btc'])}</code>
• Average Price: <code>{format_money(stats['mean_price'], 2)}</code>
• Current Price: <code>{format_money(current_price, 2)}</code>
• Current Value: <code>{format_money(stats['total_btc'] * current_price, 2)}</code>
• Total PnL: <code>{format_money(overall_pnl, 2)}</code> ({format_percentage(overall_pnl_percent)})

<b>Schedule:</b>
{next_trade_info}

<blockquote expandable>
{initial_portfolio_section}{dca_section}{trading_activity}
</blockquote >

<b>Balance:</b>
• USDT Remaining: <code>{format_money(usdt_balance, 2)}</code>
• Days Left: <code>{days_left}</code> (at {format_money(amount_per_original_unit)}/{original_unit_name})
• Estimated End Date: <code>{end_date.strftime('%Y-%m-%d %H:%M')}</code>
"""
    return message


def format_trade_summary_notification(
    trades: List[Dict[str, Any]],
    period_start: datetime,
    period_end: datetime,
    stats: Dict[str, Any],
    current_price: float,
    usdt_balance: float,
    next_trade_time: Tuple[int, int],
    title: str = "📊 <b>Trade Summary</b>"
) -> str:
    """Format trade summary notification message."""
    # Title section
    message = f"{title}\n\n"
    num_trades = len(trades)

    # Calculate duration
    duration_timedelta = period_end - period_start
    duration_hours = round(duration_timedelta.total_seconds() / 3600)

    # Format period for title
    start_str = period_start.strftime("%H:%M %d-%b")
    end_str = period_end.strftime("%H:%M %d-%b")
    period_str = f"{start_str} - {end_str}"

    # If period is within the last 24 hours, use "last X hours" format
    if duration_hours <= 24:
        period_str = f"last {duration_hours} hours"

    if num_trades == 0:
        return f"""{message}
No trades executed in this period.

<b>Balance:</b>
• USDT Remaining: <code>{format_money(usdt_balance, 2)}</code>
        """

    total_usd_spent = sum(t['usd_amount'] for t in trades)
    total_btc_bought = sum(t['btc_amount'] for t in trades)
    avg_price_period = total_usd_spent / total_btc_bought if total_btc_bought > 0 else 0

    # Sort trades by timestamp in reverse order (newest first)
    sorted_trades = sorted(trades, key=lambda t: t['timestamp'], reverse=True)

    # Group trades by day
    trade_list_str = ""
    current_day = None

    for trade in sorted_trades:
        trade_day = trade['timestamp'].date()
        trade_time = trade['timestamp'].strftime('%H:%M')

        # Add day separator if we're on a new day
        if trade_day != current_day:
            current_day = trade_day
            if trade_list_str:  # Don't add separator before the first group
                trade_list_str += "  ----------------------\n"
            trade_list_str += f"  📅 {trade_day.strftime('%d %b %Y')}:\n"

        # Add trade details
        trade_list_str += f"    • <code>{trade_time}</code>: {format_money(trade['usd_amount'])} → {format_btc(trade['btc_amount'], 6)} @ {format_money(trade['price'])}\n"

    # Calculate Overall PnL
    overall_pnl = (current_price - stats["mean_price"]) * stats["total_btc"]
    overall_pnl_percent = (current_price / stats["mean_price"] - 1) * 100 if stats["mean_price"] > 0 else 0

    # Format next trade info
    hours, minutes = next_trade_time
    next_trade_info = f"in {hours} hours {minutes} minutes"

    # Calculate average statistics for this period
    period_avg_str = ""
    if num_trades > 0:
        period_avg_str = f"\nAverage price: <code>{format_money(avg_price_period)}</code> • Average per trade: <code>{format_money(total_usd_spent/num_trades)}</code>"

    message += f"""
Executed <code>{num_trades}</code> trades totalling <code>{format_money(total_usd_spent)}</code>.{period_avg_str}

<b>Trades List</b> (tap to expand):
<blockquote expandable>
<pre>
{trade_list_str}
</pre>
</blockquote>

<b>Overall Performance:</b>
• PnL: <code>{format_money(overall_pnl, 2)}</code> ({format_percentage(overall_pnl_percent)})
• Total Invested: <code>{format_money(stats['total_spent_usd'])}</code>
• Total BTC: <code>{format_btc(stats['total_btc'])}</code>
• Average Price: <code>{format_money(stats['mean_price'], 2)}</code>

<b>Schedule & Balance:</b>
• Next Trade: <code>{next_trade_info}</code>
• USDT Remaining: <code>{format_money(usdt_balance, 2)}</code>
    """
    return message
