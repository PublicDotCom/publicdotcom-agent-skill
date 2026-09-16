import argparse
import re
import sys

from config import ensure_sdk, get_api_secret, get_account_id, create_client

# Install/upgrade the pinned SDK before importing it (see config.SDK_VERSION).
ensure_sdk()
from public_api_sdk import (
    OpenCloseIndicator,
    OrderSide,
    StrategyOrderLeg,
    StrategyQuoteRequest,
)


def parse_leg(spec):
    """
    Parse a leg spec: SYMBOL:TYPE:SIDE[:OPEN_CLOSE][:RATIO]

    Same format as preflight_multileg.py / place_multileg.py so an agent can
    quote a strategy and then place it with identical --leg arguments.
      TYPE       = EQUITY | OPTION
      SIDE       = BUY | SELL
      OPEN_CLOSE = OPEN | CLOSE (optional; required for OPTION legs)
      RATIO      = optional integer ratio (default 1)

    Returns (instrument_type, StrategyOrderLeg).
    """
    parts = spec.split(":")
    if len(parts) < 3:
        raise ValueError(f"Leg '{spec}' must be SYMBOL:TYPE:SIDE[:OPEN_CLOSE][:RATIO]")

    symbol, leg_type, side = parts[0].upper(), parts[1].upper(), parts[2].upper()
    open_close = None
    ratio = 1

    for extra in parts[3:]:
        extra_u = extra.upper()
        if extra_u in ("OPEN", "CLOSE"):
            open_close = extra_u
        elif extra_u.isdigit():
            ratio = int(extra_u)
        else:
            raise ValueError(f"Unrecognised leg component '{extra}' in '{spec}'")

    if leg_type not in ("EQUITY", "OPTION"):
        raise ValueError(f"Leg type must be EQUITY or OPTION, got '{leg_type}' in '{spec}'")
    if side not in ("BUY", "SELL"):
        raise ValueError(f"Leg side must be BUY or SELL, got '{side}' in '{spec}'")
    if leg_type == "OPTION" and open_close is None:
        raise ValueError(f"OPTION leg '{spec}' needs OPEN or CLOSE")
    if ratio < 1:
        raise ValueError(f"Ratio must be >= 1 in '{spec}'")

    leg = StrategyOrderLeg(
        symbol=symbol,
        side=OrderSide[side],
        open_close_indicator=OpenCloseIndicator[open_close] if open_close else None,
        ratio_quantity=ratio,
    )
    return leg_type, leg


def _osi_root(symbol):
    """Underlying root from an OSI option symbol (e.g. AAPL251219C00200000 -> AAPL)."""
    match = re.match(r"^([A-Z]+)\d{6}[CP]\d{8}$", symbol)
    return match.group(1) if match else None


def _fmt(value, prefix="$"):
    return f"{prefix}{value}" if value is not None else "n/a"


def _print_leg(label, leg):
    inst = leg.instrument
    oc = f" {leg.open_close_indicator.value}" if leg.open_close_indicator else ""
    ratio = f" x{leg.ratio_quantity}" if leg.ratio_quantity and leg.ratio_quantity != 1 else ""
    print(f"\n  {label} {leg.side.value} {inst.symbol}{oc}{ratio}")
    if inst.type or inst.strike_price is not None or inst.expiration_date:
        detail = []
        if inst.type:
            detail.append(inst.type.value)
        if inst.strike_price is not None:
            detail.append(f"strike {inst.strike_price}")
        if inst.expiration_date:
            detail.append(f"exp {inst.expiration_date}")
        print(f"      {'  '.join(detail)}")
    q = leg.quote
    if q:
        print(f"      Bid: {_fmt(q.bid)} x{q.bid_size if q.bid_size is not None else '?'}   "
              f"Ask: {_fmt(q.ask)} x{q.ask_size if q.ask_size is not None else '?'}   "
              f"Last: {_fmt(q.last)}")
        extras = []
        if q.open_interest is not None:
            extras.append(f"open interest {q.open_interest}")
        if q.trading_halted:
            extras.append("TRADING HALTED")
        if extras:
            print(f"      {'  '.join(extras)}")


