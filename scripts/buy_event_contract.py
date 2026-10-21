import argparse
import sys
from decimal import ROUND_CEILING, Decimal, InvalidOperation

from config import get_api_secret, get_account_id, create_client

CENT = Decimal("0.01")
BARS_SUFFIX = "-EVENTCONTRACT"


def parse_quantity(text):
    """Number of contracts: positive, at most 2 decimal places (the API limit)."""
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise argparse.ArgumentTypeError(f"invalid quantity {text!r}")
    if value <= 0 or value != value.quantize(CENT):
        raise argparse.ArgumentTypeError("quantity must be positive with at most 2 decimal places")
    return value


def parse_limit_price(text):
    """Price per contract in whole cents, 0.01-0.99."""
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise argparse.ArgumentTypeError(f"invalid price {text!r}")
    if value != value.quantize(CENT) or not Decimal("0") < value < Decimal("1"):
        raise argparse.ArgumentTypeError("limit price must be whole cents between 0.01 and 0.99")
    return value


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


def resolve_contract(client, symbol=None, event_symbol=None, contract_side=None, outcome_id=None):
    """
    Return (contract_or_symbol, outcome) for the order.

    With --symbol the bare symbol is returned (outcome None) and the caller must supply a
    limit price. With --event-symbol the event is fetched and the YES or NO contract of the
    chosen outcome is returned, so the SDK can price the order at its ask.
    """
    if symbol is not None:
        symbol = symbol.strip()
        if symbol.upper().endswith(BARS_SUFFIX):
            # get_event_contract_bars.py takes the "-EVENTCONTRACT" form; orders take the bare symbol.
            symbol = symbol[: -len(BARS_SUFFIX)]
        return symbol, None

    details = client.get_event_details(event_symbol.strip().upper(), include_all_outcomes=True)
    if outcome_id:
        outcome = next((o for o in details.outcomes if o.outcome_id == outcome_id.strip()), None)
        if outcome is None:
            ids = ", ".join(o.outcome_id for o in details.outcomes) or "none"
            raise ValueError(f"{details.event_symbol} has no outcome {outcome_id!r} (outcomes: {ids})")
    else:
        outcome = details.outcome
        if outcome is None:
            ids = ", ".join(o.outcome_id for o in details.outcomes) or "none"
            raise ValueError(
                f"{details.event_symbol} has {len(details.outcomes)} outcomes; pass --outcome-id (one of: {ids})"
            )
    contract = outcome.yes if contract_side == "YES" else outcome.no
    if contract is None:
        raise ValueError(f"outcome {outcome.outcome_id} has no {contract_side} contract")
    return contract, outcome


