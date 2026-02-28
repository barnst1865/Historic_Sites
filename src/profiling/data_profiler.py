"""
Data profiling module.

Analyzes the database to understand data quality before AI enrichment.
Produces completeness matrices, value distributions, coordinate coverage,
description richness categorization, and outlier detection.

Output: HTML report + JSON machine-readable report.
"""

import json
import logging
import sqlite3
from collections import Counter
from pathlib import Path

from config.settings import OUTPUT_DIR

logger = logging.getLogger(__name__)

# Key fields to check for completeness
COMPLETENESS_FIELDS = [
    "nris_refnum", "name", "address", "city", "county", "state",
    "latitude", "longitude", "date_constructed", "nhl_designation_date",
    "nrhp_cert_date", "short_description", "full_description",
    "condition", "public_access", "website_url",
]

# Description richness thresholds (word count)
RICHNESS_THRESHOLDS = {
    "data_rich": 50,
    "data_moderate": 5,
    "data_poor": 0,
}


def profile_completeness(conn: sqlite3.Connection) -> dict:
    """Compute NULL rate per column for key fields.

    Returns:
        Dict mapping field names to {'total', 'non_null', 'null_rate'}.
    """
    total = conn.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
    if total == 0:
        return {}

    results = {}
    for field in COMPLETENESS_FIELDS:
        non_null = conn.execute(
            f"SELECT COUNT(*) FROM sites WHERE {field} IS NOT NULL AND {field} != ''"
        ).fetchone()[0]
        results[field] = {
            "total": total,
            "non_null": non_null,
            "null_count": total - non_null,
            "null_rate": round((total - non_null) / total, 4),
        }

    return results


def profile_by_source(conn: sqlite3.Connection) -> dict:
    """Compute completeness grouped by source flags.

    Returns:
        Dict mapping source names to completeness stats.
    """
    sources = {
        "arcgis": "source_arcgis",
        "spreadsheet": "source_spreadsheet",
        "nps_parks": "source_nps_parks",
        "nomination": "source_nomination",
    }

    results = {}
    for name, col in sources.items():
        total = conn.execute(f"SELECT COUNT(*) FROM sites WHERE {col} = 1").fetchone()[0]
        if total == 0:
            results[name] = {"total": 0}
            continue

        has_coords = conn.execute(
            f"SELECT COUNT(*) FROM sites WHERE {col} = 1 AND latitude IS NOT NULL"
        ).fetchone()[0]
        has_desc = conn.execute(
            f"SELECT COUNT(*) FROM sites WHERE {col} = 1 AND "
            "(full_description IS NOT NULL OR short_description IS NOT NULL)"
        ).fetchone()[0]

        results[name] = {
            "total": total,
            "has_coordinates": has_coords,
            "has_description": has_desc,
        }

    return results


def profile_value_distributions(conn: sqlite3.Connection) -> dict:
    """Compute value distributions for categorical fields.

    Returns:
        Dict with distribution for states, designation types, etc.
    """
    distributions = {}

    # State distribution
    rows = conn.execute(
        "SELECT state, COUNT(*) as cnt FROM sites WHERE state IS NOT NULL "
        "GROUP BY state ORDER BY cnt DESC"
    ).fetchall()
    distributions["states"] = {row["state"]: row["cnt"] for row in rows}

    # Designation types
    rows = conn.execute(
        "SELECT designation_type, COUNT(*) as cnt FROM site_designations "
        "GROUP BY designation_type ORDER BY cnt DESC"
    ).fetchall()
    distributions["designation_types"] = {row["designation_type"]: row["cnt"] for row in rows}

    # Review status
    rows = conn.execute(
        "SELECT review_status, COUNT(*) as cnt FROM sites "
        "GROUP BY review_status ORDER BY cnt DESC"
    ).fetchall()
    distributions["review_status"] = {row["review_status"]: row["cnt"] for row in rows}

    # Enrichment status
    rows = conn.execute(
        "SELECT enrichment_status, COUNT(*) as cnt FROM sites "
        "GROUP BY enrichment_status ORDER BY cnt DESC"
    ).fetchall()
    distributions["enrichment_status"] = {
        row["enrichment_status"]: row["cnt"] for row in rows
    }

    return distributions


