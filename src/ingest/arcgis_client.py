"""
Paginated ArcGIS REST API client for NRHP National Historic Landmarks.

Fetches NHL point locations from the NPS MapServices cultural resources layer.
ArcGIS quirks:
  - Is_NHL uses value 'X' (not 'Yes' or 'True')
  - Geometry returned as {"x": longitude, "y": latitude}
  - Max 1,000 records per page; use resultOffset + exceededTransferLimit
  - CertDate is epoch milliseconds
"""

import json
import logging
import time

import requests

from config.settings import (
    ARCGIS_BASE_URL,
    ARCGIS_NHL_FILTER,
    ARCGIS_PAGE_SIZE,
    RAW_DIR,
)

logger = logging.getLogger(__name__)

CACHE_FILE = RAW_DIR / "arcgis_nhls.json"


def _epoch_ms_to_iso(value: int | str | None) -> str | None:
    """Convert ArcGIS date value to ISO 8601 date string.

    Handles epoch milliseconds (int) and date strings like '12/19/78'.
    """
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return time.strftime("%Y-%m-%d", time.gmtime(value / 1000))
        # Parse date strings like "12/19/78" or "01/03/2000"
        parts = str(value).strip().split("/")
        if len(parts) == 3:
            month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
            if year < 100:
                year += 1900 if year > 25 else 2000
            return f"{year:04d}-{month:02d}-{day:02d}"
        return None
    except (ValueError, OSError, TypeError):
        return None


def fetch_nhls(use_cache: bool = True) -> list[dict]:
    """Fetch all NHL records from ArcGIS REST API with pagination.

    Args:
        use_cache: If True and cache file exists, return cached data.

    Returns:
        List of raw ArcGIS feature attributes with geometry.
    """
    if use_cache and CACHE_FILE.exists():
        logger.info("Loading ArcGIS NHLs from cache: %s", CACHE_FILE)
        with open(CACHE_FILE) as f:
            return json.load(f)

    logger.info("Fetching NHLs from ArcGIS REST API...")
    all_features = []
    offset = 0

    while True:
        params = {
            "where": ARCGIS_NHL_FILTER,
            "outFields": "*",
            "outSR": "4326",
            "f": "json",
            "resultOffset": offset,
            "resultRecordCount": ARCGIS_PAGE_SIZE,
            "returnGeometry": "true",
        }

        response = requests.get(ARCGIS_BASE_URL, params=params, timeout=60)
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            raise RuntimeError(f"ArcGIS API error: {data['error']}")

        features = data.get("features", [])
        if not features:
            break

        all_features.extend(features)
        offset += len(features)
        logger.info("  Fetched %d records (total: %d)", len(features), len(all_features))

        # ArcGIS signals more pages with exceededTransferLimit
        if not data.get("exceededTransferLimit", False):
            break

        time.sleep(0.5)  # Be polite to the API

    # Cache raw response
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(all_features, f)
    logger.info("Cached %d ArcGIS NHL records to %s", len(all_features), CACHE_FILE)

    return all_features


def _get_attr(attrs: dict, *keys: str) -> str | None:
    """Get the first non-empty value from a list of attribute key aliases.

    ArcGIS field names vary across API versions (e.g. ResName vs RESNAME,
    RefNum vs NRIS_Refnum). This helper tries each alias in order.
    """
    for key in keys:
        val = attrs.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return None


def parse_features(features: list[dict]) -> list[dict]:
    """Transform raw ArcGIS features into site records matching our schema.

    Args:
        features: Raw ArcGIS feature dicts with 'attributes' and 'geometry'.

    Returns:
        List of dicts ready for upsert_site().
    """
    sites = []
    for feature in features:
        attrs = feature.get("attributes", {})
        geom = feature.get("geometry", {})

        # ArcGIS geometry: {"x": longitude, "y": latitude}
        longitude = geom.get("x")
        latitude = geom.get("y")

        # Skip features with null geometry
        if longitude is None or latitude is None:
            logger.warning("Skipping feature with no geometry: %s",
                           _get_attr(attrs, "ResName", "RESNAME"))
            continue

        site = {
            "nris_refnum": _get_attr(attrs, "RefNum", "NRIS_Refnum", "PROPERTY_ID"),
            "name": _get_attr(attrs, "ResName", "RESNAME") or "",
            "address": _get_attr(attrs, "Address"),
            "city": _get_attr(attrs, "City"),
            "county": _get_attr(attrs, "County"),
            "state": _get_attr(attrs, "State"),
            "latitude": latitude,
            "longitude": longitude,
            "coordinates_source": "arcgis",
            "nrhp_cert_date": _epoch_ms_to_iso(
                attrs.get("CertDate") or attrs.get("CERTDATE")
            ),
            "nrhp_status": _get_attr(attrs, "Status", "STATUS"),
            "source_arcgis": True,
            "primary_source": "arcgis",
        }

        # Only include records with a name
        if site["name"]:
            sites.append(site)
        else:
            logger.warning("Skipping feature with no name: refnum=%s", site["nris_refnum"])

    logger.info("Parsed %d site records from %d ArcGIS features", len(sites), len(features))
    return sites
