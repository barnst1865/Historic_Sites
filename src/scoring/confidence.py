"""
Multi-factor confidence scoring algorithm.

Eight weighted factors produce a composite score (0.0-1.0).
Thresholds: >=0.8 auto-approved, 0.5-0.8 unreviewed, <0.5 flagged.
"""

import logging
import sqlite3
import statistics

from config.settings import SCORE_AUTO_APPROVE, SCORE_FLAG_REVIEW
from src.db.queries import update_site, start_pipeline_run, complete_pipeline_run

logger = logging.getLogger(__name__)

# Scoring weights (must sum to 1.0)
WEIGHTS = {
    "data_completeness": 0.10,
    "description_richness": 0.10,
    "nrhp_official_data": 0.15,
    "nomination_extraction": 0.10,
    "ai_confidence": 0.25,
    "classification_ambiguity": 0.10,
    "source_agreement": 0.10,
    "name_specificity": 0.10,
}

# Generic names that get penalized
GENERIC_NAMES = {
    "historic district", "historic site", "historic building", "site",
    "building", "district", "house", "church", "school", "bridge",
    "cemetery", "fort", "park", "monument",
}

# Key completeness fields
KEY_FIELDS = [
    "latitude", "longitude", "state", "address", "city",
    "date_constructed", "nhl_designation_date",
]


def _score_data_completeness(site: dict) -> float:
    """Score based on percentage of key fields that are populated."""
    populated = sum(1 for f in KEY_FIELDS if site.get(f) is not None)
    return populated / len(KEY_FIELDS)


def _score_description_richness(site: dict) -> float:
    """Score based on description word count."""
    desc = site.get("full_description") or site.get("short_description") or ""
    words = len(desc.split())
    if words >= 100:
        return 1.0
    elif words >= 50:
        return 0.7
    elif words >= 5:
        return 0.4
    return 0.1


def _score_nrhp_official_data(conn: sqlite3.Connection, site_id: int) -> float:
    """Score based on presence of NRHP criteria, areas, and periods."""
    has_criteria = conn.execute(
        "SELECT COUNT(*) FROM nrhp_criteria WHERE site_id = ?", (site_id,)
    ).fetchone()[0] > 0

    has_areas = conn.execute(
        "SELECT COUNT(*) FROM nrhp_areas_of_significance WHERE site_id = ?", (site_id,)
    ).fetchone()[0] > 0

    has_periods = conn.execute(
        "SELECT COUNT(*) FROM nrhp_periods_of_significance WHERE site_id = ?", (site_id,)
    ).fetchone()[0] > 0

    score = 0.0
    if has_criteria:
        score += 0.4
    if has_areas:
        score += 0.35
    if has_periods:
        score += 0.25
    return score


def _score_nomination_extraction(site: dict) -> float:
    """Score based on nomination extraction quality."""
    if not site.get("source_nomination"):
        return 0.3  # No nomination attempted/available

    # Check if full_description was populated (sign of successful extraction)
    if site.get("full_description") and len(str(site["full_description"])) > 100:
        return 1.0
    elif site.get("full_description"):
        return 0.7

    return 0.2  # Nomination flagged but extraction failed


def _score_ai_confidence(conn: sqlite3.Connection, site_id: int) -> float:
    """Score based on mean confidence of AI-assigned categories."""
    confidences = []
    for table in ("site_eras", "site_events", "site_site_types", "site_ownership"):
        rows = conn.execute(
            f"SELECT confidence FROM {table} WHERE site_id = ?", (site_id,)
        ).fetchall()
        confidences.extend(row["confidence"] for row in rows)

    if not confidences:
        return 0.0
    return statistics.mean(confidences)


def _score_classification_ambiguity(conn: sqlite3.Connection, site_id: int) -> float:
    """Score based on clarity of classifications (low variance = clear)."""
    confidences = []
    for table in ("site_eras", "site_events", "site_site_types", "site_ownership"):
        rows = conn.execute(
            f"SELECT confidence FROM {table} WHERE site_id = ?", (site_id,)
        ).fetchall()
        confidences.extend(row["confidence"] for row in rows)

    if len(confidences) < 2:
        return 0.5  # Neutral if too few to measure
    return 1.0 - min(1.0, statistics.stdev(confidences))


def _score_source_agreement(site: dict) -> float:
    """Score based on number of contributing data sources."""
    sources = sum(1 for flag in (
        "source_arcgis", "source_spreadsheet", "source_nps_parks",
        "source_nomination", "source_shpo", "source_other"
    ) if site.get(flag))

    if sources >= 4:
        return 1.0
    elif sources == 3:
        return 0.8
    elif sources == 2:
        return 0.6
    return 0.3


def _score_name_specificity(site: dict) -> float:
    """Score based on name specificity (penalize generic names)."""
    name = (site.get("name") or "").lower().strip()
    if not name:
        return 0.0

    # Check if the name is just a generic term
    for generic in GENERIC_NAMES:
        if name == generic or name.startswith(generic + " #"):
            return 0.2

    # Short names are less specific
    if len(name) < 10:
        return 0.6

    return 1.0


def calculate_confidence(
    conn: sqlite3.Connection, site: dict
) -> tuple[float, dict]:
    """Calculate composite confidence score for a site.

    Returns:
        Tuple of (composite_score, factor_scores_dict).
    """
    site_id = site["id"]

    factors = {
        "data_completeness": _score_data_completeness(site),
        "description_richness": _score_description_richness(site),
        "nrhp_official_data": _score_nrhp_official_data(conn, site_id),
        "nomination_extraction": _score_nomination_extraction(site),
        "ai_confidence": _score_ai_confidence(conn, site_id),
        "classification_ambiguity": _score_classification_ambiguity(conn, site_id),
        "source_agreement": _score_source_agreement(site),
        "name_specificity": _score_name_specificity(site),
    }

    composite = sum(factors[k] * WEIGHTS[k] for k in factors)
    return round(composite, 4), factors


def run_scoring(conn: sqlite3.Connection) -> dict:
    """Run confidence scoring on all sites.

    Returns:
        Dict with 'scored', 'auto_approved', 'unreviewed', 'flagged' counts.
    """
    run_id = start_pipeline_run(conn, "scoring")
    stats = {"scored": 0, "auto_approved": 0, "unreviewed": 0, "flagged": 0}

    sites = [dict(row) for row in conn.execute("SELECT * FROM sites").fetchall()]

    for site in sites:
        score, factors = calculate_confidence(conn, site)

        if score >= SCORE_AUTO_APPROVE:
            review_status = "auto_approved"
            stats["auto_approved"] += 1
        elif score >= SCORE_FLAG_REVIEW:
            review_status = "unreviewed"
            stats["unreviewed"] += 1
        else:
            review_status = "flagged"
            stats["flagged"] += 1

        # Priority: lower score = higher priority (1 = most urgent)
        priority = int((1.0 - score) * 100)

        update_site(conn, site["id"], {
            "confidence_score": score,
            "review_status": review_status,
            "review_priority": priority,
        })
        stats["scored"] += 1

    conn.commit()
    complete_pipeline_run(conn, run_id, stats["scored"])
    logger.info("Scoring complete: %s", stats)
    return stats
