import argparse
import sys
from datetime import datetime, timezone

from config import ensure_sdk, get_api_secret, get_account_id, create_client

# Install/upgrade the pinned SDK before importing it (see config.SDK_VERSION).
ensure_sdk()
from public_api_sdk import (
    InstrumentType,
    OpenCloseIndicator,
    OrderInstrument,
    OrderSearchRequest,
    OrderSide,
    OrderStatus,
)

# The API returns at most this many orders per search, and only looks back 30 days.
MAX_RESULTS = 500
LOOKBACK_DAYS = 30


def _names(enum_cls, exclude=()):
    return [e.value for e in enum_cls if e not in exclude]


def parse_instrument(value, default_type="EQUITY"):
    """Parse a `SYMBOL` or `SYMBOL:TYPE` flag value into an OrderInstrument (same format as the CLI)."""
    symbol, separator, instrument_type = value.partition(":")
    symbol = symbol.strip().upper()
    instrument_type = instrument_type.strip().upper() if separator else default_type
    if not symbol or not instrument_type:
        raise ValueError(f"Invalid instrument {value!r}. Expected SYMBOL or SYMBOL:TYPE.")
    try:
        return OrderInstrument(symbol=symbol, type=InstrumentType(instrument_type))
    except ValueError:
        raise ValueError(
            f"Invalid instrument type {instrument_type!r} in {value!r}. "
            f"Expected one of: {', '.join(_names(InstrumentType))}"
        )


def parse_timestamp(value):
    """Parse `YYYY-MM-DD` or an ISO 8601 timestamp into a timezone-aware datetime.

    A bare date means midnight UTC; a timestamp without an offset is assumed to be UTC.
    A trailing `Z` is accepted (Python 3.9's fromisoformat does not understand it).
    """
    text = value.strip()
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(
            f"Invalid timestamp {value!r}. Use YYYY-MM-DD or ISO 8601, e.g. 2026-09-01T00:00:00Z."
        )
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def build_request(status=None, side=None, symbols=None, security_type=None,
                  open_close=None, created_after=None, created_before=None):
    """Turn the parsed flags into an OrderSearchRequest (only the given filters are set)."""
    filters = {}
    if status:
        filters["status"] = OrderStatus(status)
    if side:
        filters["side"] = OrderSide(side)
    if symbols:
        filters["instruments"] = [parse_instrument(s) for s in symbols]
    if security_type:
        filters["security_type"] = InstrumentType(security_type)
    if open_close:
        filters["open_close_indicator"] = OpenCloseIndicator(open_close)
    if created_after:
        filters["created_after"] = parse_timestamp(created_after)
    if created_before:
        filters["created_before"] = parse_timestamp(created_before)
    return OrderSearchRequest(**filters)


def _fmt_ts(value):
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else "n/a"


def _fmt_money(value):
    return f"${value:,.2f}" if value is not None else None


