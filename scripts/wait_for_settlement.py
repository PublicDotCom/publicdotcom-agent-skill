import argparse
import sys
from decimal import Decimal

from config import ensure_sdk, get_api_secret, get_account_id, create_client

# Install/upgrade the pinned SDK before importing it (see config.SDK_VERSION).
ensure_sdk()
from public_api_sdk import WaitTimeoutError


def _fmt_ts(value):
    return value.strftime("%Y-%m-%d %H:%M:%S %Z").strip() if value else None


def _fmt_price(value):
    """Contract prices are dollars 0.00-1.00 (= implied probability); show both."""
    if value is None:
        return "—"
    if value != value.quantize(Decimal("0.01")):
        # Quotes can carry tenths of a cent; don't round them away.
        return f"${value:.3f} ({value * 100:.1f}%)"
    return f"${value:.2f} ({value * 100:.0f}%)"


def wait_for_settlement(event_symbol, outcome_id=None, contract=None, timeout=1800.0, poll_seconds=20.0):
    """
    Poll get_event_details until the outcome has settled, then report how it settled and,
    with --contract, whether that contract paid out.
    """
    secret = get_api_secret()

    if not secret:
        print("Error: PUBLIC_COM_SECRET is not set.")
        sys.exit(1)

    client = create_client(secret, get_account_id())

    try:
        target = f"outcome {outcome_id} of {event_symbol}" if outcome_id else event_symbol
        print(f"Waiting for {target} to settle (poll every {poll_seconds}s, timeout {timeout}s)...")
        try:
            outcome = client.wait_for_settlement(
                event_symbol, outcome_id, timeout=timeout, poll_interval=poll_seconds
            )
        except WaitTimeoutError as e:
            print(f"\nTimed out: {e}")
            sys.exit(2)
        except Exception as e:
            print(f"Error waiting for settlement: {e}")
            sys.exit(1)

        settled = outcome.settled_outcome.value.replace("SETTLED_OUTCOME_", "") if outcome.settled_outcome else "n/a"
        winner = outcome.winner

        print("\n" + "=" * 70)
        print(f"OUTCOME SETTLED: {settled}")
        print("=" * 70)
        print(f"  Event:        {event_symbol}")
        print(f"  Outcome:      {outcome.title or outcome.outcome_id}")
        print(f"  Outcome ID:   {outcome.outcome_id}")
        if outcome.timeline is not None and outcome.timeline.settlement_time is not None:
            print(f"  Settled At:   {_fmt_ts(outcome.timeline.settlement_time)}")
        if winner is not None:
            side = winner.predicted_outcome.value if winner.predicted_outcome else "?"
            print(f"  Winner:       {side}  {winner.symbol}  (pays $1.00 per contract)")
        else:
            print("  Winner:       none (settled other than YES/NO)")
        for label, c in (("YES", outcome.yes), ("NO", outcome.no)):
            if c is not None:
                print(f"  {label:>3} last:     {_fmt_price(c.last)}  {c.symbol}")
        if contract:
            won = outcome.won(contract)
            verdict = "unknown" if won is None else ("WON" if won else "LOST")
            print(f"  Your contract {contract}: {verdict}")
        print("=" * 70)
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Wait until an event contract outcome settles and report the winning side",
        epilog=(
            "Exit codes:\n"
            "  0  the outcome settled\n"
            "  1  error (unknown event, multi-outcome event without --outcome-id, ...)\n"
            "  2  timed out waiting\n\n"
            "Examples:\n"
            "  python3 wait_for_settlement.py --event-symbol KALSHI.KXBTC15M-26OCT201200\n"
            "  python3 wait_for_settlement.py --event-symbol KALSHI.KXBTC15M-26OCT201200 \\\n"
            "    --contract KALSHI.KXBTC15M-26OCT201200-00.Y\n"
            "  python3 wait_for_settlement.py --event-symbol KALSHI.KXBALANCESHEET-EO26 \\\n"
            "    --outcome-id KXBALANCESHEET-EO26-6.6 --timeout 60\n\n"
            "A 15-minute window settles a few minutes after it closes.\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--event-symbol", required=True,
                        help="The event, e.g. KALSHI.KXBTC15M-26OCT201200")
    parser.add_argument("--outcome-id",
                        help="The outcome to watch; may be omitted for a single-outcome event "
                             "(IDs carry no exchange prefix, e.g. KXBALANCESHEET-EO26-6.6)")
    parser.add_argument("--contract",
                        help="A contract symbol you hold (e.g. ...-00.Y); reports whether it WON or LOST")
    parser.add_argument("--timeout", type=float, default=1800.0, help="Max seconds to wait (default 1800)")
    parser.add_argument("--poll-seconds", type=float, default=20.0, help="Polling interval (default 20)")

    args = parser.parse_args()
    if not args.event_symbol.strip():
        parser.error("--event-symbol must not be empty")
    if args.timeout <= 0 or args.poll_seconds <= 0:
        parser.error("--timeout and --poll-seconds must be positive")

    contract = args.contract.strip() if args.contract else None
    if contract and contract.upper().endswith("-EVENTCONTRACT"):
        # Accept the get_event_contract_bars.py form too; outcomes hold the bare symbol.
        contract = contract[: -len("-EVENTCONTRACT")]

    wait_for_settlement(
        event_symbol=args.event_symbol.strip().upper(),
        outcome_id=args.outcome_id.strip() if args.outcome_id else None,
        contract=contract,
        timeout=args.timeout,
        poll_seconds=args.poll_seconds,
    )
