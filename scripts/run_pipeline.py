"""
Full end-to-end pipeline orchestrator.

Runs all stages in sequence:
  1. Ingest (ArcGIS + Spreadsheet + NPS Parks)
  2. Validate
  3. Geocode
  4. Profile
  5. Enrich
  6. Score
  7. Export

Usage:
    python scripts/run_pipeline.py
    python scripts/run_pipeline.py --skip-enrich     # Skip AI enrichment
    python scripts/run_pipeline.py --skip-nominations # Skip nomination download
    python scripts/run_pipeline.py --enrich-limit 50  # Limit enrichment batch
"""

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import GEOPACKAGE_PATH
from src.db.connection import db_connection
from src.db.schema import create_database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
# Force unbuffered output so progress messages appear immediately
sys.stdout.reconfigure(line_buffering=True)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Run full historic sites pipeline")
    parser.add_argument("--skip-enrich", action="store_true", help="Skip AI enrichment")
    parser.add_argument("--skip-nominations", action="store_true", help="Skip nomination PDFs")
    parser.add_argument("--skip-shpo", action="store_true", help="Skip state SHPO ingest")
    parser.add_argument("--shpo-states", type=str, default=None,
                        help="Comma-separated state codes for SHPO (e.g., IN,MO,UT)")
    parser.add_argument("--enrich-limit", type=int, help="Limit enrichment batch size")
    parser.add_argument("--no-cache", action="store_true", help="Force fresh API fetches")
    args = parser.parse_args()

    start_time = time.time()
    logger.info("=" * 60)
    logger.info("HISTORIC SITES PIPELINE — Starting")
    logger.info("=" * 60)

    # --- Stage 0: Initialize Database ---
    if not GEOPACKAGE_PATH.exists():
        logger.info("Creating database at %s", GEOPACKAGE_PATH)
        create_database()
    else:
        logger.info("Using existing database: %s", GEOPACKAGE_PATH)

    with db_connection() as conn:
        # --- Stage 1: Ingest ---
        logger.info("\n=== STAGE 1: INGEST ===")

        from config.settings import RAW_DIR
        from src.ingest.arcgis_client import fetch_nhls, parse_features
        from src.ingest.merger import (
            merge_arcgis_records,
            merge_nps_parks_records,
            merge_spreadsheet_records,
        )
        from src.ingest.nps_parks_client import fetch_parks, parse_parks
        from src.ingest.spreadsheet_loader import load_spreadsheet
        from src.ingest.validator import run_validation, save_validation_report

        # Spreadsheet (authoritative NHL list)
        logger.info("--- NHL Spreadsheet ---")
        spreadsheet_stats = {"inserted": 0, "updated": 0, "skipped": 0}
        candidates = (
            list(RAW_DIR.glob("*NHL*.*"))
            + list(RAW_DIR.glob("*nhl*.*"))
            + list(RAW_DIR.glob("*Landmark*.*"))
            + list(RAW_DIR.glob("*landmark*.*"))
        )
        xlsx_files = list({f for f in candidates if f.suffix in (".xlsx", ".xls", ".csv")})
        if xlsx_files:
            records = load_spreadsheet(xlsx_files[0], is_nhl=True)
            spreadsheet_stats = merge_spreadsheet_records(conn, records)
            logger.info("Spreadsheet merge: %s", spreadsheet_stats)
        else:
            logger.warning("No NHL spreadsheet in %s — skipping", RAW_DIR)

        # ArcGIS (coordinates overlay)
        logger.info("--- ArcGIS NHLs ---")
        features = fetch_nhls(use_cache=not args.no_cache)
        arcgis_sites = parse_features(features)

        report = run_validation(arcgis_sites)
        save_validation_report(report)
        logger.info("Validation: %d passed, %d warnings, %d failed",
                     report["passed"], report["warnings"], report["failed"])

        arcgis_stats = merge_arcgis_records(conn, arcgis_sites)
        logger.info("ArcGIS merge: %s", arcgis_stats)

        # NPS Parks
        logger.info("--- NPS Parks ---")
        parks = fetch_parks(use_cache=not args.no_cache)
        if parks:
            nps_sites = parse_parks(parks)
            nps_stats = merge_nps_parks_records(conn, nps_sites)
            logger.info("NPS Parks merge: %s", nps_stats)

        # SHPO State Sources
        if not args.skip_shpo:
            logger.info("--- SHPO State Sources ---")
            from config.state_sources import STATE_SOURCES
            from src.ingest.merger import merge_shpo_records
            from src.ingest.shpo_dispatcher import (
                fetch_state,
                get_active_states,
                parse_state,
            )

            shpo_state_list = (
                args.shpo_states.split(",") if args.shpo_states else None
            )
            active_states = get_active_states(filter_states=shpo_state_list)
            for state_code in active_states:
                try:
                    logger.info("--- SHPO %s ---", state_code)
                    raw = fetch_state(state_code, use_cache=not args.no_cache)
                    sites = parse_state(state_code, raw)
                    shpo_config = STATE_SOURCES[state_code]
                    shpo_stats = merge_shpo_records(conn, sites, state_code, shpo_config)
                    logger.info("SHPO %s merge: %s", state_code, shpo_stats)
                except Exception:
                    logger.exception(
                        "SHPO %s failed — continuing with next state", state_code
                    )
        else:
            logger.info("--- SHPO State Sources (SKIPPED) ---")

        total = conn.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
        with_coords = conn.execute(
            "SELECT COUNT(*) FROM sites WHERE latitude IS NOT NULL"
        ).fetchone()[0]
        logger.info("After ingest: %d sites (%d with coordinates)", total, with_coords)

        # --- Stage 5: Geocode ---
        logger.info("\n=== STAGE 5: GEOCODE ===")
        from src.ingest.geocoder import run_geocoding

        geo_stats = run_geocoding(conn)
        logger.info("Geocoding: %s", geo_stats)

        with_coords = conn.execute(
            "SELECT COUNT(*) FROM sites WHERE latitude IS NOT NULL"
        ).fetchone()[0]
        logger.info("After geocoding: %d sites with coordinates", with_coords)

        # --- Stage 6: Profile ---
        logger.info("\n=== STAGE 6: PROFILE ===")
        from src.profiling.data_profiler import generate_profile, save_html_report, save_json_report

        profile = generate_profile(conn)
        save_json_report(profile)
        save_html_report(profile)
        logger.info("Profile: %d total sites, %d with coords",
                     profile["summary"]["total_sites"],
                     profile["coordinate_coverage"]["with_coordinates"])

        # --- Stage 7: Enrich ---
        if not args.skip_enrich:
            logger.info("\n=== STAGE 7: ENRICH ===")
            from src.enrich.batch_processor import run_enrichment

            enrich_stats = run_enrichment(conn, limit=args.enrich_limit)
            logger.info("Enrichment: %s", enrich_stats)
        else:
            logger.info("\n=== STAGE 7: ENRICH (SKIPPED) ===")

        # --- Stage 8: Score ---
        logger.info("\n=== STAGE 8: SCORE ===")
        from src.scoring.confidence import run_scoring

        score_stats = run_scoring(conn)
        logger.info("Scoring: %s", score_stats)

        # --- Stage 9: Export ---
        logger.info("\n=== STAGE 9: EXPORT ===")
        from src.export.csv_exporter import export_full_csv, export_review_csv
        from src.export.folium_map import generate_map
        from src.export.geojson_exporter import export_geojson
        from src.export.kml_exporter import export_kml

        kml_result = export_kml(conn)
        logger.info("KML: %d state files, master KMZ created", len(kml_result["state_files"]))

        geojson_result = export_geojson(conn)
        logger.info("GeoJSON: %d state files + all + nhls", len(geojson_result["state_files"]))

        map_path = generate_map(conn)
        logger.info("Map: %s", map_path)

        export_review_csv(conn)
        export_full_csv(conn)

        # --- Summary ---
        elapsed = time.time() - start_time
        total = conn.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
        with_coords = conn.execute(
            "SELECT COUNT(*) FROM sites WHERE latitude IS NOT NULL"
        ).fetchone()[0]

        logger.info("\n" + "=" * 60)
        logger.info("PIPELINE COMPLETE in %.1f seconds", elapsed)
        logger.info("  Total sites: %d", total)
        logger.info("  With coordinates: %d", with_coords)
        logger.info("  Review: %s", score_stats)
        logger.info("=" * 60)


if __name__ == "__main__":
    main()