def get_strategy_quote(leg_specs, base_symbol=None, account_id=None):
    secret = get_api_secret()
    account_id = account_id or get_account_id()

    if not secret:
        print("Error: PUBLIC_COM_SECRET is not set.")
        sys.exit(1)

    if not account_id:
        print("Error: No account ID provided. Either pass --account-id or set PUBLIC_COM_ACCOUNT_ID.")
        sys.exit(1)

    option_legs = []
    equity_leg = None
    try:
        for spec in leg_specs:
            leg_type, leg = parse_leg(spec)
            if leg_type == "OPTION":
                option_legs.append(leg)
            else:
                if equity_leg is not None:
                    raise ValueError("At most one EQUITY leg is allowed")
                equity_leg = leg
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    if not option_legs:
        print("Error: at least one OPTION leg is required.")
        sys.exit(1)

    if not base_symbol:
        roots = {_osi_root(l.symbol) for l in option_legs}
        roots.discard(None)
        if len(roots) != 1:
            print("Error: could not infer the underlying from the option symbols; pass --base-symbol.")
            sys.exit(1)
        base_symbol = roots.pop()

    try:
        client = create_client(secret, account_id)

        request = StrategyQuoteRequest(
            base_symbol=base_symbol.upper(),
            option_legs=option_legs,
            equity_leg=equity_leg,
        )
        quote = client.get_strategy_quote(request)

        print("=" * 70)
        print(f"STRATEGY QUOTE: {quote.strategy_name}  ({base_symbol.upper()})")
        print("=" * 70)
        dc = quote.debit_credit.value if quote.debit_credit else "n/a"
        print(f"\n  Debit/Credit:  {dc}")
        print(f"  Price:         {_fmt(quote.price)}")
        print(f"  Bid:           {_fmt(quote.bid)}")
        print(f"  Ask:           {_fmt(quote.ask)}")
        print(f"  Mark:          {_fmt(quote.mark)}")
        if quote.expiration_date:
            print(f"  Expiration:    {quote.expiration_date}")

        print(f"\n  Legs ({len(quote.strategy_legs)} option" + ("" if len(quote.strategy_legs) == 1 else "s")
              + (" + 1 equity" if quote.equity_quote else "") + "):")
        for i, leg in enumerate(quote.strategy_legs, 1):
            _print_leg(f"[{i}]", leg)
        if quote.equity_quote:
            _print_leg("[EQ]", quote.equity_quote)

        print("\n  This is a quote only — nothing was preflighted or placed. Use"
              " preflight_multileg.py / place_multileg.py (same --leg arguments) to trade it.")
        print("\n" + "=" * 70)

        client.close()
    except Exception as e:
        print(f"Error fetching strategy quote: {e}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Quote a multi-leg option strategy as a whole (net price, bid/ask, per-leg quotes)",
        epilog="Leg format: SYMBOL:TYPE:SIDE[:OPEN_CLOSE][:RATIO]  (same as preflight_multileg.py)\n\n"
               "Examples:\n"
               "  Put credit spread on SPY:\n"
               "    python3 get_strategy_quote.py \\\n"
               "      --leg SPY260313P00670000:OPTION:SELL:OPEN \\\n"
               "      --leg SPY260313P00665000:OPTION:BUY:OPEN\n\n"
               "  Covered call (equity leg + short call), explicit underlying:\n"
               "    python3 get_strategy_quote.py --base-symbol AAPL \\\n"
               "      --leg AAPL:EQUITY:BUY:100 \\\n"
               "      --leg AAPL251219C00200000:OPTION:SELL:OPEN",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--leg",
        action="append",
        required=True,
        dest="legs",
        help="Strategy leg (repeat). At least one OPTION leg; at most one EQUITY leg.",
    )
    parser.add_argument(
        "--base-symbol",
        help="Underlying ticker (inferred from the option symbols when omitted)",
    )
    parser.add_argument("--account-id", help="Account ID (uses PUBLIC_COM_ACCOUNT_ID if not provided)")

    args = parser.parse_args()
    get_strategy_quote(args.legs, base_symbol=args.base_symbol, account_id=args.account_id)
