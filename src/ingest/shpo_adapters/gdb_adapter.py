"""
Generic File Geodatabase (GDB) adapter for local SHPO data downloads.

Reads .gdb folders using geopandas/pyogrio, reprojects to EPSG:4326,
and maps fields using the same config pattern as the ArcGIS adapter.
"""

import json
import logging
from pathlib import Path

import geopandas as gpd

from config.settings import RAW_DIR
from src.ingest.shpo_adapters.base import SHPOAdapter

logger = logging.getLogger(__name__)


class GDBAdapter(SHPOAdapter):
    """Adapter for local File Geodatabase (.gdb) downloads."""

    def fetch(self, config: dict, use_cache: bool = True) -> list[dict]:
        """Read features from a local GDB file.

        Returns list of dicts mimicking ArcGIS feature format:
        [{"attributes": {...}, "geometry": {"x": lon, "y": lat}}, ...]
        """
        state_code = config["_state_code"]
        source_key = config.get("_source_key", state_code)
        cache_file = RAW_DIR / f"shpo_{source_key.lower()}.json"

        if use_cache and cache_file.exists():
            logger.info("[SHPO] %s: Loading from cache: %s", source_key, cache_file)
            with open(cache_file) as f:
                return json.load(f)

        gdb_path = Path(config["gdb_path"])
        layer = config.get("layer")

        if not gdb_path.exists():
            raise FileNotFoundError(f"[SHPO] {source_key}: GDB not found: {gdb_path}")

        logger.info("[SHPO] %s: Reading %s (layer=%s)", source_key, gdb_path, layer)
        gdf = gpd.read_file(gdb_path, layer=layer)
        logger.info("[SHPO] %s: Read %d features", source_key, len(gdf))

        # Reproject to WGS84 if needed
        if gdf.crs and gdf.crs.to_epsg() != 4326:
            logger.info(
                "[SHPO] %s: Reprojecting from %s to EPSG:4326", source_key, gdf.crs
            )
            gdf = gdf.to_crs(epsg=4326)

        # Convert to ArcGIS-like feature dicts
        features = []
        for _, row in gdf.iterrows():
            attrs = {
                k: (v if not _is_nan(v) else None)
                for k, v in row.items()
                if k != "geometry"
            }

            geom = row.geometry
            if geom is not None and not geom.is_empty:
                centroid = geom.centroid
                geometry = {"x": centroid.x, "y": centroid.y}
            else:
                geometry = {}

            features.append({"attributes": attrs, "geometry": geometry})

        # Cache
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "w") as f:
            json.dump(features, f, default=str)
        logger.info(
            "[SHPO] %s: Cached %d records to %s", source_key, len(features), cache_file
        )

        return features

    def parse(self, raw_data: list[dict], config: dict) -> list[dict]:
        """Parse GDB features into site records using the state's field map."""
        state_code = config["_state_code"]
        source_key = config.get("_source_key", state_code)
        field_map = config.get("field_map", {})
        sites = []

        for feature in raw_data:
            attrs = feature.get("attributes", {})
            geom = feature.get("geometry") or {}

            longitude = geom.get("x")
            latitude = geom.get("y")

            if longitude is None or latitude is None:
                continue

            # Resolve name from field aliases
            name = _get_first(attrs, *field_map.get("name", []))
            if name:
                name = str(name).strip()
            if not name:
                continue

            address = _get_first(attrs, *field_map.get("address", []))
            city = _get_first(attrs, *field_map.get("city", []))
            county = _get_first(attrs, *field_map.get("county", []))
            nris_refnum = _get_first(attrs, *field_map.get("nris_refnum", []))
            state_record_id = _get_first(attrs, *field_map.get("state_record_id", []))
            date_constructed = _get_first(attrs, *field_map.get("date_constructed", []))
            date_listed = _get_first(attrs, *field_map.get("date_listed", []))

            site = {
                "name": name,
                "address": str(address).strip() if address else None,
                "city": str(city).strip() if city else None,
                "county": str(county).strip() if county else None,
                "state": state_code,
                "latitude": latitude,
                "longitude": longitude,
                "coordinates_source": f"shpo_{source_key.lower()}",
                "source_shpo": True,
                "primary_source": f"shpo_{source_key.lower()}",
            }

            if nris_refnum:
                site["nris_refnum"] = str(nris_refnum).strip()
            if state_record_id:
                site["state_record_id"] = str(state_record_id).strip()
            if date_constructed:
                site["date_constructed"] = str(date_constructed).strip()
            if date_listed:
                site["state_designation_date"] = str(date_listed).strip()

            sites.append(site)

        logger.info(
            "[SHPO] %s: Parsed %d site records from %d features",
            source_key,
            len(sites),
            len(raw_data),
        )
        return sites


def _get_first(attrs: dict, *keys: str) -> str | None:
    """Get the first non-empty value from a list of attribute key aliases."""
    for key in keys:
        val = attrs.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return None


def _is_nan(value) -> bool:
    """Check if a value is NaN (float or pandas NA)."""
    try:
        import math
        return isinstance(value, float) and math.isnan(value)
    except (TypeError, ValueError):
        return False