def search_orders(request, account_id=None):
    secret = get_api_secret()
    account_id = account_id or get_account_id()

    if not secret:
        print("Error: PUBLIC_COM_SECRET is not set.")
        sys.exit(1)

    if not account_id:
        print("Error: No account ID provided. Either pass --account-id or set PUBLIC_COM_ACCOUNT_ID.")
        sys.exit(1)

    try:
        client = create_client(secret, account_id)

        orders = client.search_orders(request, account_id=account_id)

        active_filters = request.model_dump(by_alias=True, exclude_none=True)

        print("=" * 78)
        print(f"ORDER SEARCH - Account: {account_id} — {len(orders)} order(s), last {LOOKBACK_DAYS} days")
        print("=" * 78)
        if active_filters:
            print("  Filters: " + ", ".join(f"{k}={v}" for k, v in active_filters.items()))
        else:
            print("  Filters: none (every order in the window)")

        if not orders:
            print("\n  No orders matched.")
            print("\n" + "=" * 78)
            client.close()
            return

        for order in orders:
            inst = order.instrument
            size = None
            if order.quantity is not None:
                size = f"Qty {order.quantity}"
            elif order.notional_value is not None:
                size = f"Notional {_fmt_money(order.notional_value)}"

            print(f"\n  📋 {order.order_id}")
            print(f"     {inst.symbol} ({inst.type.value})  {order.side.value} {order.type.value}  {order.status.value}")
            details = []
            if size:
                details.append(size)
            if order.limit_price is not None:
                details.append(f"Limit {_fmt_money(order.limit_price)}")
            if order.stop_price is not None:
                details.append(f"Stop {_fmt_money(order.stop_price)}")
            if order.filled_quantity is not None:
                filled = f"Filled {order.filled_quantity}"
                if order.average_price is not None:
                    filled += f" @ {_fmt_money(order.average_price)}"
                details.append(filled)
            if order.open_close_indicator is not None:
                details.append(order.open_close_indicator.value)
            if details:
                print(f"     {'  |  '.join(details)}")
            times = f"Created {_fmt_ts(order.created_at)}"
            if order.filled_at:
                times += f"  |  Filled {_fmt_ts(order.filled_at)}"
            elif order.closed_at:
                times += f"  |  Closed {_fmt_ts(order.closed_at)}"
            print(f"     {times}")
            if order.bracket_id:
                role = "entry" if order.bracket_id == order.order_id else "exit leg"
                print(f"     Bracket ID: {order.bracket_id} ({role})")
            if order.legs:
                legs = ", ".join(f"{leg.side.value} {leg.instrument.symbol}" for leg in order.legs)
                print(f"     Legs: {legs}")
            if order.trades:
                print(f"     Trades: {len(order.trades)} fill(s)")
            if order.reject_reason:
                print(f"     ⚠️  Reject Reason: {order.reject_reason}")

        print("\n  Use get_order_v2.py --order-id <ID> for an order's individual fills and timestamps.")
        if len(orders) >= MAX_RESULTS:
            print(f"  ⚠️  Result capped at {MAX_RESULTS} orders — narrow the filters (e.g. --created-after) to see the rest.")
        print("\n" + "=" * 78)

        client.close()
    except Exception as e:
        print(f"Error searching orders: {e}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=f"Search the last {LOOKBACK_DAYS} days of orders on your Public.com account "
                    f"(any status, up to {MAX_RESULTS} results) with optional filters",
        epilog="Examples:\n"
               "  Every order from the last 30 days:\n"
               "    python3 search_orders.py\n\n"
               "  Filled buys of AAPL since Sept 1:\n"
               "    python3 search_orders.py --status FILLED --side BUY --symbol AAPL --created-after 2026-09-01\n\n"
               "  Cancelled option orders in a window:\n"
               "    python3 search_orders.py --status CANCELLED --security-type OPTION \\\n"
               "      --created-after 2026-09-08T00:00:00Z --created-before 2026-09-15T00:00:00Z\n\n"
               "  Orders for several instruments (TYPE defaults to EQUITY):\n"
               "    python3 search_orders.py --symbol AAPL --symbol BTC:CRYPTO",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--status", choices=_names(OrderStatus, exclude=(OrderStatus.UNKNOWN,)),
                        help="Only orders currently in this status")
    parser.add_argument("--side", choices=_names(OrderSide), help="Only BUY or SELL orders")
    parser.add_argument("--symbol", action="append", metavar="SYMBOL[:TYPE]",
                        help="Only orders for this instrument; repeatable. TYPE defaults to EQUITY "
                             "(e.g. AAPL, BTC:CRYPTO, AAPL260918C00200000:OPTION)")
    parser.add_argument("--security-type", choices=_names(InstrumentType), help="Only orders for this security type")
    parser.add_argument("--open-close", choices=_names(OpenCloseIndicator),
                        help="Only opening or closing orders (options / short sales)")
    parser.add_argument("--created-after", metavar="TIMESTAMP",
                        help=f"Only orders created at or after this time (YYYY-MM-DD or ISO 8601; "
                             f"bare dates/naive times are UTC). Cannot reach back more than {LOOKBACK_DAYS} days")
    parser.add_argument("--created-before", metavar="TIMESTAMP",
                        help="Only orders created before this time (YYYY-MM-DD or ISO 8601)")
    parser.add_argument("--account-id", help="Account ID (uses PUBLIC_COM_ACCOUNT_ID if not provided)")

    args = parser.parse_args()

    try:
        request = build_request(
            status=args.status,
            side=args.side,
            symbols=args.symbol,
            security_type=args.security_type,
            open_close=args.open_close,
            created_after=args.created_after,
            created_before=args.created_before,
        )
    except ValueError as e:
        parser.error(str(e))

    search_orders(request, account_id=args.account_id)
