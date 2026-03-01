"""
Parameterized CRUD operations for the Historic Sites database.

All functions accept a sqlite3.Connection and use parameterized queries
to prevent SQL injection. The connection is managed by the caller
(typically via db_connection context manager).
"""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone


def _checksum(data: dict) -> str:
    """Generate SHA256 checksum from a dict for change detection."""
    serialized = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


# --- Sites ---


def upsert_site(conn: sqlite3.Connection, site_data: dict) -> int:
    """Insert or update a site record keyed by nris_refnum.

    If a record with the same nris_refnum exists, updates only fields
    that are NULL or not from a manual source. Returns the site ID.

    Args:
        conn: Database connection.
        site_data: Dict with column names as keys. Must include 'name'.

    Returns:
        The site ID (existing or newly created).
    """
    refnum = site_data.get("nris_refnum")
    checksum = _checksum(site_data)

    if refnum:
        existing = conn.execute(
            "SELECT id, data_checksum FROM sites WHERE nris_refnum = ?", (refnum,)
        ).fetchone()

        if existing:
            # Skip if data hasn't changed
            if existing["data_checksum"] == checksum:
                return existing["id"]

            # Update non-manual fields that are NULL or from lower-priority sources
            site_id = existing["id"]
            updates = []
            values = []
            for col, val in site_data.items():
                if col in ("nris_refnum", "id"):
                    continue
                if val is not None:
                    updates.append(f"{col} = COALESCE(NULLIF({col}, ''), ?)")
                    values.append(val)

            if updates:
                updates.append("updated_at = ?")
                values.append(datetime.now(timezone.utc).isoformat())
                updates.append("data_checksum = ?")
                values.append(checksum)
                values.append(site_id)
                conn.execute(
                    f"UPDATE sites SET {', '.join(updates)} WHERE id = ?",
                    values,
                )
            return site_id

    # Insert new record
    site_data["data_checksum"] = checksum
    site_data["created_at"] = datetime.now(timezone.utc).isoformat()
    site_data["updated_at"] = site_data["created_at"]

    columns = ", ".join(site_data.keys())
    placeholders = ", ".join(["?"] * len(site_data))
    cursor = conn.execute(
        f"INSERT INTO sites ({columns}) VALUES ({placeholders})",
        list(site_data.values()),
    )
    return cursor.lastrowid


def get_site_by_refnum(conn: sqlite3.Connection, nris_refnum: str) -> dict | None:
    """Fetch a site by NRIS reference number."""
    row = conn.execute(
        "SELECT * FROM sites WHERE nris_refnum = ?", (nris_refnum,)
    ).fetchone()
    return dict(row) if row else None


def get_site_by_id(conn: sqlite3.Connection, site_id: int) -> dict | None:
    """Fetch a site by primary key."""
    row = conn.execute("SELECT * FROM sites WHERE id = ?", (site_id,)).fetchone()
    return dict(row) if row else None


def get_sites_for_enrichment(
    conn: sqlite3.Connection, limit: int | None = None
) -> list[dict]:
    """Fetch sites that haven't been enriched yet."""
    sql = "SELECT * FROM sites WHERE enrichment_status = 'pending' ORDER BY id"
    if limit:
        sql += f" LIMIT {limit}"
    return [dict(row) for row in conn.execute(sql).fetchall()]


def get_sites_for_geocoding(conn: sqlite3.Connection) -> list[dict]:
    """Fetch sites that have an address but no coordinates."""
    return [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM sites WHERE latitude IS NULL AND address IS NOT NULL ORDER BY id"
        ).fetchall()
    ]


def get_sites_for_review(conn: sqlite3.Connection) -> list[dict]:
    """Fetch sites flagged for manual review, ordered by priority."""
    return [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM sites WHERE review_status = 'flagged' "
            "ORDER BY review_priority ASC, confidence_score ASC"
        ).fetchall()
    ]


def update_site(conn: sqlite3.Connection, site_id: int, updates: dict) -> None:
    """Update specific fields on a site record."""
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [site_id]
    conn.execute(f"UPDATE sites SET {set_clause} WHERE id = ?", values)


def count_sites(conn: sqlite3.Connection) -> int:
    """Return total number of sites."""
    return conn.execute("SELECT COUNT(*) FROM sites").fetchone()[0]


# --- Designations ---


def add_designation(conn: sqlite3.Connection, site_id: int, designation: dict) -> None:
    """Add a designation to a site (idempotent via UNIQUE constraint)."""
    conn.execute(
        "INSERT OR IGNORE INTO site_designations "
        "(site_id, designation_type, designation_date, designating_authority, source) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            site_id,
            designation["designation_type"],
            designation.get("designation_date"),
            designation.get("designating_authority"),
            designation.get("source"),
        ),
    )


# --- NRHP Classification ---


