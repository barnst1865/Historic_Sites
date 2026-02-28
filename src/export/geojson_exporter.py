"""
GeoJSON exporter for web mapping.

Generates RFC 7946 compliant GeoJSON with flat feature properties
(no nesting) for compatibility with Leaflet, Mapbox, and Google Maps JS API.

Separate files by designation level to keep sizes manageable.
"""

import json
import logging
import sqlite3
from pathlib import Path

from config.settings import OUTPUT_DIR

logger = logging.getLogger(__name__)

GEOJSON_DIR = OUTPUT_DIR / "geojson"


def _site_to_feature(site: dict) -> dict:
    """Convert a site record to a GeoJSON Feature with flat properties."""
    properties = {
        "id": site["id"],
        "name": site["name"],
        "nris_refnum": site.get("nris_refnum"),
        "state": site.get("state"),
        "city": site.get("city"),
        "county": site.get("county"),
        "address": site.get("address"),
        "date_constructed": site.get("date_constructed"),
        "nhl_designation_date": site.get("nhl_designation_date"),
        "nrhp_cert_date": site.get("nrhp_cert_date"),
        "condition": site.get("condition"),
        "public_access": site.get("public_access"),
        "website_url": site.get("website_url"),
        "short_description": site.get("short_description"),
        "confidence_score": site.get("confidence_score"),
        "review_status": site.get("review_status"),
    }

    # Remove None values for cleaner output
    properties = {k: v for k, v in properties.items() if v is not None}

    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [site["longitude"], site["latitude"]],  # GeoJSON: [lon, lat]
        },
        "properties": properties,
    }


def _write_geojson(features: list[dict], filepath: Path, name: str) -> Path:
    """Write a GeoJSON FeatureCollection to file."""
    collection = {
        "type": "FeatureCollection",
        "name": name,
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
        },
        "features": features,
    }

    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(collection, f, indent=2)

    logger.info("Exported %d features to %s", len(features), filepath)
    return filepath


def export_all_sites(conn: sqlite3.Connection) -> Path:
    """Export all sites with coordinates as a single GeoJSON file."""
    sites = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM sites WHERE latitude IS NOT NULL AND longitude IS NOT NULL"
        ).fetchall()
    ]

    features = [_site_to_feature(s) for s in sites]
    return _write_geojson(
        features, GEOJSON_DIR / "all_historic_sites.geojson", "All Historic Sites"
    )


def export_nhls(conn: sqlite3.Connection) -> Path:
    """Export National Historic Landmarks as GeoJSON."""
    sites = [
        dict(row)
        for row in conn.execute(
            "SELECT s.* FROM sites s "
            "JOIN site_designations d ON s.id = d.site_id "
            "WHERE d.designation_type = 'Federal NHL' "
            "AND s.latitude IS NOT NULL AND s.longitude IS NOT NULL"
        ).fetchall()
    ]

    features = [_site_to_feature(s) for s in sites]
    return _write_geojson(
        features, GEOJSON_DIR / "nhls.geojson", "National Historic Landmarks"
    )


def export_by_state(conn: sqlite3.Connection) -> list[Path]:
    """Export separate GeoJSON files per state."""
    states = [
        row["state"]
        for row in conn.execute(
            "SELECT DISTINCT state FROM sites WHERE state IS NOT NULL "
            "AND latitude IS NOT NULL ORDER BY state"
        ).fetchall()
    ]

    paths = []
    for state in states:
        sites = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM sites WHERE state = ? "
                "AND latitude IS NOT NULL AND longitude IS NOT NULL",
                (state,),
            ).fetchall()
        ]
        features = [_site_to_feature(s) for s in sites]
        path = _write_geojson(
            features,
            GEOJSON_DIR / f"historic_sites_{state}.geojson",
            f"Historic Sites — {state}",
        )
        paths.append(path)

    return paths


def export_geojson(conn: sqlite3.Connection) -> dict:
    """Run all GeoJSON exports.

    Returns:
        Dict with file paths for each export.
    """
    all_path = export_all_sites(conn)
    nhl_path = export_nhls(conn)
    state_paths = export_by_state(conn)

    return {
        "all_sites": str(all_path),
        "nhls": str(nhl_path),
        "state_files": [str(p) for p in state_paths],
    }
