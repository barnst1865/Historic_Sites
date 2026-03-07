"""
Ingest ABPP (American Battlefield Protection Program) battlefield sites.

Reads the GeoJSON boundary files downloaded from the NPS ABPP ArcGIS service,
computes polygon centroids for coordinates, and merges into the database using
fuzzy name matching against existing sites.

Source: NPS American Battlefield Protection Program
  - Civil War (342 battlefields)
  - Revolutionary War (159 battlefields)
  - War of 1812 (80 battlefields)

Usage:
    python scripts/ingest_abpp.py
    python scripts/ingest_abpp.py --war civil_war
    python scripts/ingest_abpp.py --war rev_war
    python scripts/ingest_abpp.py --war war_of_1812
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.connection import db_connection
from src.db.queries import (
    add_designation,
    add_site_source,
    complete_pipeline_run,
    start_pipeline_run,
    update_source_metadata,
    upsert_site,
)
from src.ingest.validator import SpatialIndex, find_fuzzy_matches, validate_site

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

ABPP_DIR = Path(__file__).parent.parent / "manual-data" / "ABPP"

WARS = {
    "civil_war": {
        "file": "ABPP_Civil_War_Boundaries.geojson",
        "war_label": "Civil War",
        "designation_type": "ABPP Civil War Battlefield",
    },
    "rev_war": {
        "file": "ABPP_RevWar_Boundaries.geojson",
        "war_label": "Revolutionary War",
        "designation_type": "ABPP Revolutionary War Battlefield",
    },
    "war_of_1812": {
        "file": "ABPP_WarOf1812_Boundaries.geojson",
        "war_label": "War of 1812",
        "designation_type": "ABPP War of 1812 Battlefield",
    },
}

SOURCE_NAME = "abpp"
DESIGNATING_AUTHORITY = "American Battlefield Protection Program"


def _polygon_centroid(geometry: dict) -> tuple[float, float] | None:
    """Compute centroid of a GeoJSON Polygon or MultiPolygon as (lat, lon)."""
    geo_type = geometry.get("type", "")
    coords = geometry.get("coordinates", [])

    if not coords:
        return None

    all_points = []
    if geo_type == "Polygon":
        # First ring is exterior
        all_points = coords[0]
    elif geo_type == "MultiPolygon":
        for polygon in coords:
            all_points.extend(polygon[0])
    else:
        return None

    if not all_points:
        return None

    avg_lon = sum(p[0] for p in all_points) / len(all_points)
    avg_lat = sum(p[1] for p in all_points) / len(all_points)
    return avg_lat, avg_lon


def _parse_state(state_str: str) -> str:
    """Parse state code from ABPP data (handles multi-state like 'VA/WV')."""
    # Return just the first state for multi-state battlefields
    return state_str.strip().split("/")[0].upper()


def parse_abpp_geojson(filepath: Path, war_config: dict) -> list[dict]:
    """Parse an ABPP GeoJSON file into site dicts."""
    with open(filepath) as f:
        data = json.load(f)

    sites = []
    for feature in data["features"]:
        props = feature["properties"]
        geometry = feature.get("geometry")

        name = props.get("NAME", "").strip()
        if not name:
            continue

        # Title-case the name (ABPP data is often ALL CAPS)
        name = name.title()

        state = _parse_state(props.get("STATE", ""))
        site_id_code = props.get("SITE", "")

        centroid = _polygon_centroid(geometry) if geometry else None

        site = {
            "name": name,
            "state": state,
            "source_other": True,
            "primary_source": SOURCE_NAME,
        }

        if centroid:
            site["latitude"] = round(centroid[0], 6)
            site["longitude"] = round(centroid[1], 6)

        site["_abpp_site_id"] = site_id_code
        site["_war"] = war_config["war_label"]
        site["_designation_type"] = war_config["designation_type"]

        sites.append(site)

    logger.info(
        "[ABPP] Parsed %d %s battlefield sites from %s",
        len(sites), war_config["war_label"], filepath.name,
    )
    return sites


def merge_abpp_records(conn, sites: list[dict]) -> dict:
    """Merge ABPP battlefield records into the database.

    Uses proximity + fuzzy name matching against existing sites.
    Battlefields that match existing records get the ABPP designation added.
    Unmatched battlefields are inserted as new sites.
    """
    run_id = start_pipeline_run(conn, f"merge_{SOURCE_NAME}")
    stats = {"inserted": 0, "updated": 0, "matched": 0}

    # Load all existing sites for matching (battlefields span many states)
    existing = [
        dict(row)
        for row in conn.execute(
            "SELECT id, name, latitude, longitude, address, city FROM sites"
        ).fetchall()
    ]

    spatial_idx = SpatialIndex()
    for site in existing:
        spatial_idx.add(site)

    for site_data in sites:
        # Extract internal fields before validation
        abpp_site_id = site_data.pop("_abpp_site_id", "")
        war = site_data.pop("_war", "")
        designation_type = site_data.pop("_designation_type", "")

        result = validate_site(site_data)
        site_data = result["site_data"]

        site_id = None
        name = site_data.get("name", "")

        # Try fuzzy match with proximity
        matches = find_fuzzy_matches(
            name,
            site_data.get("latitude"),
            site_data.get("longitude"),
            existing,
            spatial_index=spatial_idx,
        )

        # Accept proximity matches with good name similarity
        proximity = [m for m in matches if m["match_type"] == "proximity_match"]
        if proximity and proximity[0]["score"] >= 70:
            site_id = proximity[0]["site_id"]
            stats["matched"] += 1
            logger.debug(
                "[ABPP] Matched '%s' → '%s' (score=%d, dist=%.2fkm)",
                name, proximity[0]["name"], proximity[0]["score"],
                proximity[0].get("distance_km", 0),
            )
        else:
            # Also check high-confidence name-only matches
            name_only = [
                m for m in matches
                if m["match_type"] == "name_only_match" and m["score"] >= 92
            ]
            if name_only:
                site_id = name_only[0]["site_id"]
                stats["matched"] += 1
                logger.debug(
                    "[ABPP] Name-matched '%s' → '%s' (score=%d)",
                    name, name_only[0]["name"], name_only[0]["score"],
                )

        if site_id is not None:
            # Update existing site — fill coords if missing, set source flag
            conn.execute(
                "UPDATE sites SET "
                "source_other = 1, "
                "latitude = COALESCE(latitude, ?), "
                "longitude = COALESCE(longitude, ?) "
                "WHERE id = ? AND primary_source != 'manual'",
                (site_data.get("latitude"), site_data.get("longitude"), site_id),
            )
            stats["updated"] += 1
        else:
            # Insert new battlefield site
            site_id = upsert_site(conn, site_data)
            stats["inserted"] += 1

            new_entry = {
                "id": site_id,
                "name": name,
                "latitude": site_data.get("latitude"),
                "longitude": site_data.get("longitude"),
            }
            existing.append(new_entry)
            spatial_idx.add(new_entry)

        # Always add ABPP designation
        add_designation(conn, site_id, {
            "designation_type": designation_type,
            "designating_authority": DESIGNATING_AUTHORITY,
            "source": SOURCE_NAME,
        })

        # Track provenance
        add_site_source(conn, site_id, {
            "source_name": SOURCE_NAME,
            "source_record_id": abpp_site_id,
            "raw_data": {
                "name": name,
                "war": war,
                "site_id": abpp_site_id,
                "state": site_data.get("state"),
            },
        })

    conn.commit()
    total = stats["inserted"] + stats["updated"]
    update_source_metadata(conn, SOURCE_NAME, total)
    complete_pipeline_run(conn, run_id, total + stats["matched"])
    logger.info("[ABPP] Merge complete: %s", stats)
    return stats


def main():
    parser = argparse.ArgumentParser(description="Ingest ABPP battlefield sites")
    parser.add_argument(
        "--war",
        choices=list(WARS.keys()) + ["all"],
        default="all",
        help="Which war's battlefields to ingest (default: all)",
    )
    args = parser.parse_args()

    wars_to_ingest = list(WARS.keys()) if args.war == "all" else [args.war]

    all_sites = []
    for war_key in wars_to_ingest:
        war_config = WARS[war_key]
        filepath = ABPP_DIR / war_config["file"]
        if not filepath.exists():
            logger.error("[ABPP] File not found: %s", filepath)
            continue
        sites = parse_abpp_geojson(filepath, war_config)
        all_sites.extend(sites)

    if not all_sites:
        logger.error("[ABPP] No sites to ingest")
        sys.exit(1)

    logger.info("[ABPP] === Ingesting %d battlefield sites ===", len(all_sites))

    with db_connection() as conn:
        stats = merge_abpp_records(conn, all_sites)

        total = conn.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
        with_coords = conn.execute(
            "SELECT COUNT(*) FROM sites WHERE latitude IS NOT NULL"
        ).fetchone()[0]
        logger.info("Database total: %d sites (%d with coordinates)", total, with_coords)


if __name__ == "__main__":
    main()
