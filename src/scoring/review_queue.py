"""
Review queue management.

Provides functions to query, display, and process the manual review queue.
"""

import logging
import sqlite3

from src.db.queries import get_sites_for_review, update_site

logger = logging.getLogger(__name__)


def get_review_queue(conn: sqlite3.Connection, limit: int | None = None) -> list[dict]:
    """Get the review queue sorted by priority.

    Args:
        conn: Database connection.
        limit: Max number of items to return.

    Returns:
        List of site dicts with review metadata.
    """
    sites = get_sites_for_review(conn)
    if limit:
        sites = sites[:limit]
    return sites


def get_review_stats(conn: sqlite3.Connection) -> dict:
    """Get review queue statistics."""
    rows = conn.execute(
        "SELECT review_status, COUNT(*) as cnt FROM sites GROUP BY review_status"
    ).fetchall()
    return {row["review_status"]: row["cnt"] for row in rows}


def approve_site(conn: sqlite3.Connection, site_id: int, notes: str | None = None) -> None:
    """Mark a site as manually approved."""
    updates = {"review_status": "approved"}
    if notes:
        updates["reviewer_notes"] = notes
    update_site(conn, site_id, updates)
    conn.commit()


def flag_site(
    conn: sqlite3.Connection, site_id: int, notes: str, priority: int = 1
) -> None:
    """Flag a site for further review."""
    update_site(conn, site_id, {
        "review_status": "flagged",
        "reviewer_notes": notes,
        "review_priority": priority,
    })
    conn.commit()


def update_review(
    conn: sqlite3.Connection, site_id: int, updates: dict
) -> None:
    """Apply manual review updates to a site.

    Sets primary_source to 'manual' for all updated fields.
    """
    updates["primary_source"] = "manual"
    update_site(conn, site_id, updates)
    conn.commit()
