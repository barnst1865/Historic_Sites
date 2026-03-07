"""
Data validation layer for incoming site records.

Validates coordinates, normalizes dates and state codes, and performs
entity resolution for cross-source matching. Run before data enters
the database to catch issues early.
"""

import json
import logging
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from config.settings import (
    FUZZY_MATCH_CANDIDATE,
    FUZZY_MATCH_THRESHOLD,
    GEO_PROXIMITY_KM,
    OUTPUT_DIR,
    US_LAT_MAX,
    US_LAT_MIN,
    US_LON_MAX,
    US_LON_MIN,
)

logger = logging.getLogger(__name__)

# State abbreviation mapping
STATE_ABBREVS = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
    "puerto rico": "PR", "guam": "GU", "american samoa": "AS",
    "u.s. virgin islands": "VI", "northern mariana islands": "MP",
}

VALID_STATE_CODES = set(STATE_ABBREVS.values())


def normalize_state(state: str | None) -> str | None:
    """Normalize state name or abbreviation to 2-letter code."""
    if not state:
        return None
    state = state.strip()
    if len(state) == 2 and state.upper() in VALID_STATE_CODES:
        return state.upper()
    lookup = state.lower()
    if lookup in STATE_ABBREVS:
        return STATE_ABBREVS[lookup]
    return state.upper()[:2] if len(state) >= 2 else state.upper()


def normalize_date(date_str: str | None) -> str | None:
    """Normalize various date formats to ISO 8601 (YYYY-MM-DD or YYYY).

    Handles: MM/DD/YYYY, YYYY-MM-DD, epoch milliseconds, plain years.
    """
    if not date_str:
        return None

    date_str = str(date_str).strip()

    # Already ISO format
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return date_str

    # Plain year
    if re.match(r"^\d{4}$", date_str):
        return date_str

    # MM/DD/YYYY
    match = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", date_str)
    if match:
        m, d, y = match.groups()
        return f"{y}-{int(m):02d}-{int(d):02d}"

    # Epoch milliseconds (ArcGIS CertDate)
    try:
        epoch = int(float(date_str))
        if epoch > 1e12:  # Likely milliseconds
            dt = datetime.utcfromtimestamp(epoch / 1000)
            return dt.strftime("%Y-%m-%d")
        elif epoch > 1e9:  # Likely seconds
            dt = datetime.utcfromtimestamp(epoch)
            return dt.strftime("%Y-%m-%d")
    except (ValueError, OSError):
        pass

    # Try common text formats
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%m-%d-%Y", "%d-%b-%Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    logger.warning("Could not parse date: %s", date_str)
    return date_str


def validate_coordinates(
    lat: float | None, lon: float | None
) -> dict:
    """Validate lat/lon coordinates.

    Returns:
        Dict with 'valid' bool, 'lat', 'lon' (possibly corrected),
        and 'warnings' list.
    """
    result = {"valid": True, "lat": lat, "lon": lon, "warnings": []}

    if lat is None or lon is None:
        result["valid"] = False
        result["warnings"].append("missing_coordinates")
        return result

    # Check for swapped lat/lon
    if US_LON_MIN <= lat <= US_LON_MAX and US_LAT_MIN <= lon <= US_LAT_MAX:
        result["warnings"].append("swapped_lat_lon")
        result["lat"], result["lon"] = lon, lat
        lat, lon = lon, lat
        logger.warning("Detected swapped lat/lon, corrected: (%s, %s)", lat, lon)

    # Check US bounds
    if not (US_LAT_MIN <= lat <= US_LAT_MAX):
        result["valid"] = False
        result["warnings"].append(f"latitude_out_of_bounds: {lat}")

    if not (US_LON_MIN <= lon <= US_LON_MAX):
        result["valid"] = False
        result["warnings"].append(f"longitude_out_of_bounds: {lon}")

    return result


