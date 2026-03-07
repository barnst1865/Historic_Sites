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

    def parse(self, raw_data: list[dict], config: dict) -> list[dict]:
        """Parse ArcGIS features into site records using the state's field map."""
        state_code = config["_state_code"]
        source_key = config.get("_source_key", state_code)
        field_map = config.get("field_map", {})
        sites = []

        for feature in raw_data:
            attrs = feature.get("attributes", {})
            geom = feature.get("geometry") or {}

            # ArcGIS geometry: {"x": longitude, "y": latitude}
            longitude = geom.get("x")
            latitude = geom.get("y")

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

            site = {
                "name": name,
                "address": address,
                "city": city,
                "county": county,
                "state": state_code,
                "latitude": latitude,
                "longitude": longitude,
                "coordinates_source": f"shpo_{state_code.lower()}",
                "source_shpo": True,
                "primary_source": f"shpo_{state_code.lower()}",
            }

            if nris_refnum:
                site["nris_refnum"] = nris_refnum
            if state_record_id:
                site["state_record_id"] = state_record_id
            if date_constructed:
                site["date_constructed"] = date_constructed
            if raw_date_listed is not None:
                site["state_designation_date"] = _epoch_ms_to_iso(raw_date_listed)

            sites.append(site)

        logger.info(
            "[SHPO] %s: Parsed %d site records from %d features",
            state_code,
            len(sites),
            len(raw_data),
        )
        return sites
