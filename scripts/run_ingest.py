"""
Ingest runner script.

Usage:
    python scripts/run_ingest.py --source nhl           # ArcGIS + spreadsheet
    python scripts/run_ingest.py --source arcgis        # ArcGIS only
    python scripts/run_ingest.py --source spreadsheet   # Spreadsheet only
    python scripts/run_ingest.py --source nps_parks     # NPS Parks API
    python scripts/run_ingest.py --source nominations   # Nomination PDFs
    python scripts/run_ingest.py --source shpo          # State SHPO sources
    python scripts/run_ingest.py --source shpo --states IN,MO  # Specific states
    python scripts/run_ingest.py --source all           # All active sources
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import GEOPACKAGE_PATH, RAW_DIR
from src.db.connection import db_connection
from src.db.schema import create_database
from src.ingest.arcgis_client import fetch_nhls, parse_features
from src.ingest.merger import (
    merge_arcgis_records,
    merge_nps_parks_records,
    merge_shpo_records,
    merge_spreadsheet_records,
)
from src.ingest.nps_parks_client import fetch_parks, parse_parks
from src.ingest.shpo_dispatcher import fetch_state, get_active_states, parse_state
from src.ingest.validator import run_validation, save_validation_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def ingest_arcgis(conn, no_cache: bool = False):
    """Ingest NHL records from ArcGIS REST API."""
    logger.info("=== Ingesting ArcGIS NHLs ===")
    features = fetch_nhls(use_cache=not no_cache)
    sites = parse_features(features)

    report = run_validation(sites)
    save_validation_report(report)
    logger.info(
        "Validation: %d passed, %d warnings, %d failed",
        report["passed"], report["warnings"], report["failed"],
    )

    stats = merge_arcgis_records(conn, sites)
    return stats


def ingest_spreadsheet(conn, filepath: Path | None = None):
    """Ingest NHL records from NPS spreadsheet."""
    logger.info("=== Ingesting NHL Spreadsheet ===")

    if filepath is None:
        # Look for spreadsheet in data/raw/
        candidates = list(RAW_DIR.glob("*NHL*.*")) + list(RAW_DIR.glob("*nhl*.*"))
        xlsx_files = [f for f in candidates if f.suffix in (".xlsx", ".xls", ".csv")]
        if not xlsx_files:
            logger.warning(
                "No NHL spreadsheet found in %s. Download from "
                "https://www.nps.gov/subjects/nationalregister/data-downloads.htm",
                RAW_DIR,
            )
            return {"inserted": 0, "updated": 0, "skipped": 0}
        filepath = xlsx_files[0]
        logger.info("Found spreadsheet: %s", filepath)

    from src.ingest.spreadsheet_loader import load_spreadsheet

    records = load_spreadsheet(filepath, is_nhl=True)
    stats = merge_spreadsheet_records(conn, records)
    return stats


def ingest_nps_parks(conn, no_cache: bool = False):
    """Ingest park records from NPS Parks API."""
    logger.info("=== Ingesting NPS Parks ===")
    parks = fetch_parks(use_cache=not no_cache)
    if not parks:
        logger.warning("No NPS parks data retrieved.")
        return {"inserted": 0, "updated": 0, "skipped": 0, "matched": 0}

    sites = parse_parks(parks)
    stats = merge_nps_parks_records(conn, sites)
    return stats


def ingest_shpo(conn, states: list[str] | None = None, no_cache: bool = False):
    """Ingest records from state SHPO data sources."""
    from config.state_sources import STATE_SOURCES

    active = get_active_states(filter_states=states)
    if not active:
        logger.warning("No active SHPO states to ingest")
        return {}

    logger.info("=== Ingesting SHPO: %s ===", ", ".join(active))
    all_stats = {}

    for source_key in active:
        try:
            logger.info("--- SHPO %s ---", source_key)
            raw = fetch_state(source_key, use_cache=not no_cache)
            sites = parse_state(source_key, raw)

            config = STATE_SOURCES[source_key]

            if config.get("multi_state"):
                # Group records by state and merge each group separately
                from collections import defaultdict
                by_state = defaultdict(list)
                for s in sites:
                    by_state[s.get("state", "XX")].append(s)

                combined = {"inserted": 0, "updated": 0, "matched_nris": 0,
                            "matched_fuzzy": 0, "skipped": 0}
                for st_code in sorted(by_state):
                    st_sites = by_state[st_code]
                    st_stats = merge_shpo_records(conn, st_sites, st_code, config)
                    for k in combined:
                        combined[k] += st_stats.get(k, 0)
                    logger.info("SHPO %s/%s: %s", source_key, st_code, st_stats)
                stats = combined
            else:
                real_state = config.get("state_code", source_key.split("_")[0])
                stats = merge_shpo_records(conn, sites, real_state, config)

            all_stats[source_key] = stats
            logger.info("SHPO %s merge: %s", source_key, stats)
        except Exception:
            logger.exception("SHPO %s failed — continuing with next source", source_key)
            all_stats[source_key] = {"error": True}

    return all_stats


def main():
    parser = argparse.ArgumentParser(description="Ingest historic site data")
    parser.add_argument(
        "--source",
        choices=[
            "nhl", "arcgis", "spreadsheet", "nps_parks",
            "nominations", "nrhp", "shpo", "all",
        ],
        required=True,
        help="Data source to ingest",
    )
    parser.add_argument("--file", type=Path, help="Path to spreadsheet file")
    parser.add_argument(
        "--states", type=str, default=None,
        help="Comma-separated state codes for SHPO ingest (e.g., IN,MO,UT)",
    )
    parser.add_argument("--no-cache", action="store_true", help="Force fresh API fetch")
    args = parser.parse_args()

    # Ensure database exists
    if not GEOPACKAGE_PATH.exists():
        logger.info("Creating database at %s", GEOPACKAGE_PATH)
        create_database()

    state_list = args.states.split(",") if args.states else None

    with db_connection() as conn:
        if args.source == "arcgis":
            ingest_arcgis(conn, no_cache=args.no_cache)
        elif args.source == "spreadsheet":
            ingest_spreadsheet(conn, filepath=args.file)
        elif args.source == "nps_parks":
            ingest_nps_parks(conn, no_cache=args.no_cache)
        elif args.source == "shpo":
            ingest_shpo(conn, states=state_list, no_cache=args.no_cache)
        elif args.source == "nhl":
            # NHL = spreadsheet first (authoritative), then ArcGIS overlay
            ingest_spreadsheet(conn, filepath=args.file)
            ingest_arcgis(conn, no_cache=args.no_cache)
        elif args.source == "all":
            ingest_spreadsheet(conn, filepath=args.file)
            ingest_arcgis(conn, no_cache=args.no_cache)
            ingest_nps_parks(conn, no_cache=args.no_cache)
            ingest_shpo(conn, states=state_list, no_cache=args.no_cache)
        elif args.source == "nominations":
            logger.info("Nomination ingestion — see run_ingest.py --source nominations")
            # Will be implemented in Phase 3
        elif args.source == "nrhp":
            logger.info("Full NRHP ingestion planned for Phase 9")
        else:
            logger.error("Unknown source: %s", args.source)
            sys.exit(1)

        total = conn.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
        with_coords = conn.execute(
            "SELECT COUNT(*) FROM sites WHERE latitude IS NOT NULL"
        ).fetchone()[0]
        logger.info("Database total: %d sites (%d with coordinates)", total, with_coords)


if __name__ == "__main__":
    main()
