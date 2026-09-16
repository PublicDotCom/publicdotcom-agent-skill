import argparse
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from config import ensure_sdk, get_api_secret, get_account_id, create_client

# Install/upgrade the pinned SDK before importing it (see config.SDK_VERSION).
ensure_sdk()
from public_api_sdk import (
    OrderRequest,
    OrderInstrument,
    InstrumentType,
    OrderSide,
    OrderType,
    OrderExpirationRequest,
    TimeInForce,
    EquityMarketSession,
    OpenCloseIndicator,
    OrderClass,
    TakeProfit,
    StopLoss,
    GatewayTaxLotMatchingInstruction,
)

BRACKET_CLASSES = ("BRACKET", "OCO", "OTO")


def place_order(
    symbol,
    instrument_type,
    side,
    order_type,
    quantity=None,
    amount=None,
    limit_price=None,
    stop_price=None,
    session=None,
    open_close=None,
    time_in_force=None,
    expiration_time=None,
    order_class=None,
    take_profit_limit=None,
    stop_loss_stop=None,
    stop_loss_limit=None,
    tax_lots=None,
    account_id=None,
):
    secret = get_api_secret()
    account_id = account_id or get_account_id()

    if not secret:
        print("Error: PUBLIC_COM_SECRET is not set.")
        sys.exit(1)

    if not account_id:
        print("Error: No account ID provided. Either pass --account-id or set PUBLIC_COM_ACCOUNT_ID.")
        sys.exit(1)

    # Validate quantity/amount
    if quantity is None and amount is None:
        print("Error: Either --quantity or --amount must be provided.")
        sys.exit(1)

    # Validate limit price for LIMIT/STOP_LIMIT orders
    if order_type in ["LIMIT", "STOP_LIMIT"] and limit_price is None:
        print(f"Error: --limit-price is required for {order_type} orders.")
        sys.exit(1)

    # Validate stop price for STOP/STOP_LIMIT orders
    if order_type in ["STOP", "STOP_LIMIT"] and stop_price is None:
        print(f"Error: --stop-price is required for {order_type} orders.")
        sys.exit(1)

    # Bracket-order validation. Only the rules the API documents are checked
    # here; the SDK's OrderRequest enforces the rest (whole-share quantity,
    # EQUITY/OPTION only, no --amount) so the two can't drift apart.
    is_bracket = order_class in BRACKET_CLASSES
    if not is_bracket and any(v is not None for v in (take_profit_limit, stop_loss_stop, stop_loss_limit)):
        print("Error: --take-profit-limit / --stop-loss-stop / --stop-loss-limit require --order-class BRACKET, OCO or OTO.")
        sys.exit(1)
    if is_bracket and take_profit_limit is None and stop_loss_stop is None:
        print(f"Error: --order-class {order_class} needs at least one exit leg: --take-profit-limit and/or --stop-loss-stop.")
        sys.exit(1)
    if stop_loss_limit is not None and stop_loss_stop is None:
        print("Error: --stop-loss-limit requires --stop-loss-stop.")
        sys.exit(1)
    if is_bracket and session == "EXTENDED":
        print("Error: bracket orders must use the CORE session.")
        sys.exit(1)

    # Tax-lot selection validation (server enforces the full rule set)
    if tax_lots:
        if len(tax_lots) > 8:
            print("Error: at most 8 --tax-lot instructions are allowed per order.")
            sys.exit(1)
        if not (instrument_type == "EQUITY" and side == "SELL" and open_close == "CLOSE"):
            print("Error: --tax-lot is only valid for an EQUITY SELL order with --open-close CLOSE.")
            sys.exit(1)
        if quantity is None:
            print("Error: --tax-lot requires --quantity (the lot quantities must sum to it).")
            sys.exit(1)

    # Map string values to enums
    instrument_type_map = {
        "EQUITY": InstrumentType.EQUITY,
        "OPTION": InstrumentType.OPTION,
        "CRYPTO": InstrumentType.CRYPTO,
    }
    side_map = {
        "BUY": OrderSide.BUY,
        "SELL": OrderSide.SELL,
    }
    order_type_map = {
        "LIMIT": OrderType.LIMIT,
        "MARKET": OrderType.MARKET,
        "STOP": OrderType.STOP,
        "STOP_LIMIT": OrderType.STOP_LIMIT,
    }
    session_map = {
        "CORE": EquityMarketSession.CORE,
        "EXTENDED": EquityMarketSession.EXTENDED,
    }
    open_close_map = {
        "OPEN": OpenCloseIndicator.OPEN,
        "CLOSE": OpenCloseIndicator.CLOSE,
    }
    time_in_force_map = {
        "DAY": TimeInForce.DAY,
        "GTD": TimeInForce.GTD,
    }
    if time_in_force and time_in_force not in time_in_force_map:
        print(f"Error: Invalid --time-in-force '{time_in_force}'. Must be DAY or GTD.")
        sys.exit(1)
    if time_in_force == "GTD" and not expiration_time:
        print("Error: --expiration-time YYYY-MM-DD is required when --time-in-force is GTD")
        sys.exit(1)
    expiration_time_dt = None
    if expiration_time:
        expiration_time_dt = datetime.fromisoformat(expiration_time)
        if expiration_time_dt.tzinfo is None:
            expiration_time_dt = expiration_time_dt.replace(tzinfo=timezone.utc)

    try:
        client = create_client(secret, account_id)

        # Build order request
        order_kwargs = {
            "order_id": str(uuid.uuid4()),
            "instrument": OrderInstrument(
                symbol=symbol,
                type=instrument_type_map[instrument_type],
            ),
            "order_side": side_map[side],
            "order_type": order_type_map[order_type],
            "expiration": OrderExpirationRequest(
                time_in_force=time_in_force_map.get(time_in_force, TimeInForce.DAY),
                expiration_time=expiration_time_dt,
            ),
        }

        # Add quantity or amount
        if quantity is not None:
            order_kwargs["quantity"] = Decimal(str(quantity))
        if amount is not None:
            order_kwargs["amount"] = Decimal(str(amount))

        # Add limit price if applicable
        if limit_price is not None:
            order_kwargs["limit_price"] = Decimal(str(limit_price))

        # Add stop price if applicable
        if stop_price is not None:
            order_kwargs["stop_price"] = Decimal(str(stop_price))

        # Add session for equity orders
        if session and instrument_type == "EQUITY":
            order_kwargs["equity_market_session"] = session_map[session]

        # Add open/close indicator for options and equity closes (tax-lot sells)
        if open_close and instrument_type in ("OPTION", "EQUITY"):
            order_kwargs["open_close_indicator"] = open_close_map[open_close]

        # Bracket order: class + exit legs
        if order_class:
            order_kwargs["order_class"] = OrderClass[order_class]
        if take_profit_limit is not None:
            order_kwargs["take_profit"] = TakeProfit(limit_price=Decimal(str(take_profit_limit)))
        if stop_loss_stop is not None:
            stop_loss_kwargs = {"stop_price": Decimal(str(stop_loss_stop))}
            if stop_loss_limit is not None:
                stop_loss_kwargs["limit_price"] = Decimal(str(stop_loss_limit))
            order_kwargs["stop_loss"] = StopLoss(**stop_loss_kwargs)

        # Specific tax lots to sell
        if tax_lots:
            order_kwargs["tax_lot_matching_instructions"] = [
                GatewayTaxLotMatchingInstruction(tax_lot_id=lot_id, quantity=lot_qty)
                for lot_id, lot_qty in tax_lots
            ]

        order_request = OrderRequest(**order_kwargs)
        order_response = client.place_order(order_request)

        print("Order Placed Successfully!")
        print("-" * 40)
        print(f"Order ID: {order_response.order_id}")
        print(f"Symbol: {symbol}")
        print(f"Side: {side}")
        print(f"Type: {order_type}")
        print(f"Time In Force: {time_in_force or 'DAY'}")
        if quantity is not None:
            print(f"Quantity: {quantity} shares")
        if amount is not None:
            print(f"Amount: ${amount}")
        if limit_price is not None:
            print(f"Limit Price: ${limit_price}")
        if stop_price is not None:
            print(f"Stop Price: ${stop_price}")
        if is_bracket:
            print(f"Order Class: {order_class}")
            if take_profit_limit is not None:
                print(f"Take Profit: LIMIT @ ${take_profit_limit}")
            if stop_loss_stop is not None:
                kind = "STOP_LIMIT" if stop_loss_limit is not None else "STOP"
                detail = f"stop ${stop_loss_stop}" + (f", limit ${stop_loss_limit}" if stop_loss_limit is not None else "")
                print(f"Stop Loss: {kind} ({detail})")
            print(f"Bracket ID: {order_response.order_id}")
            print("Exit legs are submitted automatically once this entry fills; every leg")
            print("reports the Bracket ID above, so get_orders.py can group them.")
        if tax_lots:
            print(f"Tax Lots: {len(tax_lots)} specific lot(s) requested")
        print("-" * 40)

        client.close()
    except Exception as e:
        print(f"Error placing order: {e}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Place an order on Public.com",
        epilog="Examples:\n"
               "  Limit buy:\n"
               "    python3 place_order.py --symbol AAPL --type EQUITY --side BUY --order-type LIMIT --quantity 10 --limit-price 227.50\n\n"
               "  Bracket entry with take-profit and stop-loss exits:\n"
               "    python3 place_order.py --symbol AAPL --type EQUITY --side BUY --order-type LIMIT --quantity 10 --limit-price 227.50 \\\n"
               "      --order-class BRACKET --take-profit-limit 240.00 --stop-loss-stop 220.00\n\n"
               "  Sell specific tax lots (IDs from get_tax_lots.py --symbol AAPL):\n"
               "    python3 place_order.py --symbol AAPL --type EQUITY --side SELL --order-type MARKET --quantity 10 --open-close CLOSE \\\n"
               "      --tax-lot LOT_A:6 --tax-lot LOT_B:4",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--symbol", required=True, help="Stock/crypto/option symbol")
    parser.add_argument(
        "--type",
        required=True,
        choices=["EQUITY", "OPTION", "CRYPTO"],
        help="Instrument type",
    )
    parser.add_argument(
        "--side",
        required=True,
        choices=["BUY", "SELL"],
        help="Order side",
    )
    parser.add_argument(
        "--order-type",
        required=True,
        choices=["LIMIT", "MARKET", "STOP", "STOP_LIMIT"],
        help="Order type",
    )
    parser.add_argument("--quantity", type=float, help="Number of shares")
    parser.add_argument("--amount", type=float, help="Notional dollar amount")
    parser.add_argument("--limit-price", type=float, help="Limit price (required for LIMIT/STOP_LIMIT)")
    parser.add_argument("--stop-price", type=float, help="Stop price (required for STOP/STOP_LIMIT)")
    parser.add_argument(
        "--session",
        choices=["CORE", "EXTENDED"],
        default="CORE",
        help="Market session (CORE or EXTENDED)",
    )
    parser.add_argument(
        "--open-close",
        choices=["OPEN", "CLOSE"],
        help="Open/Close indicator for options (also CLOSE on an equity SELL when using --tax-lot)",
    )
    parser.add_argument(
        "--time-in-force",
        choices=["DAY", "GTD"],
        default="DAY",
        help="Time in force: DAY (default) or GTD (Good Till Date — requires --expiration-time)",
    )
    parser.add_argument(
        "--expiration-time",
        help="Required when --time-in-force=GTD. YYYY-MM-DD or ISO 8601. Max 90 days out.",
    )
    parser.add_argument(
        "--order-class",
        choices=["SIMPLE", "BRACKET", "OCO", "OTO"],
        help="SIMPLE (default) places a standalone order. BRACKET/OCO/OTO attach exit legs "
             "(--take-profit-limit and/or --stop-loss-stop) that submit once this entry fills. "
             "EQUITY/OPTION only, whole-share --quantity, CORE session, entry LIMIT or MARKET (LIMIT only for OCO).",
    )
    parser.add_argument("--take-profit-limit", type=float, help="Bracket: limit price of the take-profit exit leg")
    parser.add_argument("--stop-loss-stop", type=float, help="Bracket: stop price of the stop-loss exit leg (placed as a STOP order)")
    parser.add_argument(
        "--stop-loss-limit",
        type=float,
        help="Bracket: make the stop-loss leg a STOP_LIMIT at this limit price (requires --stop-loss-stop)",
    )
    parser.add_argument(
        "--tax-lot",
        action="append",
        dest="tax_lots",
        metavar="LOT_ID:QUANTITY",
        help="Sell specific tax lots (repeat, max 8). EQUITY SELL with --open-close CLOSE only; MARKET or DAY LIMIT; "
             "quantities must sum to --quantity. Get Lot Selection IDs from get_tax_lots.py --symbol SYMBOL.",
    )
    parser.add_argument("--account-id", help="Account ID (uses PUBLIC_COM_ACCOUNT_ID if not provided)")

    args = parser.parse_args()

    tax_lots = None
    if args.tax_lots:
        tax_lots = []
        for spec in args.tax_lots:
            if ":" not in spec:
                parser.error(f"--tax-lot '{spec}' must be LOT_ID:QUANTITY")
            lot_id, lot_qty = spec.rsplit(":", 1)
            tax_lots.append((lot_id, lot_qty))

    place_order(
        symbol=args.symbol,
        instrument_type=args.type,
        side=args.side,
        order_type=args.order_type,
        quantity=args.quantity,
        amount=args.amount,
        limit_price=args.limit_price,
        stop_price=args.stop_price,
        session=args.session,
        open_close=args.open_close,
        time_in_force=args.time_in_force,
        expiration_time=args.expiration_time,
        order_class=args.order_class,
        take_profit_limit=args.take_profit_limit,
        stop_loss_stop=args.stop_loss_stop,
        stop_loss_limit=args.stop_loss_limit,
        tax_lots=tax_lots,
        account_id=args.account_id,
    )
