"""
CSV exporter for review queue and general data export.
"""

import csv
import logging
import sqlite3
from pathlib import Path

from config.settings import OUTPUT_DIR

logger = logging.getLogger(__name__)


def export_review_csv(conn: sqlite3.Connection) -> Path:
    """Export flagged sites as CSV for spreadsheet review.

    Returns:
        Path to the saved CSV file.
    """
    filepath = OUTPUT_DIR / "review" / "review_queue.csv"
    filepath.parent.mkdir(parents=True, exist_ok=True)

    sites = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM sites WHERE review_status = 'flagged' "
            "ORDER BY review_priority ASC, confidence_score ASC"
        ).fetchall()
    ]

    if not sites:
        logger.info("No flagged sites to export")
        return filepath

    fields = [
        "id", "name", "state", "city", "nris_refnum",
        "confidence_score", "review_priority", "review_status",
        "reviewer_notes", "latitude", "longitude",
        "short_description", "condition", "public_access",
    ]

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for site in sites:
            writer.writerow(site)

    logger.info("Exported %d flagged sites to %s", len(sites), filepath)
    return filepath


def export_full_csv(conn: sqlite3.Connection) -> Path:
    """Export all sites as CSV for general use.

    Returns:
        Path to the saved CSV file.
    """
    filepath = OUTPUT_DIR / "all_sites.csv"
    filepath.parent.mkdir(parents=True, exist_ok=True)

    sites = [
        dict(row)
        for row in conn.execute("SELECT * FROM sites ORDER BY state, name").fetchall()
    ]

    if not sites:
        logger.info("No sites to export")
        return filepath

    fields = list(sites[0].keys())

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for site in sites:
            writer.writerow(site)

    logger.info("Exported %d sites to %s", len(sites), filepath)
    return filepath
