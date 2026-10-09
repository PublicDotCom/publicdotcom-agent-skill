import argparse
import sys

from config import get_api_secret, get_account_id, create_client


def _fmt_ts(value):
    return value.strftime("%Y-%m-%d %H:%M %Z").strip() if value else None


def _fmt_price(value):
    """Contract prices are dollars 0.00-1.00 (= implied probability); show both."""
    if value is None:
        return "—"
    return f"${value:.2f} ({value * 100:.0f}%)"


def get_event_details(event_symbol, all_outcomes=True):
    secret = get_api_secret()

    if not secret:
        print("Error: PUBLIC_COM_SECRET is not set.")
        sys.exit(1)

    try:
        client = create_client(secret, get_account_id())

        event = client.get_event_details(event_symbol.strip().upper(), include_all_outcomes=all_outcomes)

        print("=" * 78)
        print(f"EVENT {event.event_symbol}")
        print("=" * 78)
        print(f"\n  Title:     {event.title or 'n/a'}")
        category = event.category or "n/a"
        if event.subcategories:
            category += f" / {', '.join(event.subcategories)}"
        print(f"  Category:  {category}")
        if event.exchange is not None:
            print(f"  Exchange:  {event.exchange.value}")
        status = []
        if event.resolved:
            status.append("RESOLVED")
        if event.halted:
            status.append("HALTED")
        print(f"  Status:    {', '.join(status) if status else 'open'}")
        if event.volume is not None:
            print(f"  Volume:    {event.volume:,}")
        shown = len(event.outcomes)
        total = event.outcome_count if event.outcome_count is not None else shown
        print(f"  Outcomes:  {shown} shown of {total}")

        for outcome in event.outcomes:
            print("\n" + "-" * 78)
            print(f"  {outcome.title or outcome.outcome_id}")
            print(f"    Outcome ID: {outcome.outcome_id}")
            meta = []
            if outcome.state is not None:
                meta.append(f"State {outcome.state.value}")
            if outcome.trading is not None:
                meta.append(f"Trading {outcome.trading.value}")
            if outcome.settled_outcome is not None and outcome.settled_outcome.value != "SETTLED_OUTCOME_UNSPECIFIED":
                meta.append(f"Settled {outcome.settled_outcome.value.replace('SETTLED_OUTCOME_', '')}")
            if outcome.volume is not None:
                meta.append(f"Volume {outcome.volume:,}")
            if meta:
                print(f"    {'  |  '.join(meta)}")
            tl = outcome.timeline
            if tl is not None:
                times = [
                    ("Opens", tl.open_time),
                    ("Closes", tl.close_time),
                    ("Expected expiry", tl.expected_expiration_time),
                    ("Settles", tl.settlement_time),
                ]
                times = [f"{label} {_fmt_ts(value)}" for label, value in times if value]
                if times:
                    print(f"    {'  |  '.join(times)}")
            for contract in outcome.contracts:
                side = contract.predicted_outcome.value if contract.predicted_outcome else "?"
                print(
                    f"    {side:>3}  {contract.symbol}\n"
                    f"         Bid {_fmt_price(contract.bid)}  Ask {_fmt_price(contract.ask)}  "
                    f"Last {_fmt_price(contract.last)}"
                    + (f"  OI {contract.open_interest:,}" if contract.open_interest is not None else "")
                )
            if outcome.rules:
                print(f"    Rules: {outcome.rules}")

        cftc = event.cftc_contract
        if cftc is not None:
            print("\n" + "-" * 78)
            print("  CFTC Contract Terms")
            if cftc.contract_terms_url:
                print(f"    Terms: {cftc.contract_terms_url}")
            for source in cftc.resolution_sources:
                print(f"    Resolution source: {source.name or 'n/a'}" + (f" ({source.url})" if source.url else ""))
            for prohibition in cftc.prohibitions:
                print(f"    Prohibited: {prohibition}")

        print("\n  Chart prices: get_event_contract_bars.py --event-id <ID>-EVENT --period WEEK "
              "--symbol <CONTRACT SYMBOL>-EVENTCONTRACT")
        print("\n" + "=" * 78)

        client.close()
    except Exception as e:
        print(f"Error fetching event details: {e}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Show an event contract's outcomes, YES/NO contract prices, trading timeline "
                    "and CFTC terms",
        epilog="Examples:\n"
               "  python3 get_event_details.py --event-symbol KALSHI.KXBALANCESHEET-EO26\n"
               "  python3 get_event_details.py --event-symbol KALSHI.KXBALANCESHEET-EO26 --no-all-outcomes\n\n"
               "The event symbol comes from get_event_summary.py. It is NOT the `-EVENT` id that\n"
               "get_event_contract_bars.py takes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--event-symbol", required=True,
                        help="The event symbol from get_event_summary.py, e.g. KALSHI.KXBALANCESHEET-EO26")
    parser.add_argument("--all-outcomes", action=argparse.BooleanOptionalAction, default=True,
                        help="Return every outcome (default) or, with --no-all-outcomes, a short list of up to 8")
    args = parser.parse_args()
    if not args.event_symbol.strip():
        parser.error("--event-symbol must not be empty")
    get_event_details(args.event_symbol, all_outcomes=args.all_outcomes)
