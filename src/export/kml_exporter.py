"""
KML/KMZ exporter for Google Maps and Google Earth.

Generates:
  - Per-state KML files (each under 2,000 points for Google My Maps)
  - Per-era and per-event KML files
  - Master KMZ with folder structure for Google Earth

Note: simplekml uses (longitude, latitude) order.
"""

import logging
import sqlite3
from collections import defaultdict
from pathlib import Path

import simplekml

from config.settings import OUTPUT_DIR

logger = logging.getLogger(__name__)

KML_DIR = OUTPUT_DIR / "kml"
MAX_POINTS_PER_FILE = 2000


def _site_description_html(site: dict) -> str:
    """Build HTML description for a KML placemark popup."""
    parts = []
    if site.get("short_description"):
        parts.append(f"<p>{site['short_description']}</p>")
    if site.get("address"):
        parts.append(f"<p><b>Address:</b> {site['address']}</p>")
    if site.get("city") and site.get("state"):
        parts.append(f"<p><b>Location:</b> {site['city']}, {site['state']}</p>")
    if site.get("nhl_designation_date"):
        parts.append(f"<p><b>NHL Designated:</b> {site['nhl_designation_date']}</p>")
    if site.get("nrhp_cert_date"):
        parts.append(f"<p><b>NRHP Listed:</b> {site['nrhp_cert_date']}</p>")
    if site.get("public_access"):
        parts.append(f"<p><b>Public Access:</b> {site['public_access']}</p>")
    if site.get("visiting_hours"):
        parts.append(f"<p><b>Hours:</b> {site['visiting_hours']}</p>")
    if site.get("admission_info"):
        parts.append(f"<p><b>Admission:</b> {site['admission_info']}</p>")
    if site.get("website_url"):
        parts.append(f'<p><a href="{site["website_url"]}">Website</a></p>')
    if site.get("confidence_score") is not None:
        parts.append(f"<p><b>Confidence:</b> {site['confidence_score']:.2f}</p>")
    return "\n".join(parts) if parts else site.get("name", "")


def _add_site_to_kml(kml_obj, site: dict, folder=None):
    """Add a site as a placemark to a KML document or folder."""
    target = folder if folder else kml_obj
    pnt = target.newpoint(
        name=site["name"],
        description=_site_description_html(site),
        coords=[(site["longitude"], site["latitude"])],  # simplekml: (lon, lat)
    )
    return pnt


def _get_sites_with_coords(conn: sqlite3.Connection) -> list[dict]:
    """Fetch all sites that have coordinates."""
    return [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM sites WHERE latitude IS NOT NULL AND longitude IS NOT NULL "
            "ORDER BY state, name"
        ).fetchall()
    ]


def export_by_state(conn: sqlite3.Connection) -> list[Path]:
    """Export separate KML files per state (for Google My Maps compatibility).

    Each file contains up to MAX_POINTS_PER_FILE points.
    """
    KML_DIR.mkdir(parents=True, exist_ok=True)
    sites = _get_sites_with_coords(conn)

    # Group by state
    by_state = defaultdict(list)
    for site in sites:
        state = site.get("state") or "Unknown"
        by_state[state].append(site)

    output_files = []
    for state, state_sites in sorted(by_state.items()):
        # Split into chunks if over limit
        for chunk_idx in range(0, len(state_sites), MAX_POINTS_PER_FILE):
            chunk = state_sites[chunk_idx:chunk_idx + MAX_POINTS_PER_FILE]
            suffix = f"_part{chunk_idx // MAX_POINTS_PER_FILE + 1}" if len(state_sites) > MAX_POINTS_PER_FILE else ""
            filename = f"historic_sites_{state}{suffix}.kml"

            kml = simplekml.Kml(name=f"Historic Sites — {state}{suffix}")
            for site in chunk:
                _add_site_to_kml(kml, site)

            filepath = KML_DIR / filename
            kml.save(str(filepath))
            output_files.append(filepath)

    logger.info("Exported %d state KML files to %s", len(output_files), KML_DIR)
    return output_files


def export_master_kmz(conn: sqlite3.Connection) -> Path:
    """Export a master KMZ file with folders organized by state.

    KMZ is a zipped KML that Google Earth reads natively.
    """
    KML_DIR.mkdir(parents=True, exist_ok=True)
    sites = _get_sites_with_coords(conn)

    kml = simplekml.Kml(name="Historic Sites of the United States")

    # Create folders by state
    by_state = defaultdict(list)
    for site in sites:
        state = site.get("state") or "Unknown"
        by_state[state].append(site)

    for state in sorted(by_state):
        folder = kml.newfolder(name=state)
        for site in by_state[state]:
            _add_site_to_kml(kml, site, folder=folder)

    filepath = KML_DIR / "historic_sites.kmz"
    kml.savekmz(str(filepath))
    logger.info("Exported master KMZ (%d sites) to %s", len(sites), filepath)
    return filepath


def export_kml(conn: sqlite3.Connection) -> dict:
    """Run all KML exports.

    Returns:
        Dict with 'state_files', 'master_kmz' paths.
    """
    state_files = export_by_state(conn)
    master = export_master_kmz(conn)
    return {"state_files": [str(f) for f in state_files], "master_kmz": str(master)}
