import argparse
import sys

from config import ensure_sdk, get_api_secret, get_account_id, create_client

# Install/upgrade the pinned SDK before importing it (see config.SDK_VERSION).
ensure_sdk()
from public_api_sdk import (
    BondRating,
    BondSearchRequest,
    BondStatus,
    BondType,
    CouponFrequency,
    RatingCategory,
    SortDirection,
    TreasurySubtype,
)


def _names(enum_cls):
    return [e.value for e in enum_cls]


def _tri_state(parser, name, help_text):
    """Add --<name> / --not-<name> flags that map to True / False / None."""
    dest = name.replace("-", "_")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(f"--{name}", dest=dest, action="store_true", default=None, help=f"Only {help_text}")
    group.add_argument(f"--not-{name}", dest=dest, action="store_false", help=f"Exclude {help_text}")


def search_bonds(filters, account_id=None):
    secret = get_api_secret()
    account_id = account_id or get_account_id()

    if not secret:
        print("Error: PUBLIC_COM_SECRET is not set.")
        sys.exit(1)

    try:
        client = create_client(secret, account_id)

        request = BondSearchRequest(**{k: v for k, v in filters.items() if v is not None})
        page = client.search_bonds(request)

        print("=" * 78)
        total = page.total_elements if page.total_elements is not None else len(page.content)
        pages = page.total_pages if page.total_pages is not None else "?"
        current = (page.number if page.number is not None else filters.get("page_number") or 0)
        print(f"BOND SEARCH — {total} match(es), page {current + 1} of {pages}")
        print("=" * 78)

        if not page.content:
            print("\n  No bonds matched these filters.")
            print("\n" + "=" * 78)
            client.close()
            return

        for bond in page.content:
            print(f"\n  {bond.symbol or bond.cusip or '?'}  {bond.description_short or bond.description or ''}")
            kind = bond.bond_type or "?"
            if bond.treasury_subtype:
                kind += f" / {bond.treasury_subtype}"
            if bond.treasury_duration:
                kind += f" ({bond.treasury_duration})"
            print(f"    Type:        {kind}")
            if bond.issuer:
                issuer = bond.issuer + (f" ({bond.issuer_symbol})" if bond.issuer_symbol else "")
                print(f"    Issuer:      {issuer}")
            coupon = f"{bond.coupon}%" if bond.coupon is not None else "n/a"
            if bond.coupon_frequency:
                coupon += f" {bond.coupon_frequency}"
            print(f"    Coupon:      {coupon}")
            maturity = str(bond.maturity_date) if bond.maturity_date else "n/a"
            if bond.days_until_maturity is not None:
                maturity += f" ({bond.days_until_maturity} days)"
            print(f"    Maturity:    {maturity}")
            price = f"{bond.current_price}" if bond.current_price is not None else "n/a"
            yld = f"{bond.current_yield}%" if bond.current_yield is not None else "n/a"
            print(f"    Price/Yield: {price} / {yld}")
            rating = bond.rating or "NR"
            if bond.rating_category:
                rating += f" ({bond.rating_category})"
            print(f"    Rating:      {rating}")
            flags = []
            if bond.callable:
                flags.append("callable" + (f" next {bond.next_call_date}" if bond.next_call_date else ""))
            if bond.perpetual:
                flags.append("perpetual")
            if bond.liquidity_rating is not None:
                flags.append(f"liquidity {bond.liquidity_rating}/5")
            if bond.minimum_order_size is not None:
                flags.append(f"min order {bond.minimum_order_size}")
            if flags:
                print(f"    Notes:       {', '.join(flags)}")

        print("\n  Use get_bond_details.py --symbol <SYMBOL> for the full record of one bond.")
        if page.total_pages and page.total_pages > current + 1:
            print(f"  More results: re-run with --page {current + 1}")
        print("\n" + "=" * 78)

        client.close()
    except Exception as e:
        print(f"Error searching bonds: {e}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Search Public.com's fixed income (bonds) hub with optional filters",
        epilog="Examples:\n"
               "  Investment-grade corporates yielding at least 5%:\n"
               "    python3 search_bonds.py --type CORPORATE --rating-category INVESTMENT_GRADE --min-yield 5\n\n"
               "  Treasury notes maturing in 2028, soonest first:\n"
               "    python3 search_bonds.py --type TREASURY --treasury-subtype NOTE \\\n"
               "      --min-maturity 2028-01-01 --max-maturity 2028-12-31 --sort maturityDate --sort-dir ASC\n\n"
               "  Apple's outstanding bonds:\n"
               "    python3 search_bonds.py --issuer-symbol AAPL --status OUTSTANDING",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--type", nargs="+", choices=_names(BondType), help="Bond type(s)")
    parser.add_argument("--treasury-subtype", nargs="+", choices=_names(TreasurySubtype), help="Treasury subtype(s)")
    parser.add_argument("--status", nargs="+", choices=_names(BondStatus), help="Bond status(es), e.g. OUTSTANDING")
    parser.add_argument("--issuer", help="Issuer name filter")
    parser.add_argument("--issuer-symbol", nargs="+", help="Issuer ticker(s), e.g. AAPL")
    parser.add_argument("--rating", nargs="+", choices=_names(BondRating), metavar="RATING",
                        help="S&P rating(s), e.g. AAA AA+ (NR = not rated)")
    parser.add_argument("--rating-category", choices=_names(RatingCategory), help="INVESTMENT_GRADE or SPECULATIVE_GRADE")
    parser.add_argument("--coupon-frequency", nargs="+", choices=_names(CouponFrequency), help="Coupon frequency filter")
    parser.add_argument("--min-coupon", help="Minimum coupon rate (percent)")
    parser.add_argument("--max-coupon", help="Maximum coupon rate (percent)")
    parser.add_argument("--min-yield", help="Minimum current yield (percent)")
    parser.add_argument("--max-yield", help="Maximum current yield (percent)")
    parser.add_argument("--min-maturity", help="Earliest maturity date, YYYY-MM-DD (server default: today + 14 days)")
    parser.add_argument("--max-maturity", help="Latest maturity date, YYYY-MM-DD")
    parser.add_argument("--min-par", help="Minimum par value")
    parser.add_argument("--max-par", help="Maximum par value")
    parser.add_argument("--liquidity", nargs="+", choices=["1", "2", "3", "4", "5"], help="Liquidity score(s), 1 (low) to 5 (high)")
    parser.add_argument("--min-liquidity", choices=["1", "2", "3", "4", "5"], help="Minimum liquidity score")
    _tri_state(parser, "callable", "callable bonds")
    _tri_state(parser, "perpetual", "perpetual bonds")
    _tri_state(parser, "partial-par", "bonds that allow partial-par trading")
    parser.add_argument("--page", type=int, default=None, help="Page number, zero-based (default 0)")
    parser.add_argument("--page-size", type=int, default=None, help="Results per page (default 20)")
    parser.add_argument("--sort", help="Sort property, e.g. maturityDate, currentYield, coupon")
    parser.add_argument("--sort-dir", choices=_names(SortDirection), help="ASC or DESC (default DESC)")
    parser.add_argument("--account-id", help="Account ID (uses PUBLIC_COM_ACCOUNT_ID if not provided)")

    args = parser.parse_args()

    filters = {
        "bond_type": args.type,
        "treasury_subtype": args.treasury_subtype,
        "bond_status": args.status,
        "issuer": args.issuer,
        "issuer_symbol": args.issuer_symbol,
        "rating": args.rating,
        "rating_category": args.rating_category,
        "coupon_frequency": args.coupon_frequency,
        "min_coupon": args.min_coupon,
        "max_coupon": args.max_coupon,
        "min_current_yield": args.min_yield,
        "max_current_yield": args.max_yield,
        "min_maturity_date": args.min_maturity,
        "max_maturity_date": args.max_maturity,
        "min_par_value": args.min_par,
        "max_par_value": args.max_par,
        "liquidity_rating": args.liquidity,
        "min_liquidity_rating": args.min_liquidity,
        "callable": args.callable,
        "perpetual": args.perpetual,
        "partial_par": args.partial_par,
        "page_number": args.page,
        "page_size": args.page_size,
        "sort_property": args.sort,
        "sort_direction": args.sort_dir,
    }
    search_bonds(filters, account_id=args.account_id)
