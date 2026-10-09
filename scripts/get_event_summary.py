import argparse
import sys
from datetime import datetime, timezone

from config import ensure_sdk, get_api_secret, get_account_id, create_client

# Install/upgrade the pinned SDK before importing it (see config.SDK_VERSION).
ensure_sdk()
from public_api_sdk import (
    EventFrequency,
    EventSortingMode,
    EventSummaryFilters,
    EventSummaryRequest,
)

# The API returns at most this many events per page.
PAGE_SIZE = 100


def _names(enum_cls, exclude=()):
    return [e.value for e in enum_cls if e not in exclude]


def _split(values):
    """Flatten repeated and/or comma-separated flag values, upper-cased, blanks dropped."""
    return [part.strip().upper() for value in values or [] for part in value.split(",") if part.strip()]


def parse_timestamp(value):
    """Parse `YYYY-MM-DD` or an ISO 8601 timestamp into a timezone-aware datetime (naive = UTC).

    A trailing `Z` is accepted (Python 3.9's fromisoformat does not understand it).
    """
    text = value.strip()
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(
            f"Invalid timestamp {value!r}. Use YYYY-MM-DD or ISO 8601, e.g. 2026-12-31T00:00:00Z."
        )
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def build_request(sort="VOLUME", category=None, subcategory=None, next_token=None,
                  include_resolved=None, created_within_days=None, event_symbols=None,
                  frequencies=None, resolution_start=None, resolution_end=None):
    """Turn the parsed flags into an EventSummaryRequest.

    The `filters` block is only sent when a filter flag is given. The API requires both of
    its lists, so an omitted one defaults to `eventSymbols: []` / `frequencies: [ALL]`
    (same as the CLI).
    """
    fields = {"sorting_mode": EventSortingMode(sort)}
    if category is not None:
        fields["category"] = category
    if subcategory is not None:
        fields["subcategory"] = subcategory
    if next_token is not None:
        fields["next_token"] = next_token
    if include_resolved is not None:
        fields["display_resolved_events"] = include_resolved
    if created_within_days is not None:
        fields["created_within_days"] = created_within_days

    symbols = _split(event_symbols)
    freqs = [EventFrequency(f) for f in _split(frequencies)]
    if symbols or freqs or resolution_start or resolution_end:
        filters = {
            "event_symbols": symbols,
            "frequencies": freqs or [EventFrequency.ALL],
        }
        if resolution_start:
            filters["resolution_time_start"] = parse_timestamp(resolution_start)
        if resolution_end:
            filters["resolution_time_end"] = parse_timestamp(resolution_end)
        fields["filters"] = EventSummaryFilters(**filters)

    return EventSummaryRequest(**fields)


def _fmt_ts(value):
    return value.strftime("%Y-%m-%d %H:%M %Z").strip() if value else "n/a"


