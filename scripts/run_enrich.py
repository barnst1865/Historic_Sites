"""
AI enrichment runner script.

Usage:
    python scripts/run_enrich.py                 # Enrich all pending sites
    python scripts/run_enrich.py --limit 50      # Enrich first 50 sites
    python scripts/run_enrich.py --force          # Re-enrich all sites
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import GEOPACKAGE_PATH
from src.db.connection import db_connection
from src.enrich.batch_processor import run_enrichment

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Run AI enrichment")
    parser.add_argument("--limit", type=int, help="Max sites to enrich")
    parser.add_argument("--force", action="store_true", help="Re-enrich all sites")
    args = parser.parse_args()

    if not GEOPACKAGE_PATH.exists():
        logger.error(
            "Database not found. Run ingest first: python scripts/run_ingest.py --source nhl"
        )
        sys.exit(1)

    with db_connection() as conn:
        stats = run_enrichment(conn, limit=args.limit, force=args.force)
        logger.info("Enrichment results: %s", stats)


if __name__ == "__main__":
    main()
