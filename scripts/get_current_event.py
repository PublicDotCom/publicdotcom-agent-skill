import argparse
import sys
from datetime import datetime, timezone
from decimal import Decimal

from config import ensure_sdk, get_api_secret, get_account_id, create_client

# Install/upgrade the pinned SDK before importing it (see config.SDK_VERSION).
ensure_sdk()
from public_api_sdk import EventFrequency, WaitTimeoutError


def _fmt_ts(value):
    return value.strftime("%Y-%m-%d %H:%M:%S %Z").strip() if value else "n/a"


def _fmt_price(value):
    """Contract prices are dollars 0.00-1.00 (= implied probability); show both."""
    if value is None:
        return "—"
    if value != value.quantize(Decimal("0.01")):
        # Quotes can carry tenths of a cent; don't round them away.
        return f"${value:.3f} ({value * 100:.1f}%)"
    return f"${value:.2f} ({value * 100:.0f}%)"


def _fmt_left(seconds):
    if seconds is None:
        return "n/a"
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m {secs:02d}s"


def _seconds_until(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return max(0.0, (value - datetime.now(timezone.utc)).total_seconds())


def get_current_event(series, frequency="FIFTEEN_MINUTES", category=None, subcategory=None,
                      wait=False, timeout=900.0, poll_seconds=30.0, details=True):
    """
    Find the open event of a recurring series (e.g. a 15-minute "Up or Down" window) that
    closes soonest, optionally waiting until one is listed, and show its YES/NO prices.
    """
    secret = get_api_secret()

    if not secret:
        print("Error: PUBLIC_COM_SECRET is not set.")
        sys.exit(1)

    try:
        client = create_client(secret, get_account_id())
        freq = EventFrequency(frequency)

        if wait:
            print(f"Waiting for an open {series} event (poll every {poll_seconds}s, timeout {timeout}s)...")
            try:
                event = client.wait_for_current_event(
                    series, freq, category=category, subcategory=subcategory,
                    timeout=timeout, poll_interval=poll_seconds,
                )
            except WaitTimeoutError as e:
                print(f"\nTimed out: {e}")
                client.close()
                sys.exit(2)
        else:
            event = client.get_current_event(series, freq, category=category, subcategory=subcategory)

        if event is None:
            print(f"No open {series} event at {freq.value} frequency right now.")
            print("The next window is usually listed a minute or two after the previous one closes;")
            print("re-run with --wait to poll until it appears.")
            client.close()
            sys.exit(1)

        print("=" * 78)
        print(f"CURRENT {series} EVENT")
        print("=" * 78)
        print(f"\n  Title:         {event.title or 'n/a'}")
        print(f"  Event Symbol:  {event.event_symbol}")
        print(f"  Series:        {event.series or 'n/a'}")
        category_text = event.category or "n/a"
        if event.subcategories:
            category_text += f" / {', '.join(event.subcategories)}"
        print(f"  Category:      {category_text}")
        print(f"  Resolves:      {_fmt_ts(event.resolution_time)}  "
              f"({_fmt_left(_seconds_until(event.resolution_time))} left)")
        if event.volume is not None:
            print(f"  Volume:        {event.volume:,}")

        if details:
            event_details = client.get_event_details(event.event_symbol)
            for outcome in event_details.outcomes:
                print("\n" + "-" * 78)
                print(f"  {outcome.title or outcome.outcome_id}")
                print(f"    Outcome ID:  {outcome.outcome_id}")
                print(f"    Tradable:    {'yes' if outcome.is_tradable else 'no'}  |  "
                      f"Closes {_fmt_ts(outcome.close_time)} ({_fmt_left(outcome.seconds_left)} left)")
                for label, contract in (("YES", outcome.yes), ("NO", outcome.no)):
                    if contract is None:
                        continue
                    print(f"    {label:>3}  {contract.symbol}\n"
                          f"         Bid {_fmt_price(contract.bid)}  Ask {_fmt_price(contract.ask)}  "
                          f"Last {_fmt_price(contract.last)}")
            if len(event_details.outcomes) > 1:
                print("\n  Multi-outcome event: pass --outcome-id to buy_event_contract.py / wait_for_settlement.py.")

        print(f"\n  Buy:    buy_event_contract.py --event-symbol {event.event_symbol} --contract YES|NO")
        print(f"  Settle: wait_for_settlement.py --event-symbol {event.event_symbol}")
        print("\n" + "=" * 78)

        client.close()
    except Exception as e:
        print(f"Error finding current event: {e}")
        sys.exit(1)


if __name__ == "__main__":
    frequencies = [f.value for f in EventFrequency if f != EventFrequency.UNKNOWN]
    parser = argparse.ArgumentParser(
        description="Find the open event of a recurring prediction market (e.g. a 15-minute window) "
                    "that closes soonest, with its YES/NO prices",
        epilog="Exit codes:\n"
               "  0  found an open event\n"
               "  1  no open event right now (without --wait), or an error\n"
               "  2  --wait timed out\n\n"
               "Examples:\n"
               "  python3 get_current_event.py --series KXBTC15M\n"
               "  python3 get_current_event.py --series KXBTC15M --wait --timeout 300\n"
               "  python3 get_current_event.py --series <SERIES> --frequency ONE_HOUR --category Crypto\n\n"
               "The series is the ticker between the exchange prefix and the first '-' of an event\n"
               "symbol: KALSHI.KXBTC15M-26OCT201200 -> KXBTC15M (get_event_summary.py shows it).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--series", required=True, type=str.upper,
                        help="Series ticker, e.g. KXBTC15M (see the Series line of get_event_summary.py)")
    parser.add_argument("--frequency", default="FIFTEEN_MINUTES", type=str.upper, choices=frequencies,
                        help="How often the series recurs (default: FIFTEEN_MINUTES)")
    parser.add_argument("--category", help="Optional category to search, e.g. Crypto")
    parser.add_argument("--subcategory", help="Optional subcategory to search, e.g. BTC")
    parser.add_argument("--wait", action="store_true",
                        help="Poll until the series has an open event instead of exiting when it has none")
    parser.add_argument("--timeout", type=float, default=900.0,
                        help="With --wait: max seconds to wait (default 900)")
    parser.add_argument("--poll-seconds", type=float, default=30.0,
                        help="With --wait: seconds between checks (default 30)")
    parser.add_argument("--details", action=argparse.BooleanOptionalAction, default=True,
                        help="Also fetch the event's outcomes and YES/NO prices (default); --no-details skips it")

    args = parser.parse_args()
    if not args.series.strip():
        parser.error("--series must not be empty")
    if args.timeout <= 0 or args.poll_seconds <= 0:
        parser.error("--timeout and --poll-seconds must be positive")

    get_current_event(
        series=args.series.strip(),
        frequency=args.frequency,
        category=args.category,
        subcategory=args.subcategory,
        wait=args.wait,
        timeout=args.timeout,
        poll_seconds=args.poll_seconds,
        details=args.details,
    )
