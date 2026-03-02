"""
Batch geocoding pipeline.

Primary: Census Bureau Batch Geocoder (free, up to 10K addresses/batch)
Fallback: Nominatim (OpenStreetMap) via geopy (1 req/sec)

Maps geocoder results to quality levels:
  - exact: Census Exact match
  - interpolated: Census Non_Exact match
  - landmark: Nominatim matched by site name (likely precise)
  - city_level: Nominatim city-level result
  - zip_level: Nominatim ZIP-level result
"""

import csv
import io
import logging
import sqlite3
import time

import requests
from geopy.exc import GeocoderServiceError, GeocoderTimedOut
from geopy.geocoders import Nominatim

from config.settings import (
    CENSUS_BATCH_SIZE,
    CENSUS_GEOCODER_URL,
    NOMINATIM_RATE_LIMIT,
    NOMINATIM_USER_AGENT,
)
from src.db.queries import (
    complete_pipeline_run,
    get_sites_for_geocoding,
    start_pipeline_run,
    update_site,
)
from src.ingest.validator import validate_coordinates

logger = logging.getLogger(__name__)


def _format_elapsed(seconds: float) -> str:
    """Format seconds into human-readable elapsed time."""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


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

    # Census geocoder requires a street address — skip address-less sites
    addressable = [s for s in sites if s.get("address")]
    if not addressable:
        return {}

    results = {}

    # Process in chunks of CENSUS_BATCH_SIZE
    for i in range(0, len(addressable), CENSUS_BATCH_SIZE):
        chunk = addressable[i:i + CENSUS_BATCH_SIZE]
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
    name: str | None = None,
) -> dict | None:
    """Geocode a single site using Nominatim.

    When address is missing but name is available, tries a landmark lookup
    first ("name, city, state") before falling back to city-level.

    Args:
        address: Street address.
        city: City name.
        state: State abbreviation.
        name: Site/landmark name (used when address is missing).

    Returns:
        Dict with 'lat', 'lon', 'quality', 'source' or None.
    """
    geolocator = Nominatim(user_agent=NOMINATIM_USER_AGENT, timeout=10)

    # Strategy A: If we have an address, use it directly
    if address:
        parts = [p for p in [address, city, state, "United States"] if p]
        query = ", ".join(parts)
        try:
            location = geolocator.geocode(query, exactly_one=True, country_codes="us")
            if location:
                return {
                    "lat": location.latitude,
                    "lon": location.longitude,
                    "quality": "interpolated",
                    "source": "nominatim",
                }
        except (GeocoderTimedOut, GeocoderServiceError) as e:
            logger.warning("Nominatim geocoding failed for '%s': %s", query, e)
        return None

    # Strategy B: No address — try landmark name lookup first
    if name and (city or state):
        landmark_query = ", ".join(
            p for p in [name, city, state, "United States"] if p
        )
        try:
            location = geolocator.geocode(
                landmark_query, exactly_one=True, country_codes="us"
            )
            if location:
                return {
                    "lat": location.latitude,
                    "lon": location.longitude,
                    "quality": "landmark",
                    "source": "nominatim",
                }
        except (GeocoderTimedOut, GeocoderServiceError) as e:
            logger.warning(
                "Nominatim landmark lookup failed for '%s': %s", landmark_query, e
            )

        # Rate limit between attempts
        time.sleep(NOMINATIM_RATE_LIMIT)

    # Strategy C: Fall back to city-level
    city_parts = [p for p in [city, state, "United States"] if p]
    if city_parts:
        city_query = ", ".join(city_parts)
        try:
            location = geolocator.geocode(
                city_query, exactly_one=True, country_codes="us"
            )
            if location:
                return {
                    "lat": location.latitude,
                    "lon": location.longitude,
                    "quality": "city_level",
                    "source": "nominatim",
                }
        except (GeocoderTimedOut, GeocoderServiceError) as e:
            logger.warning(
                "Nominatim city-level failed for '%s': %s", city_query, e
            )

    return None


def run_geocoding(conn: sqlite3.Connection, force: bool = False) -> dict:
    """Run geocoding pipeline on all sites missing coordinates.

    Args:
        conn: Database connection.
        force: If True, re-geocode sites that already have coordinates.

    Returns:
        Dict with counts by quality level.
    """
    run_id = start_pipeline_run(conn, "geocoding")
    stats = {
        "census_matched": 0,
        "nominatim_matched": 0,
        "landmark_matched": 0,
        "city_level": 0,
        "failed": 0,
        "skipped": 0,
    }

    # Get sites needing geocoding
    sites = get_sites_for_geocoding(conn)
    if not sites:
        logger.info("No sites need geocoding")
        complete_pipeline_run(conn, run_id, 0)
        return stats

    logger.info("Geocoding %d sites", len(sites))

    # Separate sites with addresses (Census-eligible) from those without
    sites_with_address = [s for s in sites if s.get("address")]
    sites_without_address = [s for s in sites if not s.get("address")]
    logger.info(
        "  %d with street address (Census+Nominatim), %d without (Nominatim landmark)",
        len(sites_with_address),
        len(sites_without_address),
    )

    # Strategy 1: Census Bureau batch (only for sites with addresses)
    census_results = geocode_census_batch(sites_with_address)
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

    # Strategy 2: Nominatim fallback for Census failures + all address-less sites
    census_matched_ids = set(census_results.keys())
    nominatim_sites = [
        s for s in sites_with_address if s["id"] not in census_matched_ids
    ] + sites_without_address

    total_nom = len(nominatim_sites)
    logger.info("Nominatim geocoding for %d sites", total_nom)
    start_time = time.monotonic()

    for idx, site in enumerate(nominatim_sites, 1):
        result = geocode_nominatim_single(
            site.get("address"),
            site.get("city"),
            site.get("state"),
            name=site.get("name"),
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
                if result["quality"] == "landmark":
                    stats["landmark_matched"] += 1
                elif result["quality"] == "city_level":
                    stats["city_level"] += 1
                else:
                    stats["nominatim_matched"] += 1
            else:
                stats["failed"] += 1
        else:
            stats["failed"] += 1

        # Batch commit every 50 sites for crash safety
        if idx % 50 == 0:
            conn.commit()

            elapsed = time.monotonic() - start_time
            avg_per_site = elapsed / idx
            remaining = (total_nom - idx) * avg_per_site
            logger.info(
                "Nominatim progress: %d/%d | landmark=%d, city=%d, address=%d, failed=%d | "
                "Elapsed: %s | ETA: %s",
                idx,
                total_nom,
                stats["landmark_matched"],
                stats["city_level"],
                stats["nominatim_matched"],
                stats["failed"],
                _format_elapsed(elapsed),
                _format_elapsed(remaining),
            )

        time.sleep(NOMINATIM_RATE_LIMIT)

    conn.commit()
    total_processed = sum(stats.values())
    complete_pipeline_run(conn, run_id, total_processed)
    logger.info("Geocoding complete: %s", stats)
    return stats
