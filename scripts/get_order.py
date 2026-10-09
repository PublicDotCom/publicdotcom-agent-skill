import argparse
import sys

from config import get_api_secret, get_account_id, create_client


def _fmt_ts(value):
    return value.strftime("%Y-%m-%d %H:%M:%S %Z").strip() if value else None


def get_order(order_id, account_id=None):
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

        order = client.get_order(order_id=order_id, account_id=account_id)

        print("=" * 70)
        print(f"ORDER {order.order_id}")
        print("=" * 70)

        inst = order.instrument
        print(f"\n  Status:        {order.status.value}")
        print(f"  Symbol:        {inst.symbol} ({inst.type.value})")
        print(f"  Side:          {order.side.value}")
        print(f"  Order Type:    {order.type.value}")
        if order.bracket_id:
            role = "entry" if order.bracket_id == order.order_id else "exit leg"
            print(f"  Bracket ID:    {order.bracket_id}  ({role} of a bracket order)")

        if order.quantity is not None:
            print(f"  Quantity:      {order.quantity}")
        if order.notional_value is not None:
            print(f"  Notional:      ${order.notional_value:,.2f}")
        if order.filled_quantity is not None:
            print(f"  Filled:        {order.filled_quantity}")
        if order.average_price is not None:
            print(f"  Avg Price:     ${order.average_price}")
        if order.limit_price is not None:
            print(f"  Limit Price:   ${order.limit_price}")
        if order.stop_price is not None:
            print(f"  Stop Price:    ${order.stop_price}")
        if order.open_close_indicator is not None:
            print(f"  Open/Close:    {order.open_close_indicator.value}")
        if order.expiration is not None and order.expiration.time_in_force is not None:
            print(f"  Time in Force: {order.expiration.time_in_force.value}")
        if order.equity_market_session is not None:
            # Response-side vocabulary (REGULAR / REST_OF_DAY / TWENTY_FOUR_HOURS) — printed as reported,
            # it is not the same set of names used by --session when placing an order.
            print(f"  Session:       {order.equity_market_session.value}")

        print("\n  Timeline:")
        print(f"    Created:       {_fmt_ts(order.created_at) or 'n/a'}")
        if order.filled_at:
            print(f"    Filled:        {_fmt_ts(order.filled_at)}")
        if order.replaced_at:
            print(f"    Replaced:      {_fmt_ts(order.replaced_at)}")
        if order.closed_at:
            print(f"    Closed:        {_fmt_ts(order.closed_at)}")
        if order.last_modified:
            print(f"    Last Modified: {_fmt_ts(order.last_modified)}")
        if order.reject_reason:
            print(f"\n  Reject Reason: {order.reject_reason}")

        if order.legs:
            print("\n  Legs:")
            for i, leg in enumerate(order.legs, 1):
                oc = f" ({leg.open_close_indicator.value})" if leg.open_close_indicator else ""
                ratio = f" x{leg.ratio_quantity}" if leg.ratio_quantity else ""
                print(f"    [{i}] {leg.side.value} {leg.instrument.symbol}{oc}{ratio}")

        if order.trades:
            print(f"\n  Trades ({len(order.trades)} fill(s)):")
            for i, trade in enumerate(order.trades, 1):
                side = trade.side.value if trade.side else order.side.value
                qty = trade.quantity if trade.quantity is not None else "?"
                price = f"${trade.price}" if trade.price is not None else "?"
                when = _fmt_ts(trade.timestamp) or "n/a"
                trade_id = f"  id {trade.trade_id}" if trade.trade_id else ""
                print(f"    [{i}] {side} {qty} {trade.instrument.symbol} @ {price}  {when}{trade_id}")
        else:
            print("\n  Trades:        none yet")

        print("\n" + "=" * 70)

        client.close()
    except Exception as e:
        print(f"Error fetching order: {e}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Get the status, timeline and individual fills of a specific order "
                    "(only orders created within the last 30 days)"
    )
    parser.add_argument("--order-id", required=True, help="The order ID to look up")
    parser.add_argument("--account-id", help="Account ID (uses PUBLIC_COM_ACCOUNT_ID if not provided)")
    args = parser.parse_args()
    get_order(order_id=args.order_id, account_id=args.account_id)