def validate_site(site_data: dict) -> dict:
    """Validate a complete site record.

    Returns:
        Dict with 'status' ('pass'/'warning'/'fail'), 'site_data' (normalized),
        and 'issues' list.
    """
    issues = []
    status = "pass"

    # Normalize state
    if site_data.get("state"):
        site_data["state"] = normalize_state(site_data["state"])
        if site_data["state"] not in VALID_STATE_CODES:
            issues.append(f"unknown_state: {site_data['state']}")
            status = "warning"

    # Normalize dates
    for date_field in ("nhl_designation_date", "nrhp_cert_date", "date_constructed",
                        "state_designation_date"):
        if site_data.get(date_field):
            site_data[date_field] = normalize_date(site_data[date_field])

    # Validate coordinates
    coord_result = validate_coordinates(
        site_data.get("latitude"), site_data.get("longitude")
    )
    if coord_result["warnings"]:
        issues.extend(coord_result["warnings"])
        if not coord_result["valid"]:
            status = "fail" if status != "fail" else status
        else:
            status = "warning" if status == "pass" else status
    site_data["latitude"] = coord_result["lat"]
    site_data["longitude"] = coord_result["lon"]

    # Normalize city/county to title case
    for field in ("city", "county"):
        if site_data.get(field):
            site_data[field] = site_data[field].strip().title()

    # Normalize address
    if site_data.get("address"):
        site_data["address"] = site_data["address"].strip()

    return {"status": status, "site_data": site_data, "issues": issues}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in kilometers."""
    import math

    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _normalize_name_for_matching(name: str) -> str:
    """Strip common NPS suffixes and normalize for fuzzy matching."""
    from config.nrhp_taxonomy import NAME_SUFFIXES_TO_STRIP

    normalized = name.strip()
    for suffix in sorted(NAME_SUFFIXES_TO_STRIP, key=len, reverse=True):
        if normalized.lower().endswith(suffix.lower()):
            normalized = normalized[: -len(suffix)].strip()
            break

    # Remove parenthetical remarks
    normalized = re.sub(r"\s*\(.*?\)\s*", " ", normalized).strip()
    return normalized


class SpatialIndex:
    """Coarse lat/lon grid for fast spatial candidate lookup.

    Buckets sites into ~5.5km cells (0.05 degrees). Lookup returns sites
    from the 9 neighboring cells, reducing fuzzy match candidates from
    hundreds of thousands to typically 10-180.
    """

    CELL_SIZE = 0.05  # ~5.5 km at US latitudes

    def __init__(self):
        self._grid: dict[tuple, list[dict]] = defaultdict(list)
        self._no_coords: list[dict] = []

    def _cell(self, lat: float, lon: float) -> tuple[int, int]:
        return (round(lat / self.CELL_SIZE), round(lon / self.CELL_SIZE))

    def add(self, site: dict):
        """Add a site to the spatial index."""
        lat, lon = site.get("latitude"), site.get("longitude")
        if lat is not None and lon is not None:
            self._grid[self._cell(lat, lon)].append(site)
        else:
            self._no_coords.append(site)

    def neighbors(self, lat: float | None, lon: float | None) -> list[dict]:
        """Return sites in the 9 neighboring cells + all no-coord sites."""
        if lat is None or lon is None:
            # No coords: return everything (can't narrow spatially)
            result = list(self._no_coords)
            for bucket in self._grid.values():
                result.extend(bucket)
            return result

        cx, cy = self._cell(lat, lon)
        result = list(self._no_coords)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                result.extend(self._grid.get((cx + dx, cy + dy), []))
        return result


def find_fuzzy_matches(
    name: str,
    lat: float | None,
    lon: float | None,
    existing_sites: list[dict],
    spatial_index: SpatialIndex | None = None,
) -> list[dict]:
    """Find potential matches for a site among existing records.

    Uses fuzzy name matching + geographic proximity. When a spatial_index
    is provided, only nearby candidates are checked instead of the full list.

    Returns:
        List of match dicts with 'site_id', 'name', 'score', 'distance_km', 'match_type'.
    """
    from rapidfuzz import fuzz

    normalized = _normalize_name_for_matching(name)
    norm_len = len(normalized)
    matches = []

    candidates = spatial_index.neighbors(lat, lon) if spatial_index else existing_sites

    for site in candidates:
        existing_norm = _normalize_name_for_matching(site["name"])

        # Cheap length-ratio pre-check: skip if lengths differ by >2x
        ex_len = len(existing_norm)
        if norm_len and ex_len:
            ratio = norm_len / ex_len if norm_len < ex_len else ex_len / norm_len
            if ratio < 0.4:
                continue

        score = fuzz.token_sort_ratio(normalized, existing_norm)

        distance = None
        if lat and lon and site.get("latitude") and site.get("longitude"):
            distance = _haversine_km(lat, lon, site["latitude"], site["longitude"])

        match_info = {
            "site_id": site["id"],
            "name": site["name"],
            "score": score,
            "distance_km": distance,
        }

        # Strong match: high name similarity
        if score >= FUZZY_MATCH_THRESHOLD:
            match_info["match_type"] = "name_match"
            matches.append(match_info)
        # Geographic proximity with moderate name similarity
        elif (
            score >= FUZZY_MATCH_CANDIDATE
            and distance is not None
            and distance <= GEO_PROXIMITY_KM
        ):
            match_info["match_type"] = "proximity_match"
            matches.append(match_info)

    return sorted(matches, key=lambda m: m["score"], reverse=True)


def run_validation(sites: list[dict]) -> dict:
    """Run validation on a batch of site records and return a report.

    Returns:
        Dict with 'passed', 'warnings', 'failed' counts and 'details' list.
    """
    report = {"passed": 0, "warnings": 0, "failed": 0, "details": []}

    for site in sites:
        result = validate_site(site)
        status = result["status"]

        if status == "pass":
            report["passed"] += 1
        elif status == "warning":
            report["warnings"] += 1
        else:
            report["failed"] += 1

        if result["issues"]:
            report["details"].append({
                "name": site.get("name", "Unknown"),
                "nris_refnum": site.get("nris_refnum"),
                "status": status,
                "issues": result["issues"],
            })

    return report


def save_validation_report(report: dict, filepath: Path | None = None) -> Path:
    """Save validation report to JSON file."""
    if filepath is None:
        filepath = OUTPUT_DIR / "validation_report.json"
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(report, f, indent=2)
    logger.info("Validation report saved to %s", filepath)
    return filepath
