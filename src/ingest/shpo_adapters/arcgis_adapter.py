"""
Generic ArcGIS REST adapter for state SHPO data.

Reuses pagination, field mapping, and caching patterns from arcgis_client.py.
Each state's field names and endpoint are configured in config/state_sources.py.
"""

import json
import logging
import time

import requests

from config.settings import RAW_DIR
from src.ingest.arcgis_client import _epoch_ms_to_iso, _get_attr
from src.ingest.shpo_adapters.base import SHPOAdapter

logger = logging.getLogger(__name__)

# Map full state names to 2-letter codes for national datasets
_STATE_NAME_TO_CODE = {
    "ALABAMA": "AL", "ALASKA": "AK", "AMERICAN SAMOA": "AS", "ARIZONA": "AZ",
    "ARKANSAS": "AR", "CALIFORNIA": "CA", "COLORADO": "CO", "CONNECTICUT": "CT",
    "DELAWARE": "DE", "DISTRICT OF COLUMBIA": "DC", "FLORIDA": "FL",
    "GEORGIA": "GA", "GUAM": "GU", "HAWAII": "HI", "IDAHO": "ID",
    "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS",
    "KENTUCKY": "KY", "LOUISIANA": "LA", "MAINE": "ME", "MARYLAND": "MD",
    "MASSACHUSETTS": "MA", "MICHIGAN": "MI", "MINNESOTA": "MN",
    "MISSISSIPPI": "MS", "MISSOURI": "MO", "MONTANA": "MT", "NEBRASKA": "NE",
    "NEVADA": "NV", "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ",
    "NEW MEXICO": "NM", "NEW YORK": "NY", "NORTH CAROLINA": "NC",
    "NORTH DAKOTA": "ND", "N. MARIANA ISLANDS": "MP", "OHIO": "OH",
    "OKLAHOMA": "OK", "OREGON": "OR", "PALAU": "PW", "PENNSYLVANIA": "PA",
    "PUERTO RICO": "PR", "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD", "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT",
    "VERMONT": "VT", "VIRGIN ISLANDS": "VI", "VIRGINIA": "VA",
    "WASHINGTON": "WA", "WEST VIRGINIA": "WV", "WISCONSIN": "WI",
    "WYOMING": "WY", "FED. STATES": "FM", "MARSHALL ISLANDS": "MH",
}