def get_event_summary(request):
    secret = get_api_secret()

    if not secret:
        print("Error: PUBLIC_COM_SECRET is not set.")
        sys.exit(1)

    try:
        client = create_client(secret, get_account_id())

        page = client.get_event_summary(request)

        print("=" * 78)
        print(f"EVENT SUMMARY — {len(page.content)} event(s), sorted by {request.sorting_mode.value}")
        print("=" * 78)
        active = request.model_dump(by_alias=True, exclude_none=True)
        active.pop("sortingMode", None)
        if active:
            print("  Filters: " + ", ".join(f"{k}={v}" for k, v in active.items()))

        if not page.content:
            print("\n  No events matched.")

        for event in page.content:
            flags = []
            if event.resolved:
                flags.append("RESOLVED")
            if event.halted:
                flags.append("HALTED")
            status = f"  [{', '.join(flags)}]" if flags else ""
            print(f"\n  🎯 {event.title or '(untitled)'}{status}")
            print(f"     Event Symbol: {event.event_symbol}")
            category = event.category or "n/a"
            if event.subcategories:
                category += f" / {', '.join(event.subcategories)}"
            print(f"     Category:     {category}")
            volume = f"{event.volume:,}" if event.volume is not None else "n/a"
            print(f"     Volume:       {volume}  |  Resolves {_fmt_ts(event.resolution_time)}")
            if event.symbols:
                shown = ", ".join(event.symbols[:4])
                more = f" (+{len(event.symbols) - 4} more)" if len(event.symbols) > 4 else ""
                print(f"     Contracts:    {shown}{more}")

        print("\n  Next: get_event_details.py --event-symbol <EVENT SYMBOL> for outcomes and YES/NO prices.")
        if page.next_token:
            print(f"  More results: re-run with the same flags plus --next-token {page.next_token}")
        print("\n" + "=" * 78)

        client.close()
    except Exception as e:
        print(f"Error fetching event summary: {e}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=f"List event-contract (prediction market) events, up to {PAGE_SIZE} per page",
        epilog="Examples:\n"
               "  Highest-volume events:\n"
               "    python3 get_event_summary.py\n\n"
               "  Newest events in a category (see get_event_categories.py):\n"
               "    python3 get_event_summary.py --sort RECENTLY_ADDED --category Economics\n\n"
               "  Daily events resolving before year end, including resolved ones:\n"
               "    python3 get_event_summary.py --frequency ONE_DAY --resolution-end 2026-12-31 --include-resolved\n\n"
               "  Specific events:\n"
               "    python3 get_event_summary.py --event-symbol KALSHI.KXBALANCESHEET-EO26\n\n"
               "  Next page:\n"
               "    python3 get_event_summary.py --next-token <TOKEN>",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--sort", default="VOLUME", type=str.upper, choices=_names(EventSortingMode),
                        help="Sort order (default: VOLUME)")
    parser.add_argument("--category", help="Limit to a category from get_event_categories.py")
    parser.add_argument("--subcategory", help="Limit to a subcategory")
    parser.add_argument("--next-token", help="nextToken from a previous page, to fetch the next page")
    parser.add_argument("--include-resolved", action=argparse.BooleanOptionalAction, default=None,
                        help="Include (or, with --no-include-resolved, exclude) resolved events; "
                             "server default when omitted")
    parser.add_argument("--created-within-days", type=int, metavar="N",
                        help="Only events created within the last N days")
    parser.add_argument("--event-symbol", action="append", metavar="EVENT_SYMBOL",
                        help="Only these events, e.g. KALSHI.KXBALANCESHEET-EO26. Repeat or comma-separate")
    parser.add_argument("--frequency", action="append", metavar="FREQUENCY",
                        help="Event frequency filter: " + ", ".join(_names(EventFrequency, exclude=(EventFrequency.UNKNOWN,)))
                             + ". Repeat for multiple")
    parser.add_argument("--resolution-start", metavar="TIMESTAMP",
                        help="Only events resolving at or after this time (YYYY-MM-DD or ISO 8601; naive = UTC)")
    parser.add_argument("--resolution-end", metavar="TIMESTAMP",
                        help="Only events resolving at or before this time (YYYY-MM-DD or ISO 8601; naive = UTC)")

    args = parser.parse_args()

    valid_frequencies = set(_names(EventFrequency, exclude=(EventFrequency.UNKNOWN,)))
    bad = [f for f in _split(args.frequency) if f not in valid_frequencies]
    if bad:
        parser.error(f"Invalid --frequency {', '.join(bad)}. Expected one of: {', '.join(sorted(valid_frequencies))}")
    if args.created_within_days is not None and args.created_within_days < 1:
        parser.error("--created-within-days must be at least 1")

    try:
        request = build_request(
            sort=args.sort,
            category=args.category,
            subcategory=args.subcategory,
            next_token=args.next_token,
            include_resolved=args.include_resolved,
            created_within_days=args.created_within_days,
            event_symbols=args.event_symbol,
            frequencies=args.frequency,
            resolution_start=args.resolution_start,
            resolution_end=args.resolution_end,
        )
    except ValueError as e:
        parser.error(str(e))

    get_event_summary(request)