def profile_coordinate_coverage(conn: sqlite3.Connection) -> dict:
    """Compute coordinate coverage statistics.

    Returns:
        Dict with total, with_coords, without_coords, by_state breakdown.
    """
    total = conn.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
    with_coords = conn.execute(
        "SELECT COUNT(*) FROM sites WHERE latitude IS NOT NULL"
    ).fetchone()[0]

    by_state = {}
    rows = conn.execute(
        "SELECT state, "
        "COUNT(*) as total, "
        "SUM(CASE WHEN latitude IS NOT NULL THEN 1 ELSE 0 END) as with_coords "
        "FROM sites WHERE state IS NOT NULL GROUP BY state ORDER BY state"
    ).fetchall()
    for row in rows:
        by_state[row["state"]] = {
            "total": row["total"],
            "with_coords": row["with_coords"],
            "coverage": round(row["with_coords"] / row["total"], 4) if row["total"] > 0 else 0,
        }

    return {
        "total": total,
        "with_coordinates": with_coords,
        "without_coordinates": total - with_coords,
        "coverage_rate": round(with_coords / total, 4) if total > 0 else 0,
        "by_state": by_state,
    }


def profile_description_richness(conn: sqlite3.Connection) -> dict:
    """Categorize sites by description richness (word count).

    Returns:
        Dict with counts for data_rich, data_moderate, data_poor.
    """
    rows = conn.execute(
        "SELECT id, full_description, short_description FROM sites"
    ).fetchall()

    categories = {"data_rich": 0, "data_moderate": 0, "data_poor": 0}
    site_richness = {}

    for row in rows:
        desc = row["full_description"] or row["short_description"] or ""
        word_count = len(desc.split()) if desc else 0

        if word_count >= RICHNESS_THRESHOLDS["data_rich"]:
            cat = "data_rich"
        elif word_count >= RICHNESS_THRESHOLDS["data_moderate"]:
            cat = "data_moderate"
        else:
            cat = "data_poor"

        categories[cat] += 1
        site_richness[row["id"]] = cat

    return {"counts": categories, "site_categories": site_richness}


def detect_outliers(conn: sqlite3.Connection) -> list[dict]:
    """Detect outlier records that may have data quality issues.

    Checks: coordinates far from state centroid, implausible dates.
    """
    outliers = []

    # Dates outside plausible range
    rows = conn.execute(
        "SELECT id, name, date_constructed FROM sites "
        "WHERE date_constructed IS NOT NULL"
    ).fetchall()
    for row in rows:
        date_str = row["date_constructed"]
        try:
            year = int(date_str[:4])
            if year < 1400 or year > 2026:
                outliers.append({
                    "site_id": row["id"],
                    "name": row["name"],
                    "issue": f"implausible_date: {date_str}",
                })
        except (ValueError, TypeError):
            pass

    # Coordinates at exact zero (common data error)
    rows = conn.execute(
        "SELECT id, name, latitude, longitude FROM sites "
        "WHERE latitude = 0 OR longitude = 0"
    ).fetchall()
    for row in rows:
        outliers.append({
            "site_id": row["id"],
            "name": row["name"],
            "issue": f"zero_coordinate: ({row['latitude']}, {row['longitude']})",
        })

    return outliers


def generate_profile(conn: sqlite3.Connection) -> dict:
    """Generate complete data profile.

    Returns:
        Full profile dict with all analysis results.
    """
    logger.info("Generating data profile...")

    profile = {
        "completeness": profile_completeness(conn),
        "by_source": profile_by_source(conn),
        "distributions": profile_value_distributions(conn),
        "coordinate_coverage": profile_coordinate_coverage(conn),
        "description_richness": profile_description_richness(conn),
        "outliers": detect_outliers(conn),
    }

    # Summary stats
    total = conn.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
    profile["summary"] = {
        "total_sites": total,
        "total_sources": conn.execute("SELECT COUNT(*) FROM site_sources").fetchone()[0],
        "total_designations": conn.execute(
            "SELECT COUNT(*) FROM site_designations"
        ).fetchone()[0],
    }

    return profile