class ArcGISAdapter(SHPOAdapter):
    """Generic ArcGIS REST API adapter for SHPO endpoints."""

    def fetch(self, config: dict, use_cache: bool = True) -> list[dict]:
        """Fetch all records from a state ArcGIS endpoint with pagination."""
        state_code = config["_state_code"]
        source_key = config.get("_source_key", state_code)
        cache_file = RAW_DIR / f"shpo_{source_key.lower()}.json"

        if use_cache and cache_file.exists():
            logger.info("[SHPO] %s: Loading from cache: %s", source_key, cache_file)
            with open(cache_file) as f:
                return json.load(f)

        logger.info("[SHPO] %s: Fetching from %s", source_key, config["endpoint"])

        pagination = config.get("pagination", "offset")
        if pagination == "objectid":
            all_features = self._fetch_by_objectid(config, source_key)
        else:
            all_features = self._fetch_by_offset(config, source_key)

        # Cache raw response
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "w") as f:
            json.dump(all_features, f)
        logger.info(
            "[SHPO] %s: Cached %d records to %s",
            source_key,
            len(all_features),
            cache_file,
        )

        return all_features

    def _fetch_by_offset(self, config: dict, source_key: str) -> list[dict]:
        """Standard resultOffset pagination."""
        all_features = []
        offset = 0
        page_size = config.get("page_size", 1000)
        rate_limit = config.get("rate_limit", 0.5)

        while True:
            params = {
                "where": config.get("where", "1=1"),
                "outFields": "*",
                "outSR": str(config.get("out_sr", 4326)),
                "f": "json",
                "resultOffset": offset,
                "resultRecordCount": page_size,
                "returnGeometry": "true",
            }

            response = requests.get(config["endpoint"], params=params, timeout=60)
            response.raise_for_status()
            data = response.json()

            if "error" in data:
                raise RuntimeError(
                    f"[SHPO] {source_key}: ArcGIS API error: {data['error']}"
                )

            features = data.get("features", [])
            if not features:
                break

            all_features.extend(features)
            offset += len(features)
            logger.info(
                "[SHPO] %s: Fetched %d records (total: %d)",
                source_key,
                len(features),
                len(all_features),
            )

            if not data.get("exceededTransferLimit", False):
                break

            time.sleep(rate_limit)

        return all_features

    def _fetch_by_objectid(self, config: dict, source_key: str) -> list[dict]:
        """ObjectId-based pagination for servers that don't support resultOffset."""
        page_size = config.get("page_size", 1000)
        rate_limit = config.get("rate_limit", 0.5)
        oid_field = config.get("oid_field", "OBJECTID")

        # Step 1: Get all object IDs
        logger.info("[SHPO] %s: Fetching object IDs...", source_key)
        params = {
            "where": config.get("where", "1=1"),
            "returnIdsOnly": "true",
            "f": "json",
        }
        response = requests.get(config["endpoint"], params=params, timeout=60)
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            raise RuntimeError(
                f"[SHPO] {source_key}: ArcGIS API error: {data['error']}"
            )

        object_ids = sorted(data.get("objectIds", []))
        if not object_ids:
            logger.warning("[SHPO] %s: No object IDs returned", source_key)
            return []

        logger.info("[SHPO] %s: Found %d object IDs", source_key, len(object_ids))

        # Step 2: Fetch in batches by ID range
        all_features = []
        for i in range(0, len(object_ids), page_size):
            batch_ids = object_ids[i : i + page_size]
            id_list = ",".join(str(oid) for oid in batch_ids)

            params = {
                "objectIds": id_list,
                "outFields": "*",
                "outSR": str(config.get("out_sr", 4326)),
                "f": "json",
                "returnGeometry": "true",
            }

            response = requests.get(config["endpoint"], params=params, timeout=60)
            response.raise_for_status()
            data = response.json()

            if "error" in data:
                raise RuntimeError(
                    f"[SHPO] {source_key}: ArcGIS API error: {data['error']}"
                )

            features = data.get("features", [])
            all_features.extend(features)
            logger.info(
                "[SHPO] %s: Fetched %d records (total: %d / %d)",
                source_key,
                len(features),
                len(all_features),
                len(object_ids),
            )

            time.sleep(rate_limit)

        return all_features

    def parse(self, raw_data: list[dict], config: dict) -> list[dict]:
        """Parse ArcGIS features into site records using the state's field map."""
        state_code = config["_state_code"]
        source_key = config.get("_source_key", state_code)
        field_map = config.get("field_map", {})
        sites = []

        for feature in raw_data:
            attrs = feature.get("attributes", {})
            geom = feature.get("geometry") or {}

            # ArcGIS geometry: points have {"x": lon, "y": lat}
            # Polygons have {"rings": [[[x,y], ...], ...]}
            longitude = geom.get("x")
            latitude = geom.get("y")

            if longitude is None or latitude is None:
                # Try multipoint: {"points": [[x,y], ...]}
                points = geom.get("points")
                if points and points[0]:
                    longitude = points[0][0]
                    latitude = points[0][1]

            if longitude is None or latitude is None:
                # Try polygon centroid from rings
                rings = geom.get("rings")
                if rings and rings[0]:
                    ring = rings[0]  # outer ring
                    longitude = sum(p[0] for p in ring) / len(ring)
                    latitude = sum(p[1] for p in ring) / len(ring)

            # Skip features with null geometry
            if longitude is None or latitude is None:
                logger.debug(
                    "[SHPO] %s: Skipping feature with no geometry", state_code
                )
                continue

            # Resolve name from field aliases
            name = _get_attr(attrs, *field_map.get("name", []))
            if name:
                # Strip invisible Unicode chars (zero-width spaces, etc.)
                name = name.strip().strip("\u200b\u200c\u200d\ufeff")

            # Skip records with no name
            if not name:
                logger.debug(
                    "[SHPO] %s: Skipping feature with no name", state_code
                )
                continue

            # Build address — handle compound address_parts or simple alias
            address = None
            if "address_parts" in field_map:
                parts = field_map["address_parts"]
                number = _get_attr(attrs, *parts.get("number", []))
                direction = _get_attr(attrs, *parts.get("direction", []))
                street = _get_attr(attrs, *parts.get("street", []))
                addr_components = [
                    c for c in [number, direction, street] if c
                ]
                address = " ".join(addr_components) if addr_components else None
            elif field_map.get("address"):
                address = _get_attr(attrs, *field_map["address"])

            # Resolve other fields
            city = _get_attr(attrs, *field_map.get("city", []))
            county = _get_attr(attrs, *field_map.get("county", []))
            nris_refnum = _get_attr(attrs, *field_map.get("nris_refnum", []))
            state_record_id = _get_attr(
                attrs, *field_map.get("state_record_id", [])
            )

            # Date fields
            date_constructed = _get_attr(
                attrs, *field_map.get("date_constructed", [])
            )
            raw_date_listed = None
            for key in field_map.get("date_listed", []):
                val = attrs.get(key)
                if val is not None:
                    raw_date_listed = val
                    break

            # Allow per-record state from a field (e.g. national NRHP dataset)
            state_name_field = field_map.get("state_name_field")
            record_state = state_code
            if state_name_field:
                raw_state = _get_attr(attrs, state_name_field)
                record_state = _STATE_NAME_TO_CODE.get(
                    (raw_state or "").upper(), state_code
                )

            site = {
                "name": name,
                "address": address,
                "city": city,
                "county": county,
                "state": record_state,
                "latitude": latitude,
                "longitude": longitude,
                "coordinates_source": f"shpo_{source_key.lower()}",
                "source_shpo": True,
                "primary_source": f"shpo_{source_key.lower()}",
            }

            if nris_refnum:
                site["nris_refnum"] = nris_refnum
            if state_record_id:
                site["state_record_id"] = state_record_id
            if date_constructed:
                site["date_constructed"] = date_constructed
            if raw_date_listed is not None:
                if isinstance(raw_date_listed, str):
                    site["state_designation_date"] = raw_date_listed
                else:
                    site["state_designation_date"] = _epoch_ms_to_iso(raw_date_listed)

            sites.append(site)

        logger.info(
            "[SHPO] %s: Parsed %d site records from %d features",
            state_code,
            len(sites),
            len(raw_data),
        )
        return sites
