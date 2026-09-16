import argparse
import base64
import sys

from config import ensure_sdk, get_api_secret, get_account_id, create_client

# Install/upgrade the pinned SDK before importing it (see config.SDK_VERSION).
ensure_sdk()


def _fmt_money(value):
    return f"${value:,.2f}" if value is not None else "n/a"


def _signed_money(value):
    if value is None:
        return "n/a"
    sign = "+" if value >= 0 else "-"
    return f"{sign}${abs(value):,.2f}"


def _print_out_of_date(status, indent="      "):
    if not status:
        return
    line = f"{indent}Out of date: {status.type.value}"
    if status.description and status.description.header:
        line += f" — {status.description.header}"
    print(line)
    if status.order:
        print(f"{indent}  Related order: {status.order.id} ({status.order.description})")


def print_summary(summary):
    print("=" * 70)
    print(f"UNREALIZED TAX LOTS — as of {summary.as_of}")
    print("=" * 70)
    print(f"\n  Total P/L:       {_signed_money(summary.total_profit_loss)}")
    print(f"  Short term:      {_signed_money(summary.short_term)}")
    print(f"  Long term:       {_signed_money(summary.long_term)}")
    print(f"  60/40 term:      {_signed_money(summary.sixty_forty_term)}")

    if not summary.lots:
        print("\n  No unrealized lots.")
        print("\n" + "=" * 70)
        return

    print(f"\n  {len(summary.lots)} symbol(s):")
    for lot in summary.lots:
        print(f"\n  {lot.symbol} — {lot.company_name}")
        print(f"    Quantity:        {lot.quantity}")
        print(f"    Unit Cost:       {_fmt_money(lot.unit_cost)}")
        print(f"    Cost Basis:      {_fmt_money(lot.cost_basis)}")
        print(f"    Current Price:   {_fmt_money(lot.current_price)}")
        print(f"    Current Value:   {_fmt_money(lot.current_value)}")
        print(f"    Gain/Loss:       {_signed_money(lot.gain_loss)}"
              f"  (ST {_signed_money(lot.short_term_gain_loss)}, LT {_signed_money(lot.long_term_gain_loss)})")
        if lot.details:
            d = lot.details
            print(f"    Option:          {d.root_symbol} {d.option_type.value} {d.strike_price} exp {d.expiration_date}")
        if lot.lot_selection_id:
            print(f"    Lot Selection ID: {lot.lot_selection_id}")
        _print_out_of_date(lot.out_of_date_status, indent="    ")

    print("\n  Run with --symbol SYMBOL to see the individual lots for one holding.")
    print("\n" + "=" * 70)


def print_detail(detail, price=None):
    print("=" * 70)
    print(f"UNREALIZED TAX LOTS: {detail.symbol} — {detail.company_name}  (as of {detail.as_of})")
    if price is not None:
        print(f"  Valued at supplied price: ${price}")
    print("=" * 70)

    if detail.details:
        d = detail.details
        print(f"\n  Option: {d.root_symbol} {d.option_type.value} strike {d.strike_price} exp {d.expiration_date}")

    lots = detail.lots or []
    if not lots:
        print("\n  No open lots for this symbol.")
        print("\n" + "=" * 70)
        return

    total_qty = sum(l.quantity for l in lots)
    total_gl = sum(l.gain_loss for l in lots)
    print(f"\n  {len(lots)} lot(s), {total_qty} total, gain/loss {_signed_money(total_gl)}")

    for i, lot in enumerate(lots, 1):
        print(f"\n  [{i}] opened {lot.open_date}  ({lot.term})")
        print(f"      Quantity:       {lot.quantity}")
        print(f"      Unit Cost:      {_fmt_money(lot.unit_cost)}"
              + (f"  (open buy price {_fmt_money(lot.open_buy_price)})" if lot.open_buy_price is not None else ""))
        print(f"      Cost Basis:     {_fmt_money(lot.cost_basis)}")
        print(f"      Current Price:  {_fmt_money(lot.current_price)}")
        print(f"      Current Value:  {_fmt_money(lot.current_value)}")
        print(f"      Gain/Loss:      {_signed_money(lot.gain_loss)}"
              f"  (ST {_signed_money(lot.short_term_gain_loss)}, LT {_signed_money(lot.long_term_gain_loss)})")
        if lot.wash_sale:
            print("      Wash Sale:      YES")
        if lot.lot_selection_id:
            print(f"      Lot Selection ID: {lot.lot_selection_id}")
        else:
            print("      Lot Selection ID: (not selectable)")
        _print_out_of_date(lot.out_of_date_status)

    print("\n  To sell specific lots, pass their Lot Selection IDs to place_order.py via"
          " --tax-lot LOT_ID:QUANTITY (SELL, EQUITY, --open-close CLOSE).")
    print("\n" + "=" * 70)


def export_csv(client, out_path):
    csv_file = client.get_unrealized_tax_lots_csv()
    if not csv_file.base64_data:
        print("Error: the API returned an empty CSV export.")
        sys.exit(1)
    raw = base64.b64decode(csv_file.base64_data)
    if out_path == "-":
        sys.stdout.write(raw.decode("utf-8", errors="replace"))
        return
    target = out_path or csv_file.file_name or "tax_lots.csv"
    with open(target, "wb") as fh:
        fh.write(raw)
    rows = max(raw.count(b"\n") - 1, 0)
    print(f"Wrote {rows} tax-lot row(s) to {target}")


def get_tax_lots(symbol=None, price=None, csv=False, out=None, account_id=None):
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

        if csv:
            export_csv(client, out)
        elif symbol:
            detail = client.get_unrealized_tax_lots_for_symbol(symbol.upper(), price=price)
            print_detail(detail, price=price)
        else:
            summary = client.get_unrealized_tax_lots()
            print_summary(summary)

        client.close()
    except Exception as e:
        print(f"Error fetching tax lots: {e}")
        print("Note: tax-lot endpoints require an API key with the trading.read scope.")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Show unrealized tax lots for an account (summary, per-symbol detail, or CSV export)",
        epilog="Examples:\n"
               "  Account-wide summary grouped by symbol:\n"
               "    python3 get_tax_lots.py\n\n"
               "  Every open lot for one symbol:\n"
               "    python3 get_tax_lots.py --symbol AAPL\n\n"
               "  Re-value AAPL lots at a hypothetical price:\n"
               "    python3 get_tax_lots.py --symbol AAPL --price 250.00\n\n"
               "  Export the full lot list as CSV (to a file, or '-' for stdout):\n"
               "    python3 get_tax_lots.py --csv --out my_lots.csv",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--symbol", help="Show individual lots for this symbol instead of the summary")
    parser.add_argument(
        "--price",
        help="With --symbol: value the lots at this price instead of the current market price",
    )
    parser.add_argument("--csv", action="store_true", help="Export all lots as CSV instead of printing")
    parser.add_argument("--out", help="With --csv: output path (default: server file name), or '-' for stdout")
    parser.add_argument("--account-id", help="Account ID (uses PUBLIC_COM_ACCOUNT_ID if not provided)")

    args = parser.parse_args()

    if args.price and not args.symbol:
        parser.error("--price requires --symbol")
    if args.out and not args.csv:
        parser.error("--out requires --csv")
    if args.csv and args.symbol:
        parser.error("--csv exports every lot; it cannot be combined with --symbol")

    get_tax_lots(
        symbol=args.symbol,
        price=args.price,
        csv=args.csv,
        out=args.out,
        account_id=args.account_id,
    )
