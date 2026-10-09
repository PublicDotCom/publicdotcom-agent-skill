import argparse
import sys

from config import ensure_sdk, get_api_secret, get_account_id, create_client

# Install/upgrade the pinned SDK before importing it (see config.SDK_VERSION).
ensure_sdk()
from public_api_sdk import EventContractBarPeriod

# The API accepts at most this many contract symbols per request.
MAX_SYMBOLS = 8


def _split(values):
    """Flatten repeated and/or comma-separated --symbol values, upper-cased, blanks dropped."""
    return [part.strip().upper() for value in values or [] for part in value.split(",") if part.strip()]


def _fmt_price(value):
    """Prices are dollars 0.00-1.00 (= implied probability); show both."""
    if value is None:
        return "n/a"
    return f"${value:.2f} ({value * 100:.0f}%)"


def get_event_contract_bars(event_id, period, symbols, account_id=None):
    """
    Fetch chart bars for up to 8 contracts of one prediction-market event.

    Args:
        event_id: The `-EVENT` grouping id, e.g. KALSHI.KXBALANCESHEET-EO26-EVENT
        period: DAY, WEEK, MONTH or ALL
        symbols: 1-8 `-EVENTCONTRACT` symbols belonging to the event
        account_id: Account ID (optional; uses PUBLIC_COM_ACCOUNT_ID env var if unset)
    """
    secret = get_api_secret()
    account_id = account_id or get_account_id()

    if not secret:
        print("Error: PUBLIC_COM_SECRET is not set.")
        sys.exit(1)

    try:
        client = create_client(secret, account_id)

        response = client.get_event_contract_bars(
            event_id=event_id.strip().upper(),
            period=EventContractBarPeriod(period),
            symbols=symbols,
        )

        print("=" * 72)
        print(f"EVENT CONTRACT BARS: {event_id.strip().upper()}  ({response.period or period})")
        print("  Prices are 0.00-1.00 dollars = implied probability; a .N symbol carries the NO side.")
        print("=" * 72)

        returned = {chart.symbol for chart in response.charts}
        missing = [s for s in symbols if s not in returned]

        for chart in response.charts:
            print("\n" + "-" * 72)
            print(f"  {chart.symbol}  ({len(chart.bars)} bar(s))")
            print("-" * 72)
            print(f"    Current: {_fmt_price(chart.current_price)}  |  Previous Close: {_fmt_price(chart.previous_close_price)}")
            if chart.total_gain_loss is not None:
                pct = f" ({chart.total_gain_loss_percentage}%)" if chart.total_gain_loss_percentage is not None else ""
                print(f"    Change over period: ${chart.total_gain_loss}{pct}")
            for bar in chart.bars:
                print(
                    f"    {bar.timestamp}  "
                    f"O={bar.open}  H={bar.high}  L={bar.low}  C={bar.close}  V={bar.volume}"
                )

        if not response.charts:
            print("\n  No charts returned.")
        if missing:
            print(f"\n  ⚠️  No data for: {', '.join(missing)} (unknown symbol, no candles, or no price in this period)")
        print("\n  Charts can start at different times — align them by timestamp, not by position.")
        print("\n" + "=" * 72)

        client.close()
    except Exception as e:
        print(f"Error fetching event contract bars: {e}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=f"Fetch chart bars for up to {MAX_SYMBOLS} contracts of one event contract "
                    "(prediction market) event",
        epilog="Examples:\n"
               "  python3 get_event_contract_bars.py --event-id KALSHI.KXBALANCESHEET-EO26-EVENT --period WEEK \\\n"
               "    --symbol KALSHI.KXBALANCESHEET-EO26-6.6.Y-EVENTCONTRACT\n\n"
               "  YES and NO sides of an outcome, comma-separated:\n"
               "    python3 get_event_contract_bars.py --event-id KALSHI.KXBALANCESHEET-EO26-EVENT --period ALL \\\n"
               "      --symbol KALSHI.KXBALANCESHEET-EO26-6.6.Y-EVENTCONTRACT,KALSHI.KXBALANCESHEET-EO26-6.6.N-EVENTCONTRACT\n\n"
               "--event-id is the `-EVENT` grouping id, NOT the event symbol from get_event_summary.py /\n"
               "get_event_details.py (append -EVENT to that symbol). Contract symbols take the\n"
               "-EVENTCONTRACT suffix.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--event-id", required=True,
                        help="The -EVENT grouping id, e.g. KALSHI.KXBALANCESHEET-EO26-EVENT")
    parser.add_argument("--period", required=True, type=str.upper, choices=[p.value for p in EventContractBarPeriod],
                        help="Time window, measured back from now (or from the event's close once it stops trading)")
    parser.add_argument("--symbol", action="append", required=True, metavar="SYMBOL",
                        help=f"An -EVENTCONTRACT symbol of the event. Repeat or comma-separate, up to {MAX_SYMBOLS}")
    parser.add_argument("--account-id", help="Account ID (uses PUBLIC_COM_ACCOUNT_ID env var if not provided)")

    args = parser.parse_args()

    symbols = _split(args.symbol)
    if not symbols:
        parser.error("Pass at least one --symbol.")
    if len(symbols) > MAX_SYMBOLS:
        parser.error(f"Too many symbols ({len(symbols)}); the API accepts at most {MAX_SYMBOLS} per request.")
    if not args.event_id.strip():
        parser.error("--event-id must not be empty")

    get_event_contract_bars(args.event_id, args.period, symbols, account_id=args.account_id)