def buy_event_contract(symbol=None, event_symbol=None, contract_side=None, outcome_id=None,
                       quantity=Decimal("1"), limit_price=None, account_id=None):
    """
    Buy an event contract (a YES or NO side) with a DAY limit order.
    """
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

        contract, outcome = resolve_contract(client, symbol, event_symbol, contract_side, outcome_id)
        if outcome is not None and not outcome.is_tradable:
            state = outcome.state.value if outcome.state else "n/a"
            trading = outcome.trading.value if outcome.trading else "n/a"
            print(f"Error: outcome {outcome.outcome_id} is not accepting orders right now "
                  f"(state {state}, trading {trading}, {_fmt_left(outcome.seconds_left)} until close).")
            print("For a recurring market, find the next window with get_current_event.py --wait.")
            client.close()
            sys.exit(1)

        new_order = client.buy_event_contract(
            contract, quantity, limit_price=limit_price, account_id=account_id
        )

        contract_symbol = contract if isinstance(contract, str) else contract.symbol
        if limit_price is None:
            # Same rule as the SDK: the ask, rounded up to a whole cent.
            limit_price = contract.ask.quantize(CENT, rounding=ROUND_CEILING)

        print("Order Placed Successfully!")
        print("-" * 40)
        print(f"Order ID: {new_order.order_id}")
        print(f"Contract: {contract_symbol}")
        if outcome is not None:
            print(f"Outcome: {outcome.title or outcome.outcome_id} ({contract_side})")
        print("Side: BUY")
        print("Type: LIMIT")
        print("Time In Force: DAY")
        print(f"Quantity: {quantity} contract(s)")
        print(f"Limit Price: {_fmt_price(limit_price)}")
        if outcome is not None:
            print(f"Closes In: {_fmt_left(outcome.seconds_left)}")
        print("-" * 40)
        print(f"Track the fill:  wait_for_fill.py --order-id {new_order.order_id}")
        if event_symbol is not None:
            settle = f"wait_for_settlement.py --event-symbol {event_symbol.strip().upper()}"
            if outcome_id:
                settle += f" --outcome-id {outcome_id.strip()}"
            print(f"Await result:    {settle} --contract {contract_symbol}")

        client.close()
    except Exception as e:
        print(f"Error placing event contract order: {e}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Buy an event contract (prediction market YES/NO side) with a DAY limit order",
        epilog="Examples:\n"
               "  Current 15-minute window, YES side at the ask (find it with get_current_event.py):\n"
               "    python3 buy_event_contract.py --event-symbol KALSHI.KXBTC15M-26OCT201200 --contract YES\n\n"
               "  Multi-outcome event: pick the outcome (IDs from get_event_details.py):\n"
               "    python3 buy_event_contract.py --event-symbol KALSHI.KXBALANCESHEET-EO26 --outcome-id KXBALANCESHEET-EO26-6.6 \\\n"
               "      --contract NO --quantity 5\n\n"
               "  By contract symbol (a limit price is then required):\n"
               "    python3 buy_event_contract.py --symbol KALSHI.KXBTC15M-26OCT201200-00.Y --limit-price 0.55\n\n"
               "Always a BUY with a DAY limit order. Without --limit-price the limit is the\n"
               "contract's current ask rounded UP to a whole cent. Preflight first with\n"
               "preflight_event_contract.py (same flags).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--event-symbol",
                        help="Event symbol (e.g. from get_current_event.py); the contract is picked with --contract")
    target.add_argument("--symbol",
                        help="Contract symbol ending in .Y (YES) or .N (NO), e.g. KALSHI.KXBTC15M-26OCT201200-00.Y; "
                             "requires --limit-price")
    parser.add_argument("--contract", type=str.upper, choices=["YES", "NO"],
                        help="With --event-symbol: buy the YES or the NO contract")
    parser.add_argument("--outcome-id",
                        help="With --event-symbol: the outcome, for events with more than one "
                             "(IDs carry no exchange prefix, e.g. KXBALANCESHEET-EO26-6.6)")
    parser.add_argument("--quantity", type=parse_quantity, default=Decimal("1"),
                        help="Number of contracts (default 1; at most 2 decimal places)")
    parser.add_argument("--limit-price", type=parse_limit_price,
                        help="Most to pay per contract, whole cents 0.01-0.99 "
                             "(default with --event-symbol: the ask rounded up to a cent)")
    parser.add_argument("--account-id", help="Account ID (uses PUBLIC_COM_ACCOUNT_ID if not provided)")

    args = parser.parse_args()

    if args.event_symbol is not None:
        if not args.event_symbol.strip():
            parser.error("--event-symbol must not be empty")
        if args.contract is None:
            parser.error("--event-symbol requires --contract YES or NO")
    else:
        if not args.symbol.strip():
            parser.error("--symbol must not be empty")
        if args.contract is not None or args.outcome_id is not None:
            parser.error("--contract / --outcome-id only apply with --event-symbol")
        if args.limit_price is None:
            parser.error("--symbol requires --limit-price (or use --event-symbol to buy at the ask)")

    buy_event_contract(
        symbol=args.symbol,
        event_symbol=args.event_symbol,
        contract_side=args.contract,
        outcome_id=args.outcome_id,
        quantity=args.quantity,
        limit_price=args.limit_price,
        account_id=args.account_id,
    )