def add_nrhp_criterion(
    conn: sqlite3.Connection, site_id: int, criterion: str, source: str
) -> None:
    """Add an NRHP criterion (A-D) to a site."""
    conn.execute(
        "INSERT OR IGNORE INTO nrhp_criteria (site_id, criterion, source) VALUES (?, ?, ?)",
        (site_id, criterion, source),
    )


def add_nrhp_area(
    conn: sqlite3.Connection, site_id: int, area_slug: str, source: str
) -> None:
    """Add an NRHP area of significance to a site."""
    conn.execute(
        "INSERT OR IGNORE INTO nrhp_areas_of_significance (site_id, area_slug, source) "
        "VALUES (?, ?, ?)",
        (site_id, area_slug, source),
    )


def add_nrhp_period(
    conn: sqlite3.Connection,
    site_id: int,
    start_year: int | None,
    end_year: int | None,
    source: str,
) -> None:
    """Add a period of significance to a site."""
    conn.execute(
        "INSERT INTO nrhp_periods_of_significance (site_id, start_year, end_year, source) "
        "VALUES (?, ?, ?, ?)",
        (site_id, start_year, end_year, source),
    )


# --- Enrichment Categories ---


def add_site_category(
    conn: sqlite3.Connection,
    table: str,
    site_id: int,
    category_id: int,
    rank: int = 1,
    confidence: float = 1.0,
    source: str = "ai",
) -> None:
    """Add a category assignment to a site via a junction table.

    Args:
        table: One of 'site_eras', 'site_events', 'site_site_types', 'site_ownership'.
        category_id: ID in the corresponding dimension table.
    """
    fk_col = {
        "site_eras": "era_id",
        "site_events": "event_id",
        "site_site_types": "type_id",
        "site_ownership": "ownership_id",
    }[table]

    conn.execute(
        f"INSERT OR IGNORE INTO {table} (site_id, {fk_col}, rank, confidence, source) "
        "VALUES (?, ?, ?, ?, ?)",
        (site_id, category_id, rank, confidence, source),
    )


# --- Site Sources ---


def add_site_source(conn: sqlite3.Connection, site_id: int, source_data: dict) -> None:
    """Record a source contribution for a site."""
    conn.execute(
        "INSERT INTO site_sources "
        "(site_id, source_name, source_record_id, source_url, date_fetched, raw_data_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            site_id,
            source_data["source_name"],
            source_data.get("source_record_id"),
            source_data.get("source_url"),
            datetime.now(timezone.utc).isoformat(),
            json.dumps(source_data.get("raw_data"), default=str)
            if source_data.get("raw_data")
            else None,
        ),
    )


# --- Site Relationships ---


def add_relationship(
    conn: sqlite3.Connection,
    site_id_a: int,
    site_id_b: int,
    rel_type: str,
    rel_name: str | None = None,
    notes: str | None = None,
) -> None:
    """Add a relationship between two sites."""
    conn.execute(
        "INSERT OR IGNORE INTO site_relationships "
        "(site_id_a, site_id_b, relationship_type, relationship_name, notes) "
        "VALUES (?, ?, ?, ?, ?)",
        (site_id_a, site_id_b, rel_type, rel_name, notes),
    )


# --- Pipeline Tracking ---


def start_pipeline_run(conn: sqlite3.Connection, stage: str) -> int:
    """Record the start of a pipeline run. Returns the run ID."""
    cursor = conn.execute(
        "INSERT INTO pipeline_runs (stage, status) VALUES (?, 'running')",
        (stage,),
    )
    conn.commit()
    return cursor.lastrowid


def complete_pipeline_run(
    conn: sqlite3.Connection,
    run_id: int,
    records_processed: int,
    status: str = "completed",
    error_message: str | None = None,
) -> None:
    """Record the completion of a pipeline run."""
    conn.execute(
        "UPDATE pipeline_runs SET completed_at = ?, records_processed = ?, "
        "status = ?, error_message = ? WHERE id = ?",
        (
            datetime.now(timezone.utc).isoformat(),
            records_processed,
            status,
            error_message,
            run_id,
        ),
    )


def update_pipeline_run_progress(
    conn: sqlite3.Connection,
    run_id: int,
    records_processed: int,
) -> None:
    """Update records_processed for a running pipeline without changing status."""
    conn.execute(
        "UPDATE pipeline_runs SET records_processed = ? WHERE id = ?",
        (records_processed, run_id),
    )


def update_source_metadata(
    conn: sqlite3.Connection,
    source_name: str,
    record_count: int,
    checksum: str | None = None,
) -> None:
    """Update metadata for a data source after fetch."""
    conn.execute(
        "INSERT OR REPLACE INTO data_source_metadata "
        "(source_name, last_fetch, record_count, checksum) VALUES (?, ?, ?, ?)",
        (source_name, datetime.now(timezone.utc).isoformat(), record_count, checksum),
    )
