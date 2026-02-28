"""
Batch geocoding pipeline.

Primary: Census Bureau Batch Geocoder (free, up to 10K addresses/batch)
Fallback: Nominatim (OpenStreetMap) via geopy (1 req/sec)

Maps geocoder results to quality levels:
  - exact: Census Exact match
  - interpolated: Census Non_Exact match
  - city_level: Nominatim city-level result
  - zip_level: Nominatim ZIP-level result
"""

import csv
import io
import logging
import sqlite3
import time

import requests
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

from config.settings import (
    CENSUS_BATCH_SIZE,
    CENSUS_GEOCODER_URL,
    NOMINATIM_RATE_LIMIT,
    NOMINATIM_USER_AGENT,
)
from src.db.queries import (
    get_sites_for_geocoding,
    update_site,
    start_pipeline_run,
    complete_pipeline_run,
)
from src.ingest.validator import validate_coordinates

logger = logging.getLogger(__name__)


def _build_census_batch(sites: list[dict]) -> str:
    """Build CSV content for Census Bureau batch geocoder.

    Format: Unique ID, Street address, City, State, ZIP
    """
    output = io.StringIO()
    writer = csv.writer(output)
    for site in sites:
        writer.writerow([
            site["id"],
            site.get("address", "") or "",
            site.get("city", "") or "",
            site.get("state", "") or "",
            "",  # ZIP code (often not available)
        ])
    return output.getvalue()


def geocode_census_batch(sites: list[dict]) -> dict[int, dict]:
    """Geocode a batch of sites using the Census Bureau API.

    Args:
        sites: List of site dicts with 'id', 'address', 'city', 'state'.

    Returns:
        Dict mapping site_id to {'lat', 'lon', 'quality', 'source'}.
    """
    if not sites:
        return {}

    results = {}

    # Process in chunks of CENSUS_BATCH_SIZE
    for i in range(0, len(sites), CENSUS_BATCH_SIZE):
        chunk = sites[i:i + CENSUS_BATCH_SIZE]
        csv_data = _build_census_batch(chunk)

        try:
            response = requests.post(
                CENSUS_GEOCODER_URL,
                files={"addressFile": ("addresses.csv", csv_data)},
                data={
                    "benchmark": "Public_AR_Current",
                    "vintage": "Current_Current",
                },
                timeout=120,
            )
            response.raise_for_status()

            # Parse response CSV
            reader = csv.reader(io.StringIO(response.text))
            for row in reader:
                if len(row) < 6:
                    continue

                site_id = int(row[0])
                match_type = row[2].strip('"')  # Match, No_Match, Tie, Non_Exact

                if match_type in ("Match", "Non_Exact"):
                    # Coordinates are in row[5] as "lon,lat"
                    coords = row[5].strip('"').split(",")
                    if len(coords) == 2:
                        lon = float(coords[0])
                        lat = float(coords[1])

                        quality = "exact" if match_type == "Match" else "interpolated"
                        results[site_id] = {
                            "lat": lat,
                            "lon": lon,
                            "quality": quality,
                            "source": "census_geocoder",
                        }

            logger.info(
                "Census batch %d-%d: %d/%d matched",
                i, i + len(chunk), len(results), len(chunk),
            )

        except requests.RequestException as e:
            logger.warning("Census geocoder batch failed: %s", e)

    return results


def geocode_nominatim_single(
    address: str | None,
    city: str | None,
    state: str | None,
) -> dict | None:
    """Geocode a single address using Nominatim.

    Args:
        address: Street address.
        city: City name.
        state: State abbreviation.

    Returns:
        Dict with 'lat', 'lon', 'quality', 'source' or None.
    """
    parts = [p for p in [address, city, state, "United States"] if p]
    query = ", ".join(parts)

    try:
        geolocator = Nominatim(user_agent=NOMINATIM_USER_AGENT, timeout=10)
        location = geolocator.geocode(query, exactly_one=True, country_codes="us")

        if location:
            # Determine quality based on the detail level
            quality = "city_level"
            if address:
                quality = "interpolated"

            return {
                "lat": location.latitude,
                "lon": location.longitude,
                "quality": quality,
                "source": "nominatim",
            }

    except (GeocoderTimedOut, GeocoderServiceError) as e:
        logger.warning("Nominatim geocoding failed for '%s': %s", query, e)

    return None


def run_geocoding(conn: sqlite3.Connection, force: bool = False) -> dict:
    """Run geocoding pipeline on all sites missing coordinates.

    Args:
        conn: Database connection.
        force: If True, re-geocode sites that already have coordinates.

    Returns:
        Dict with 'census_matched', 'nominatim_matched', 'failed' counts.
    """
    run_id = start_pipeline_run(conn, "geocoding")
    stats = {"census_matched": 0, "nominatim_matched": 0, "failed": 0, "skipped": 0}

    # Get sites needing geocoding
    sites = get_sites_for_geocoding(conn)
    if not sites:
        logger.info("No sites need geocoding")
        complete_pipeline_run(conn, run_id, 0)
        return stats

    logger.info("Geocoding %d sites", len(sites))

    # Strategy 1: Census Bureau batch
    census_results = geocode_census_batch(sites)
    for site_id, result in census_results.items():
        coord_check = validate_coordinates(result["lat"], result["lon"])
        if coord_check["valid"]:
            update_site(conn, site_id, {
                "latitude": result["lat"],
                "longitude": result["lon"],
                "coordinates_source": result["source"],
                "geocode_quality": result["quality"],
            })
            stats["census_matched"] += 1

    conn.commit()

    # Strategy 2: Nominatim fallback for Census failures
    failed_sites = [s for s in sites if s["id"] not in census_results]
    logger.info("Nominatim fallback for %d sites", len(failed_sites))

    for site in failed_sites:
        result = geocode_nominatim_single(
            site.get("address"), site.get("city"), site.get("state")
        )

        if result:
            coord_check = validate_coordinates(result["lat"], result["lon"])
            if coord_check["valid"]:
                update_site(conn, site["id"], {
                    "latitude": result["lat"],
                    "longitude": result["lon"],
                    "coordinates_source": result["source"],
                    "geocode_quality": result["quality"],
                })
                stats["nominatim_matched"] += 1
            else:
                stats["failed"] += 1
        else:
            stats["failed"] += 1

        time.sleep(NOMINATIM_RATE_LIMIT)

    conn.commit()
    complete_pipeline_run(conn, run_id, sum(stats.values()))
    logger.info("Geocoding complete: %s", stats)
    return stats
