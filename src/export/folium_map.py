"""
Interactive HTML map generator using Folium.

Creates a Leaflet-based map with:
  - MarkerCluster for performance
  - FeatureGroups with LayerControl by designation level
  - Styled popups with visitor access info
  - Terrain basemap option
"""

import logging
import sqlite3
from pathlib import Path

import folium
from folium.plugins import MarkerCluster

from config.settings import OUTPUT_DIR

logger = logging.getLogger(__name__)

MAP_DIR = OUTPUT_DIR / "maps"

# Default map center (approximate center of contiguous US)
DEFAULT_CENTER = [39.8283, -98.5795]
DEFAULT_ZOOM = 5


def _popup_html(site: dict) -> str:
    """Build styled HTML popup for a map marker."""
    parts = [f"<h4>{site['name']}</h4>"]

    if site.get("city") and site.get("state"):
        parts.append(f"<p><b>{site['city']}, {site['state']}</b></p>")
    elif site.get("state"):
        parts.append(f"<p><b>{site['state']}</b></p>")

    if site.get("short_description"):
        desc = site["short_description"][:300]
        parts.append(f"<p>{desc}</p>")

    if site.get("nhl_designation_date"):
        parts.append(f"<p><small>NHL: {site['nhl_designation_date']}</small></p>")

    if site.get("public_access"):
        parts.append(f"<p><small>Access: {site['public_access']}</small></p>")

    if site.get("visiting_hours"):
        parts.append(f"<p><small>Hours: {site['visiting_hours'][:100]}</small></p>")

    if site.get("admission_info"):
        parts.append(f"<p><small>{site['admission_info'][:100]}</small></p>")

    if site.get("website_url"):
        parts.append(f'<p><a href="{site["website_url"]}" target="_blank">Website</a></p>')

    return "\n".join(parts)


def _designation_color(conn: sqlite3.Connection, site_id: int) -> str:
    """Choose marker color based on highest designation level."""
    row = conn.execute(
        "SELECT designation_type FROM site_designations WHERE site_id = ? "
        "ORDER BY CASE designation_type "
        "WHEN 'Federal NHL' THEN 1 "
        "WHEN 'Federal NRHP' THEN 2 "
        "WHEN 'NPS Unit' THEN 3 "
        "WHEN 'State Register' THEN 4 "
        "WHEN 'Local Landmark' THEN 5 "
        "ELSE 6 END "
        "LIMIT 1",
        (site_id,),
    ).fetchone()

    if not row:
        return "gray"

    colors = {
        "Federal NHL": "red",
        "Federal NRHP": "blue",
        "NPS Unit": "green",
        "State Register": "orange",
        "Local Landmark": "purple",
        "Tribal": "darkred",
        "Private/NGO": "cadetblue",
    }
    return colors.get(row["designation_type"], "gray")


def generate_map(conn: sqlite3.Connection) -> Path:
    """Generate an interactive Folium map with all sites.

    Returns:
        Path to the saved HTML file.
    """
    MAP_DIR.mkdir(parents=True, exist_ok=True)

    # Create base map with multiple tile layers
    m = folium.Map(
        location=DEFAULT_CENTER,
        zoom_start=DEFAULT_ZOOM,
        tiles="OpenStreetMap",
    )

    # Add terrain option
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
        attr="Esri",
        name="Terrain",
    ).add_to(m)

    # Create feature groups by designation level
    groups = {
        "National Historic Landmarks": folium.FeatureGroup(name="National Historic Landmarks"),
        "National Register": folium.FeatureGroup(name="National Register"),
        "NPS Units": folium.FeatureGroup(name="NPS Units"),
        "Other": folium.FeatureGroup(name="Other Sites"),
    }

    # Fetch all sites with coordinates
    sites = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM sites WHERE latitude IS NOT NULL AND longitude IS NOT NULL"
        ).fetchall()
    ]

    logger.info("Adding %d sites to map", len(sites))

    # Add MarkerCluster to each group
    clusters = {name: MarkerCluster() for name in groups}
    for name, cluster in clusters.items():
        cluster.add_to(groups[name])

    for site in sites:
        popup_html = _popup_html(site)
        color = _designation_color(conn, site["id"])

        # Determine which group this site belongs to
        designation = conn.execute(
            "SELECT designation_type FROM site_designations WHERE site_id = ? LIMIT 1",
            (site["id"],),
        ).fetchone()

        if designation:
            dtype = designation["designation_type"]
            if dtype == "Federal NHL":
                group_name = "National Historic Landmarks"
            elif dtype == "Federal NRHP":
                group_name = "National Register"
            elif dtype == "NPS Unit":
                group_name = "NPS Units"
            else:
                group_name = "Other"
        else:
            group_name = "Other"

        folium.Marker(
            location=[site["latitude"], site["longitude"]],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=site["name"],
            icon=folium.Icon(color=color, icon="info-sign"),
        ).add_to(clusters[group_name])

    # Add groups to map
    for group in groups.values():
        group.add_to(m)

    # Add layer control
    folium.LayerControl().add_to(m)

    filepath = MAP_DIR / "historic_sites_map.html"
    m.save(str(filepath))
    logger.info("Map saved to %s", filepath)
    return filepath
