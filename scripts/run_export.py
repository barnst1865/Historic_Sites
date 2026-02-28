"""
Export runner script.

Usage:
    python scripts/run_export.py                     # All formats
    python scripts/run_export.py --format kml        # KML/KMZ only
    python scripts/run_export.py --format geojson    # GeoJSON only
    python scripts/run_export.py --format map        # HTML map only
    python scripts/run_export.py --format csv        # CSV only
    python scripts/run_export.py --format csv --review-only  # Review queue CSV
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import GEOPACKAGE_PATH
from src.db.connection import db_connection
from src.export.csv_exporter import export_full_csv, export_review_csv
from src.export.folium_map import generate_map
from src.export.geojson_exporter import export_geojson
from src.export.kml_exporter import export_kml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Export historic site data")
    parser.add_argument(
        "--format",
        choices=["kml", "geojson", "map", "csv", "all"],
        default="all",
        help="Output format (default: all)",
    )
    parser.add_argument(
        "--review-only",
        action="store_true",
        help="Export only review queue (CSV format)",
    )
    args = parser.parse_args()

    if not GEOPACKAGE_PATH.exists():
        logger.error("Database not found. Run the pipeline first.")
        sys.exit(1)

    with db_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
        with_coords = conn.execute(
            "SELECT COUNT(*) FROM sites WHERE latitude IS NOT NULL"
        ).fetchone()[0]
        logger.info("Database: %d sites (%d with coordinates)", total, with_coords)

        if args.format in ("kml", "all"):
            logger.info("=== Exporting KML/KMZ ===")
            result = export_kml(conn)
            logger.info("KML: %d state files, master KMZ: %s",
                        len(result["state_files"]), result["master_kmz"])

        if args.format in ("geojson", "all"):
            logger.info("=== Exporting GeoJSON ===")
            result = export_geojson(conn)
            logger.info("GeoJSON: all=%s, nhls=%s, %d state files",
                        result["all_sites"], result["nhls"], len(result["state_files"]))

        if args.format in ("map", "all"):
            logger.info("=== Generating HTML Map ===")
            path = generate_map(conn)
            logger.info("Map: %s", path)

        if args.format in ("csv", "all"):
            if args.review_only:
                logger.info("=== Exporting Review Queue CSV ===")
                path = export_review_csv(conn)
                logger.info("Review CSV: %s", path)
            else:
                logger.info("=== Exporting CSV ===")
                review_path = export_review_csv(conn)
                full_path = export_full_csv(conn)
                logger.info("Review CSV: %s", review_path)
                logger.info("Full CSV: %s", full_path)


if __name__ == "__main__":
    main()
