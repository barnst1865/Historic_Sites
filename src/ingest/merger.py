"""
Cross-source deduplication and merge engine.

Merges records from multiple data sources into the sites table using
idempotent upsert logic. Keyed by nris_refnum for federal records,
with fuzzy name + geographic proximity matching as fallback.

Key behaviors:
  - Never overwrites fields where source = 'manual'
  - Change detection via SHA256 checksums — only processes changed records
  - Source priority determines which value wins for each field group
  - All source contributions tracked in site_sources table
"""

import logging
import sqlite3

from config.settings import FIELD_PRIORITY, FUZZY_MATCH_CANDIDATE, FUZZY_MATCH_THRESHOLD
from src.db.queries import (
    add_designation,
    add_nrhp_area,
    add_nrhp_criterion,
    add_site_source,
    complete_pipeline_run,
    get_site_by_refnum,
    start_pipeline_run,
    update_source_metadata,
    upsert_site,
)
from src.ingest.validator import find_fuzzy_matches, validate_site

logger = logging.getLogger(__name__)


def _should_update_field(
    field_group: str,
    new_source: str,
    existing_source: str | None,
) -> bool:
    """Determine if a new source value should override the existing one.

    Manual sources always win. Otherwise, use FIELD_PRIORITY ordering.
    """
    if existing_source == "manual":
        return False
    if new_source == "manual":
        return True

    priority = FIELD_PRIORITY.get(field_group)
    if not priority:
        return True  # No priority defined — accept new value

    new_rank = priority.index(new_source) if new_source in priority else len(priority)
    existing_rank = (
        priority.index(existing_source) if existing_source in priority else len(priority)
    )
    return new_rank <= existing_rank


def merge_arcgis_records(
    conn: sqlite3.Connection, sites: list[dict], source_name: str = "arcgis"
) -> dict:
    """Merge ArcGIS-parsed site records into the database.

    Returns:
        Dict with 'inserted', 'updated', 'skipped' counts.
    """
    run_id = start_pipeline_run(conn, f"merge_{source_name}")
    stats = {"inserted": 0, "updated": 0, "skipped": 0}

    for site_data in sites:
        result = validate_site(site_data)
        site_data = result["site_data"]

        refnum = site_data.get("nris_refnum")
        existing = get_site_by_refnum(conn, refnum) if refnum else None

        if existing:
            site_id = existing["id"]
            stats["updated"] += 1
        else:
            site_id = None
            stats["inserted"] += 1

        site_id = upsert_site(conn, site_data)

        # Track source contribution
        add_site_source(conn, site_id, {
            "source_name": source_name,
            "source_record_id": refnum,
            "raw_data": site_data,
        })

    conn.commit()
    update_source_metadata(conn, source_name, stats["inserted"] + stats["updated"])
    complete_pipeline_run(conn, run_id, sum(stats.values()))
    logger.info("Merge %s: %s", source_name, stats)
    return stats


def merge_spreadsheet_records(
    conn: sqlite3.Connection, records: list[dict], source_name: str = "nhl_spreadsheet"
) -> dict:
    """Merge spreadsheet-parsed records into the database.

    Each record dict has 'site_data', 'criteria', 'areas', 'designation', 'raw_row' keys.

    Returns:
        Dict with 'inserted', 'updated', 'skipped' counts.
    """
    run_id = start_pipeline_run(conn, f"merge_{source_name}")
    stats = {"inserted": 0, "updated": 0, "skipped": 0}

    for record in records:
        site_data = record["site_data"]
        result = validate_site(site_data)
        site_data = result["site_data"]

        refnum = site_data.get("nris_refnum")
        existing = get_site_by_refnum(conn, refnum) if refnum else None

        if existing:
            stats["updated"] += 1
        else:
            stats["inserted"] += 1

        site_id = upsert_site(conn, site_data)

        # Add NRHP criteria
        for criterion in record.get("criteria", []):
            add_nrhp_criterion(conn, site_id, criterion, source_name)

        # Add areas of significance
        for area_slug in record.get("areas", []):
            add_nrhp_area(conn, site_id, area_slug, source_name)

        # Add designation
        if record.get("designation"):
            add_designation(conn, site_id, record["designation"])

        # Track source
        add_site_source(conn, site_id, {
            "source_name": source_name,
            "source_record_id": refnum,
            "raw_data": record.get("raw_row"),
        })

    conn.commit()
    update_source_metadata(conn, source_name, stats["inserted"] + stats["updated"])
    complete_pipeline_run(conn, run_id, sum(stats.values()))
    logger.info("Merge %s: %s", source_name, stats)
    return stats


