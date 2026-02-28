"""
NPS Parks API client.

Fetches park information from the NPS Developer API (https://developer.nps.gov/api/v1).
Provides rich descriptions and operating hours for NPS-managed sites.

API quirks:
  - latLong is a string "lat:38.9, long:-77.0" requiring parsing
  - Rate limit: 1,000 requests per hour
  - Pagination via start parameter
"""

import json
import logging
import re
import time
from pathlib import Path

import requests

from config.settings import (
    NPS_API_BASE_URL,
    NPS_API_KEY,
    NPS_API_PAGE_SIZE,
    RAW_DIR,
)

logger = logging.getLogger(__name__)

CACHE_FILE = RAW_DIR / "nps_parks.json"


def _parse_latlong(latlong_str: str) -> tuple[float | None, float | None]:
    """Parse NPS API latLong string like 'lat:38.89, long:-77.03'.

    Returns:
        Tuple of (latitude, longitude) or (None, None) if parsing fails.
    """
    if not latlong_str or not latlong_str.strip():
        return None, None

    lat_match = re.search(r"lat:\s*(-?[\d.]+)", latlong_str)
    lon_match = re.search(r"long:\s*(-?[\d.]+)", latlong_str)

    lat = float(lat_match.group(1)) if lat_match else None
    lon = float(lon_match.group(1)) if lon_match else None

    return lat, lon


def fetch_parks(use_cache: bool = True) -> list[dict]:
    """Fetch all parks from the NPS Parks API with pagination.

    Args:
        use_cache: If True and cache file exists, return cached data.

    Returns:
        List of raw NPS park data dicts.
    """
    if not NPS_API_KEY:
        logger.warning("NPS_API_KEY not set. Skipping NPS Parks API fetch.")
        return []

    if use_cache and CACHE_FILE.exists():
        logger.info("Loading NPS parks from cache: %s", CACHE_FILE)
        with open(CACHE_FILE) as f:
            return json.load(f)

    logger.info("Fetching parks from NPS API...")
    all_parks = []
    start = 0

    while True:
        params = {
            "api_key": NPS_API_KEY,
            "limit": NPS_API_PAGE_SIZE,
            "start": start,
        }

        response = requests.get(
            f"{NPS_API_BASE_URL}/parks", params=params, timeout=30
        )
        response.raise_for_status()
        data = response.json()

        parks = data.get("data", [])
        if not parks:
            break

        all_parks.extend(parks)
        total = int(data.get("total", 0))
        start += len(parks)
        logger.info("  Fetched %d parks (total: %d / %d)", len(parks), len(all_parks), total)

        if start >= total:
            break

        time.sleep(1.0)  # Respect rate limits

    # Cache raw response
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(all_parks, f)
    logger.info("Cached %d NPS parks to %s", len(all_parks), CACHE_FILE)

    return all_parks


def parse_parks(parks: list[dict]) -> list[dict]:
    """Transform raw NPS park data into site records.

    Args:
        parks: Raw NPS API park data dicts.

    Returns:
        List of dicts ready for upsert_site().
    """
    sites = []
    for park in parks:
        lat, lon = _parse_latlong(park.get("latLong", ""))

        # Build description from available fields
        description = park.get("description", "")

        # Extract operating hours
        hours_list = park.get("operatingHours", [])
        visiting_hours = None
        if hours_list:
            std_hours = hours_list[0].get("standardHours", {})
            if std_hours:
                parts = []
                for day in ["monday", "tuesday", "wednesday", "thursday",
                            "friday", "saturday", "sunday"]:
                    val = std_hours.get(day, "")
                    if val and val.lower() != "closed":
                        parts.append(f"{day.title()}: {val}")
                if parts:
                    visiting_hours = "; ".join(parts)

        # Extract entrance fees
        fees = park.get("entranceFees", [])
        admission_info = None
        if fees:
            fee_parts = []
            for fee in fees:
                cost = fee.get("cost", "0.00")
                title = fee.get("title", "")
                if cost == "0.00" or cost == "0":
                    fee_parts.append(f"{title}: Free")
                else:
                    fee_parts.append(f"{title}: ${cost}")
            if fee_parts:
                admission_info = "; ".join(fee_parts)

        site = {
            "nps_park_code": park.get("parkCode", "").strip() or None,
            "name": (park.get("fullName") or park.get("name", "")).strip(),
            "state": (park.get("states") or "").strip() or None,
            "latitude": lat,
            "longitude": lon,
            "coordinates_source": "nps_parks" if lat else None,
            "short_description": description[:500] if description else None,
            "full_description": description if len(description) > 500 else None,
            "website_url": park.get("url"),
            "visiting_hours": visiting_hours,
            "admission_info": admission_info,
            "source_nps_parks": True,
        }

        if site["name"]:
            sites.append(site)

    logger.info("Parsed %d site records from %d NPS parks", len(sites), len(parks))
    return sites