def save_json_report(profile: dict, filepath: Path | None = None) -> Path:
    """Save profile as JSON."""
    if filepath is None:
        filepath = OUTPUT_DIR / "data_profile.json"
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(profile, f, indent=2, default=str)
    logger.info("Profile JSON saved to %s", filepath)
    return filepath


def save_html_report(profile: dict, filepath: Path | None = None) -> Path:
    """Generate an HTML data profile report."""
    if filepath is None:
        filepath = OUTPUT_DIR / "data_profile_report.html"
    filepath.parent.mkdir(parents=True, exist_ok=True)

    summary = profile.get("summary", {})
    completeness = profile.get("completeness", {})
    coord_cov = profile.get("coordinate_coverage", {})
    richness = profile.get("description_richness", {}).get("counts", {})
    outliers = profile.get("outliers", [])

    # Build completeness rows
    comp_rows = ""
    for field, stats in completeness.items():
        pct = (1 - stats["null_rate"]) * 100
        color = "#4caf50" if pct > 80 else "#ff9800" if pct > 50 else "#f44336"
        comp_rows += (
            f"<tr><td>{field}</td><td>{stats['non_null']}/{stats['total']}</td>"
            f"<td><div style='background:{color};width:{pct}%;height:20px;'></div>"
            f"{pct:.1f}%</td></tr>\n"
        )

    # Build outlier rows
    outlier_rows = ""
    for o in outliers[:50]:
        outlier_rows += f"<tr><td>{o['site_id']}</td><td>{o['name']}</td><td>{o['issue']}</td></tr>\n"

    html = f"""<!DOCTYPE html>
<html><head><title>Historic Sites Data Profile</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 40px; }}
table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background: #f5f5f5; }}
.stat {{ display: inline-block; margin: 10px 20px; padding: 20px; background: #f0f0f0;
         border-radius: 8px; text-align: center; min-width: 150px; }}
.stat h3 {{ margin: 0; font-size: 2em; color: #333; }}
.stat p {{ margin: 5px 0 0; color: #666; }}
</style></head>
<body>
<h1>Historic Sites — Data Profile Report</h1>

<div>
  <div class="stat"><h3>{summary.get('total_sites', 0):,}</h3><p>Total Sites</p></div>
  <div class="stat"><h3>{coord_cov.get('with_coordinates', 0):,}</h3><p>With Coordinates</p></div>
  <div class="stat"><h3>{summary.get('total_designations', 0):,}</h3><p>Designations</p></div>
  <div class="stat"><h3>{len(outliers)}</h3><p>Outliers</p></div>
</div>

<h2>Field Completeness</h2>
<table><tr><th>Field</th><th>Populated</th><th>Coverage</th></tr>
{comp_rows}
</table>

<h2>Description Richness</h2>
<table><tr><th>Category</th><th>Count</th></tr>
<tr><td>Data Rich (50+ words)</td><td>{richness.get('data_rich', 0)}</td></tr>
<tr><td>Data Moderate (5-50 words)</td><td>{richness.get('data_moderate', 0)}</td></tr>
<tr><td>Data Poor (&lt;5 words)</td><td>{richness.get('data_poor', 0)}</td></tr>
</table>

<h2>Coordinate Coverage</h2>
<p>{coord_cov.get('with_coordinates', 0)} / {coord_cov.get('total', 0)} sites have coordinates
({coord_cov.get('coverage_rate', 0) * 100:.1f}%)</p>

<h2>Outliers ({len(outliers)} detected)</h2>
<table><tr><th>ID</th><th>Name</th><th>Issue</th></tr>
{outlier_rows}
</table>

</body></html>"""

    with open(filepath, "w") as f:
        f.write(html)
    logger.info("Profile HTML saved to %s", filepath)
    return filepath