def merge_nps_parks_records(
    conn: sqlite3.Connection, sites: list[dict], source_name: str = "nps_parks"
) -> dict:
    """Merge NPS Parks API records into the database.

    NPS Parks records lack nris_refnum, so matching is done by fuzzy name.

    Returns:
        Dict with 'inserted', 'updated', 'skipped', 'matched' counts.
    """
    run_id = start_pipeline_run(conn, f"merge_{source_name}")
    stats = {"inserted": 0, "updated": 0, "skipped": 0, "matched": 0}

    # Load existing sites for fuzzy matching
    existing = [
        dict(row) for row in conn.execute(
            "SELECT id, name, latitude, longitude FROM sites"
        ).fetchall()
    ]

    for site_data in sites:
        result = validate_site(site_data)
        site_data = result["site_data"]

        # Try fuzzy match against existing records
        matches = find_fuzzy_matches(
            site_data.get("name", ""),
            site_data.get("latitude"),
            site_data.get("longitude"),
            existing,
        )

        if matches and matches[0]["score"] >= 85:
            # Match found — update existing record with NPS Parks data
            matched_id = matches[0]["site_id"]
            # Only update description and visitor info fields (NPS Parks speciality)
            update_fields = {}
            for field in ("short_description", "full_description", "website_url",
                         "visiting_hours", "admission_info", "nps_park_code"):
                if site_data.get(field):
                    update_fields[field] = site_data[field]

            if update_fields:
                update_fields["source_nps_parks"] = True
                set_clause = ", ".join(f"{k} = ?" for k in update_fields)
                values = list(update_fields.values()) + [matched_id]
                conn.execute(
                    f"UPDATE sites SET {set_clause} WHERE id = ? AND "
                    "(reviewer_notes IS NULL OR primary_source != 'manual')",
                    values,
                )

            stats["matched"] += 1

            add_site_source(conn, matched_id, {
                "source_name": source_name,
                "source_record_id": site_data.get("nps_park_code"),
                "raw_data": site_data,
            })
        else:
            # No match — insert as new record
            site_id = upsert_site(conn, site_data)
            stats["inserted"] += 1

            add_site_source(conn, site_id, {
                "source_name": source_name,
                "source_record_id": site_data.get("nps_park_code"),
                "raw_data": site_data,
            })

            # Add to existing list for subsequent matching
            existing.append({
                "id": site_id,
                "name": site_data.get("name", ""),
                "latitude": site_data.get("latitude"),
                "longitude": site_data.get("longitude"),
            })

    conn.commit()
    update_source_metadata(conn, source_name, sum(stats.values()) - stats["skipped"])
    complete_pipeline_run(conn, run_id, sum(stats.values()))
    logger.info("Merge %s: %s", source_name, stats)
    return stats


