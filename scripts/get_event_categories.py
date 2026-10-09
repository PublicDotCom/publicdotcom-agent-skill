import argparse
import sys

from config import get_api_secret, get_account_id, create_client


def get_event_categories():
    """List the event-contract (prediction market) categories, their subcategories and frequency filters."""
    secret = get_api_secret()

    if not secret:
        print("Error: PUBLIC_COM_SECRET is not set.")
        sys.exit(1)

    try:
        client = create_client(secret, get_account_id())

        response = client.get_event_categories()

        print("=" * 70)
        print(f"EVENT CATEGORIES — {len(response.categories)} categor{'y' if len(response.categories) == 1 else 'ies'}")
        print("=" * 70)

        if not response.categories:
            print("\n  No categories returned.")

        for category in response.categories:
            print(f"\n  🗂️  {category.category}")
            if category.subcategories:
                print(f"     Subcategories: {', '.join(category.subcategories)}")
            freq = category.event_frequency
            if freq is not None and freq.show and freq.frequencies:
                print(f"     Frequencies:   {', '.join(f.value for f in freq.frequencies)}")

        print("\n  Next: get_event_summary.py --category <CATEGORY> to list its events.")
        print("\n" + "=" * 70)

        client.close()
    except Exception as e:
        print(f"Error fetching event categories: {e}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="List event-contract (prediction market) categories, their subcategories, "
                    "and the frequency filters each supports",
        epilog="Example:\n"
               "  python3 get_event_categories.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.parse_args()
    get_event_categories()
