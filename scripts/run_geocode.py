"""
Standalone geocoding runner.

Tier 1: Nominatim landmark lookup (all sites without coordinates)
Tier 2: Claude AI address lookup (sites Tier 1 couldn't precisely locate)

Usage:
    python scripts/run_geocode.py                        # Tier 1 only
    python scripts/run_geocode.py --ai-lookup            # Tier 1 + Tier 2
    python scripts/run_geocode.py --ai-lookup --limit 50 # Tier 2 limited to 50
    python scripts/run_geocode.py --ai-only --limit 10   # Tier 2 only (skip Tier 1)
"""

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import GEOPACKAGE_PATH
from src.db.connection import db_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
sys.stdout.reconfigure(line_buffering=True)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Geocode historic sites")
    parser.add_argument(
        "--ai-lookup",
        action="store_true",
        help="Run Tier 2 AI address lookup after Nominatim",
    )
    parser.add_argument(
        "--ai-only",
        action="store_true",
        help="Skip Tier 1, run only Tier 2 AI lookup",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of sites for AI lookup",
    )
    args = parser.parse_args()

    if not GEOPACKAGE_PATH.exists():
        logger.error("Database not found: %s. Run the pipeline first.", GEOPACKAGE_PATH)
        sys.exit(1)

    start_time = time.time()

    with db_connection() as conn:
        # Pre-stats
        total = conn.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
        with_coords = conn.execute(
            "SELECT COUNT(*) FROM sites WHERE latitude IS NOT NULL"
        ).fetchone()[0]
        logger.info("Before geocoding: %d/%d sites have coordinates", with_coords, total)

        # Tier 1: Census + Nominatim
        if not args.ai_only:
            logger.info("=== TIER 1: Census + Nominatim Geocoding ===")
            from src.ingest.geocoder import run_geocoding

            geo_stats = run_geocoding(conn)
            logger.info("Tier 1 results: %s", geo_stats)

            with_coords = conn.execute(
                "SELECT COUNT(*) FROM sites WHERE latitude IS NOT NULL"
            ).fetchone()[0]
            logger.info("After Tier 1: %d/%d sites have coordinates", with_coords, total)

        # Tier 2: AI address lookup
        if args.ai_lookup or args.ai_only:
            logger.info("=== TIER 2: AI Address Lookup ===")
            from src.geocode.ai_address_lookup import lookup_addresses

            ai_stats = lookup_addresses(conn, limit=args.limit)
            logger.info("Tier 2 results: %s", ai_stats)

            with_coords = conn.execute(
                "SELECT COUNT(*) FROM sites WHERE latitude IS NOT NULL"
            ).fetchone()[0]
            logger.info("After Tier 2: %d/%d sites have coordinates", with_coords, total)

        # Final summary
        elapsed = time.time() - start_time
        with_coords = conn.execute(
            "SELECT COUNT(*) FROM sites WHERE latitude IS NOT NULL"
        ).fetchone()[0]
        missing = total - with_coords

        # Quality breakdown
        quality_counts = conn.execute(
            "SELECT geocode_quality, COUNT(*) FROM sites "
            "WHERE geocode_quality IS NOT NULL GROUP BY geocode_quality"
        ).fetchall()

        logger.info("=" * 50)
        logger.info("GEOCODING COMPLETE in %.1f seconds", elapsed)
        logger.info("  Total sites: %d", total)
        logger.info("  With coordinates: %d", with_coords)
        logger.info("  Still missing: %d", missing)
        for row in quality_counts:
            logger.info("  Quality '%s': %d", row[0], row[1])
        logger.info("=" * 50)


if __name__ == "__main__":
    main()