def merge_shpo_records(
    conn: sqlite3.Connection,
    sites: list[dict],
    state_code: str,
    config: dict,
) -> dict:
    """Merge SHPO state records into the database.

    Three-pass matching:
      1. NRIS refnum match (if record has nris_refnum)
      2. Fuzzy name + geographic proximity match (scoped to same state)
      3. Insert as new record

    Matched sites get source_shpo=1 and NULL fields filled via COALESCE.
    Federal data is never overwritten. Designations are always added (additive).

    Returns:
        Dict with 'inserted', 'updated', 'matched_nris', 'matched_fuzzy', 'skipped' counts.
    """
    source_name = f"shpo_{state_code.lower()}"
    run_id = start_pipeline_run(conn, f"merge_{source_name}")
    stats = {
        "inserted": 0,
        "updated": 0,
        "matched_nris": 0,
        "matched_fuzzy": 0,
        "skipped": 0,
    }

    # Load existing sites in this state for fuzzy matching
    existing = [
        dict(row)
        for row in conn.execute(
            "SELECT id, name, latitude, longitude FROM sites WHERE state = ?",
            (state_code,),
        ).fetchall()
    ]

    for site_data in sites:
        result = validate_site(site_data)
        site_data = result["site_data"]

        site_id = None

        # Pass 1: NRIS refnum match
        refnum = site_data.get("nris_refnum")
        if refnum:
            existing_site = get_site_by_refnum(conn, refnum)
            if existing_site:
                site_id = existing_site["id"]
                stats["matched_nris"] += 1

        # Pass 2: Fuzzy name + proximity match
        if site_id is None:
            matches = find_fuzzy_matches(
                site_data.get("name", ""),
                site_data.get("latitude"),
                site_data.get("longitude"),
                existing,
            )
            if matches and matches[0]["score"] >= FUZZY_MATCH_THRESHOLD:
                site_id = matches[0]["site_id"]
                stats["matched_fuzzy"] += 1
            elif matches and matches[0]["score"] >= FUZZY_MATCH_CANDIDATE:
                logger.info(
                    "[SHPO] %s: Candidate match (score=%d): '%s' ~ '%s'",
                    state_code,
                    matches[0]["score"],
                    site_data.get("name"),
                    matches[0]["name"],
                )

        # Update matched site or insert new
        if site_id is not None:
            # Fill NULL fields — never overwrite existing federal data
            update_fields = {}
            for field in (
                "address", "city", "county", "date_constructed",
                "state_designation_date",
            ):
                if site_data.get(field):
                    update_fields[field] = site_data[field]

            update_fields["source_shpo"] = True

            if update_fields:
                # COALESCE: only fill fields that are currently NULL or empty
                set_parts = []
                values = []
                for k, v in update_fields.items():
                    if k == "source_shpo":
                        set_parts.append(f"{k} = ?")
                    else:
                        set_parts.append(f"{k} = COALESCE(NULLIF({k}, ''), ?)")
                    values.append(v)
                values.append(site_id)
                conn.execute(
                    f"UPDATE sites SET {', '.join(set_parts)} WHERE id = ? "
                    "AND primary_source != 'manual'",
                    values,
                )
            stats["updated"] += 1
        else:
            # Pass 3: Insert as new record
            # Remove state_record_id before insert (not a sites table column)
            insert_data = {
                k: v for k, v in site_data.items() if k != "state_record_id"
            }
            site_id = upsert_site(conn, insert_data)
            stats["inserted"] += 1

            # Add to existing list for subsequent fuzzy matching
            existing.append({
                "id": site_id,
                "name": site_data.get("name", ""),
                "latitude": site_data.get("latitude"),
                "longitude": site_data.get("longitude"),
            })

        # Always add designation (INSERT OR IGNORE — additive)
        for desig_type in config.get("designation_types", ["State Register"]):
            add_designation(conn, site_id, {
                "designation_type": desig_type,
                "designation_date": site_data.get("state_designation_date"),
                "designating_authority": config.get("designating_authority"),
                "source": source_name,
            })

        # Track provenance
        add_site_source(conn, site_id, {
            "source_name": source_name,
            "source_record_id": site_data.get("state_record_id") or refnum,
            "raw_data": site_data,
        })

    conn.commit()
    total_processed = sum(stats.values())
    update_source_metadata(conn, source_name, total_processed - stats["skipped"])
    complete_pipeline_run(conn, run_id, total_processed)
    logger.info("Merge %s: %s", source_name, stats)
    return stats
