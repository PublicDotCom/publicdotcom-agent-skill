import argparse
import sys

from config import ensure_sdk, get_api_secret, get_account_id, create_client

# Install/upgrade the pinned SDK before importing it (see config.SDK_VERSION).
ensure_sdk()


def _row(label, value, suffix=""):
    if value is None or value == "":
        return
    print(f"    {label:<22}{value}{suffix}")


def get_bond_details(symbol, account_id=None):
    secret = get_api_secret()
    account_id = account_id or get_account_id()

    if not secret:
        print("Error: PUBLIC_COM_SECRET is not set.")
        sys.exit(1)

    try:
        client = create_client(secret, account_id)

        bond = client.get_bond_details(symbol=symbol.upper(), account_id=account_id)

        print("=" * 70)
        print(f"BOND DETAILS: {bond.symbol or symbol.upper()}")
        if bond.description:
            print(f"  {bond.description}")
        print("=" * 70)

        print("\n  IDENTITY")
        _row("CUSIP:", bond.cusip)
        issuer = bond.issuer
        if issuer and bond.issuer_symbol:
            issuer = f"{issuer} ({bond.issuer_symbol})"
        _row("Issuer:", issuer)
        kind = bond.bond_type
        if kind and bond.treasury_subtype:
            kind += f" / {bond.treasury_subtype}"
        if kind and bond.treasury_duration:
            kind += f" ({bond.treasury_duration})"
        _row("Type:", kind)
        _row("Status:", bond.bond_status)
        _row("Seniority:", bond.seniority)
        country = bond.country_issue
        if country and bond.country_domicile and bond.country_domicile != country:
            country = f"{country} (issuer domiciled in {bond.country_domicile})"
        _row("Country:", country)

        print("\n  PRICING")
        _row("Current Price:", bond.current_price)
        _row("Current Yield:", bond.current_yield, "%")
        _row("Par Value:", bond.par_value)
        _row("Accrued Interest:", bond.accrued_interest)
        _row("Issue Price:", bond.issue_price)
        _row("Issue Size:", bond.issue_size)
        _row("Min Order Size:", bond.minimum_order_size)
        _row("Min Order Increment:", bond.minimum_order_increment)
        if bond.partial_par is not None:
            _row("Partial Par:", "yes" if bond.partial_par else "no")
        _row("Liquidity Rating:", bond.liquidity_rating, "/5" if bond.liquidity_rating else "")

        print("\n  COUPON")
        _row("Coupon:", bond.coupon, "%")
        _row("Frequency:", bond.coupon_frequency)
        _row("Next Coupon Date:", bond.next_coupon_date)

        print("\n  MATURITY & CALLS")
        _row("Issue Date:", bond.issue_date)
        _row("Maturity Date:", bond.maturity_date)
        _row("Days Until Maturity:", bond.days_until_maturity)
        if bond.perpetual is not None:
            _row("Perpetual:", "yes" if bond.perpetual else "no")
        if bond.callable is not None:
            _row("Callable:", "yes" if bond.callable else "no")
        _row("Next Call Date:", bond.next_call_date)
        _row("Next Call Price:", bond.next_call_price)

        print("\n  RATINGS")
        rating = bond.rating
        if rating and bond.rating_category:
            rating = f"{rating} ({bond.rating_category})"
        _row("S&P Rating:", rating)
        outlook = bond.sp_outlook
        if outlook and bond.sp_outlook_date:
            outlook = f"{outlook} (as of {bond.sp_outlook_date})"
        _row("S&P Outlook:", outlook)
        watch = bond.sp_creditwatch
        if watch and bond.sp_creditwatch_date:
            watch = f"{watch} (as of {bond.sp_creditwatch_date})"
        _row("S&P CreditWatch:", watch)

        print("\n  For a live bid/ask with markup and minimum sizes, run:"
              f" get_quotes.py {bond.symbol or symbol.upper()}:BOND")
        print("\n" + "=" * 70)

        client.close()
    except Exception as e:
        print(f"Error fetching bond details: {e}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Get comprehensive details for a single bond",
        epilog="Example:\n"
               "  python3 get_bond_details.py --symbol 912810TM0-BOND\n\n"
               "Bond symbols are usually CUSIP-BOND. Find them with search_bonds.py.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--symbol", required=True, help="Bond symbol, e.g. 912810TM0-BOND")
    parser.add_argument("--account-id", help="Account ID (uses PUBLIC_COM_ACCOUNT_ID if not provided)")

    args = parser.parse_args()
    get_bond_details(symbol=args.symbol, account_id=args.account_id)
