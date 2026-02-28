"""
CLI manual review interface.

Presents flagged sites one at a time for human review.
Supports approve, modify, skip, and export actions.

Usage:
    python scripts/review_tool.py              # Interactive review
    python scripts/review_tool.py --stats      # Show review statistics
    python scripts/review_tool.py --export     # Export review queue to CSV
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import GEOPACKAGE_PATH, OUTPUT_DIR
from src.db.connection import db_connection
from src.scoring.review_queue import (
    approve_site,
    flag_site,
    get_review_queue,
    get_review_stats,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def show_stats(conn):
    """Display review queue statistics."""
    stats = get_review_stats(conn)
    print("\n=== Review Queue Statistics ===")
    for status, count in sorted(stats.items()):
        print(f"  {status}: {count}")
    total = sum(stats.values())
    print(f"  Total: {total}")


def review_interactive(conn):
    """Interactive review session."""
    queue = get_review_queue(conn)
    if not queue:
        print("No sites in the review queue.")
        return

    print(f"\n{len(queue)} sites flagged for review.\n")

    for i, site in enumerate(queue):
        print(f"\n--- Site {i + 1}/{len(queue)} ---")
        print(f"  ID:         {site['id']}")
        print(f"  Name:       {site['name']}")
        print(f"  State:      {site.get('state', 'N/A')}")
        print(f"  NRIS:       {site.get('nris_refnum', 'N/A')}")
        print(f"  Score:      {site.get('confidence_score', 'N/A')}")
        print(f"  Priority:   {site.get('review_priority', 'N/A')}")
        desc = site.get("short_description") or site.get("full_description") or "N/A"
        print(f"  Description: {desc[:200]}...")
        print(f"  Coords:     ({site.get('latitude', 'N/A')}, {site.get('longitude', 'N/A')})")

        while True:
            action = input("\n  [a]pprove  [s]kip  [f]lag  [q]uit > ").strip().lower()
            if action == "a":
                notes = input("  Notes (optional): ").strip() or None
                approve_site(conn, site["id"], notes)
                print("  Approved.")
                break
            elif action == "s":
                break
            elif action == "f":
                notes = input("  Flag reason: ").strip()
                flag_site(conn, site["id"], notes)
                print("  Flagged.")
                break
            elif action == "q":
                print("Exiting review.")
                return
            else:
                print("  Invalid action. Try again.")


def export_queue(conn):
    """Export review queue to CSV."""
    queue = get_review_queue(conn)
    if not queue:
        print("No sites in the review queue.")
        return

    import csv

    filepath = OUTPUT_DIR / "review" / "review_queue.csv"
    filepath.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "id", "name", "state", "nris_refnum", "confidence_score",
        "review_priority", "review_status", "reviewer_notes",
        "latitude", "longitude", "short_description",
    ]

    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for site in queue:
            writer.writerow(site)

    print(f"Exported {len(queue)} sites to {filepath}")


def main():
    parser = argparse.ArgumentParser(description="Manual review tool")
    parser.add_argument("--stats", action="store_true", help="Show review statistics")
    parser.add_argument("--export", action="store_true", help="Export review queue to CSV")
    args = parser.parse_args()

    if not GEOPACKAGE_PATH.exists():
        print("Database not found. Run the pipeline first.")
        sys.exit(1)

    with db_connection() as conn:
        if args.stats:
            show_stats(conn)
        elif args.export:
            export_queue(conn)
        else:
            review_interactive(conn)


if __name__ == "__main__":
    main()
