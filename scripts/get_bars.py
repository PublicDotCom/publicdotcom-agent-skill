import argparse
import sys

from config import ensure_sdk, get_api_secret, get_account_id, create_client

# Install/upgrade the pinned SDK before importing it (see config.SDK_VERSION).
ensure_sdk()
from public_api_sdk import (
    BarPeriod,
    BarAggregation,
    InstrumentType,
    TradingSessionToggle,
)


def get_bars(
    symbol,
    period,
    instrument_type="EQUITY",
    aggregation=None,
    purchase_date=None,
    session_toggle=None,
    ipo_date=None,
    account_id=None,
):
    """
    Fetch historical OHLCV bar data for a symbol.

    Args:
        symbol: Ticker symbol (e.g. "AAPL", "BTC", "AAPL260320C00280000")
        period: One of BarPeriod values (DAY, WEEK, MONTH, QUARTER, HALF_YEAR,
                YEAR, FIVE_YEARS, YTD, SINCE_PURCHASE)
        instrument_type: EQUITY, CRYPTO, OPTION, INDEX, or EVENTCONTRACT. Defaults to EQUITY.
                For several contracts of one prediction-market event, use get_event_contract_bars.py.
        aggregation: Optional bar size override (ONE_MINUTE, FIVE_MINUTES, ...)
        purchase_date: Required when period=SINCE_PURCHASE. Format YYYY-MM-DD.
        session_toggle: DAY equity charts only — REGULAR_HOURS, REGULAR_AND_EXTENDED_HOURS
                (server default) or ALL_SESSIONS (adds the overnight 00:00-04:00 / 20:00-24:00 buckets)
        ipo_date: The asset's IPO / first-trade date (YYYY-MM-DD). For assets younger than the
                period the server returns finer bars plus a `leading_fill` describing the flat lead-in.
        account_id: Account ID (optional; uses PUBLIC_COM_ACCOUNT_ID env var if unset)
    """
    secret = get_api_secret()
    account_id = account_id or get_account_id()

    if not secret:
        print("Error: PUBLIC_COM_SECRET is not set.")
        sys.exit(1)

    period_map = {p.name: p for p in BarPeriod}
    aggregation_map = {a.name: a for a in BarAggregation}
    instrument_type_map = {
        "EQUITY": InstrumentType.EQUITY,
        "CRYPTO": InstrumentType.CRYPTO,
        "OPTION": InstrumentType.OPTION,
        "INDEX": InstrumentType.INDEX,
        "EVENTCONTRACT": InstrumentType.EVENTCONTRACT,
    }

    if period not in period_map:
        print(f"Error: Invalid period '{period}'. Must be one of: {', '.join(period_map.keys())}")
        sys.exit(1)

    if aggregation is not None and aggregation not in aggregation_map:
        print(f"Error: Invalid aggregation '{aggregation}'. Must be one of: {', '.join(aggregation_map.keys())}")
        sys.exit(1)

    if instrument_type not in instrument_type_map:
        print(f"Error: Invalid instrument type '{instrument_type}'. Must be EQUITY, CRYPTO, OPTION, INDEX, or EVENTCONTRACT.")
        sys.exit(1)

    if period == "SINCE_PURCHASE" and not purchase_date:
        print("Error: --purchase-date is required when --period SINCE_PURCHASE.")
        sys.exit(1)

    try:
        client = create_client(secret, account_id)

        kwargs = {
            "symbol": symbol,
            "period": period_map[period],
            "instrument_type": instrument_type_map[instrument_type],
        }
        if aggregation is not None:
            kwargs["aggregation"] = aggregation_map[aggregation]
        if purchase_date is not None:
            kwargs["purchase_date"] = purchase_date
        if session_toggle is not None:
            kwargs["trading_session_toggle"] = TradingSessionToggle[session_toggle]
        if ipo_date is not None:
            kwargs["ipo_date"] = ipo_date

        response = client.get_bars(**kwargs)

        print("=" * 60)
        print(f"HISTORICAL BARS: {response.symbol} ({instrument_type})")
        print(f"  Period: {response.period}")
        print(f"  Total Expected Bars: {response.total_expected_bars}")
        if response.previous_close_price is not None:
            print(f"  Previous Close: ${response.previous_close_price}")
        if response.total_gain_loss is not None:
            print(f"  Total Gain/Loss: ${response.total_gain_loss}")
        if response.total_gain_loss_percentage is not None:
            print(f"  Total Gain/Loss %: {response.total_gain_loss_percentage}%")

        if response.last_regular_trading_session_close is not None:
            last = response.last_regular_trading_session_close
            print(f"\n  Last Regular Session Close ({last.close_date}): ${last.close}")
            if last.change is not None:
                print(f"    Change: ${last.change}")
            if last.percent_change is not None:
                print(f"    Percent Change: {last.percent_change}%")

        if response.leading_fill is not None:
            lf = response.leading_fill
            print(f"\n  Leading Fill (asset younger than the period): {lf.count} flat bar(s) at ${lf.value}")
            print(f"    from {lf.start_timestamp} to the first real bar at {lf.end_timestamp}")

        sessions = [
            ("PRE-MARKET OVERNIGHT (00:00-04:00 ET)", response.pre_market_overnight),
            ("PRE-MARKET", response.pre_market),
            ("REGULAR MARKET", response.regular_market),
            ("AFTER-HOURS", response.after_market),
            ("POST-MARKET OVERNIGHT (20:00-24:00 ET)", response.post_market_overnight),
        ]
        for label, session in sessions:
            if session is None:  # overnight buckets only come back with ALL_SESSIONS
                continue
            print("\n" + "-" * 60)
            print(f"{label}  (expected: {session.expected_bars}, returned: {len(session.bars)})")
            print("-" * 60)
            for bar in session.bars:
                print(
                    f"  {bar.timestamp}  "
                    f"O={bar.open}  H={bar.high}  L={bar.low}  C={bar.close}  V={bar.volume}"
                )

        print("\n" + "=" * 60)

        client.close()
    except Exception as e:
        print(f"Error fetching bars: {e}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch historical OHLCV bar data for a symbol",
        epilog="Examples:\n"
               "  python3 get_bars.py --symbol AAPL --period YEAR\n"
               "  python3 get_bars.py --symbol AAPL --period MONTH --aggregation ONE_DAY\n"
               "  python3 get_bars.py --symbol BTC --type CRYPTO --period WEEK\n"
               "  python3 get_bars.py --symbol AAPL --period SINCE_PURCHASE --purchase-date 2024-01-15\n"
               "  python3 get_bars.py --symbol AAPL --period DAY --session-toggle ALL_SESSIONS\n"
               "  python3 get_bars.py --symbol NEWCO --period YEAR --ipo-date 2026-03-15",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--symbol", required=True, help="Symbol (e.g. AAPL, BTC, OSI option symbol)")
    parser.add_argument(
        "--period",
        required=True,
        choices=[p.name for p in BarPeriod],
        help="Time window for bars",
    )
    parser.add_argument(
        "--type",
        default="EQUITY",
        choices=["EQUITY", "CRYPTO", "OPTION", "INDEX", "EVENTCONTRACT"],
        help="Instrument type (default: EQUITY). For up to 8 contracts of one event in a single call, "
             "use get_event_contract_bars.py",
    )
    parser.add_argument(
        "--aggregation",
        choices=[a.name for a in BarAggregation],
        help="Optional bar size override; server picks a sensible default if omitted",
    )
    parser.add_argument(
        "--purchase-date",
        help="Required for --period SINCE_PURCHASE. Format: YYYY-MM-DD",
    )
    parser.add_argument(
        "--session-toggle",
        choices=[t.name for t in TradingSessionToggle],
        help="DAY equity charts: REGULAR_HOURS (9:30-16:00 ET), REGULAR_AND_EXTENDED_HOURS (4:00-20:00 ET, "
             "server default) or ALL_SESSIONS (midnight-to-midnight, adds the overnight buckets)",
    )
    parser.add_argument(
        "--ipo-date",
        help="IPO / first-trade date (YYYY-MM-DD) for recently listed assets; enables finer bars plus a leading-fill summary",
    )
    parser.add_argument(
        "--account-id",
        help="Account ID (uses PUBLIC_COM_ACCOUNT_ID env var if not provided)",
    )

    args = parser.parse_args()

    get_bars(
        symbol=args.symbol,
        period=args.period,
        instrument_type=args.type,
        aggregation=args.aggregation,
        purchase_date=args.purchase_date,
        session_toggle=args.session_toggle,
        ipo_date=args.ipo_date,
        account_id=args.account_id,
    )
