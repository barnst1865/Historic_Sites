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

from config.settings import (
    FIELD_PRIORITY,
    FUZZY_MATCH_CANDIDATE,
    FUZZY_NAME_ONLY_THRESHOLD,
)
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
from src.ingest.validator import SpatialIndex, find_fuzzy_matches, validate_site

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


def _names_differ_only_by_number(name_a: str, name_b: str) -> bool:
    """Check if two names are identical except for a number.

    Catches false positives like 'Fire Station No. 25' vs 'Fire Station No. 7',
    'Comfort Station O-303' vs 'Comfort Station O-302', or
    'N 23rd Street Bridge' vs 'N 21st Street Bridge'.
    """
    import re

    # Match digit sequences and ordinals (1st, 2nd, 3rd, 4th, 21st, etc.)
    num_pattern = r"\d+(?:st|nd|rd|th)?\b"
    placeholder = "\x00"
    a_stripped = re.sub(num_pattern, placeholder, name_a.lower().strip())
    b_stripped = re.sub(num_pattern, placeholder, name_b.lower().strip())

    if a_stripped != b_stripped:
        return False

    # Same template — check if any numbers actually differ
    a_nums = re.findall(num_pattern, name_a.lower())
    b_nums = re.findall(num_pattern, name_b.lower())
    return a_nums != b_nums


def _normalize_address(addr: str) -> str:
    """Normalize an address for comparison (lowercase, strip punctuation)."""
    import re

    addr = addr.lower().strip()
    addr = re.sub(r"[.,#]", "", addr)
    # Common abbreviations
    for full, abbr in [
        ("street", "st"), ("avenue", "ave"), ("boulevard", "blvd"),
        ("drive", "dr"), ("road", "rd"), ("lane", "ln"),
        ("court", "ct"), ("place", "pl"), ("north", "n"),
        ("south", "s"), ("east", "e"), ("west", "w"),
    ]:
        addr = re.sub(rf"\b{full}\b", abbr, addr)
    return re.sub(r"\s+", " ", addr).strip()


def merge_shpo_records(
    conn: sqlite3.Connection,
    sites: list[dict],
    state_code: str,
    config: dict,
) -> dict:
    """Merge SHPO state records into the database.

    Five-pass matching:
      1. NRIS refnum match (if record has nris_refnum)
      2. Address + city match (if both records have address and city)
      3. Proximity + fuzzy name match (distance <= 0.5km AND score >= 70)
      4. Name-only match with strict threshold (score >= 90, no coords required)
      5. Insert as new record

    Matched sites get source_shpo=1 and NULL fields filled via COALESCE.
    Federal data is never overwritten. Designations are always added (additive).

    Returns:
        Dict with 'inserted', 'updated', 'matched_nris', 'matched_address',
        'matched_fuzzy', 'skipped' counts.
    """
    source_name = f"shpo_{state_code.lower()}"
    run_id = start_pipeline_run(conn, f"merge_{source_name}")
    stats = {
        "inserted": 0,
        "updated": 0,
        "matched_nris": 0,
        "matched_address": 0,
        "matched_fuzzy": 0,
        "skipped": 0,
    }

    # Load existing sites in this state for fuzzy matching
    existing = [
        dict(row)
        for row in conn.execute(
            "SELECT id, name, latitude, longitude, address, city"
            " FROM sites WHERE state = ?",
            (state_code,),
        ).fetchall()
    ]

    # Build spatial index for O(1) neighbor lookup instead of O(N) scan
    spatial_idx = SpatialIndex()
    for site in existing:
        spatial_idx.add(site)

    # Build address index for Pass 2
    addr_index: dict[str, list[dict]] = {}
    for site in existing:
        if site.get("address") and site.get("city"):
            key = _normalize_address(site["address"]) + "|" + site["city"].lower().strip()
            addr_index.setdefault(key, []).append(site)

    total_records = len(sites)
    for idx, site_data in enumerate(sites):
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

        # Pass 2: Address + city match
        if site_id is None and site_data.get("address") and site_data.get("city"):
            addr_key = (
                _normalize_address(site_data["address"])
                + "|" + site_data["city"].lower().strip()
            )
            addr_matches = addr_index.get(addr_key, [])
            if len(addr_matches) == 1:
                site_id = addr_matches[0]["id"]
                stats["matched_address"] += 1
            elif len(addr_matches) > 1:
                # Multiple sites at same address — use name as tiebreaker
                from rapidfuzz import fuzz

                best = max(
                    addr_matches,
                    key=lambda s: fuzz.token_sort_ratio(
                        site_data.get("name", ""), s.get("name", "")
                    ),
                )
                site_id = best["id"]
                stats["matched_address"] += 1

        # Pass 3: Proximity + fuzzy name match (requires coords)
        if site_id is None:
            matches = find_fuzzy_matches(
                site_data.get("name", ""),
                site_data.get("latitude"),
                site_data.get("longitude"),
                existing,
                spatial_index=spatial_idx,
            )
            incoming_name = site_data.get("name", "")

            # First try proximity matches (most reliable)
            proximity_matches = [
                m for m in matches
                if m["match_type"] == "proximity_match"
                and not _names_differ_only_by_number(incoming_name, m["name"])
            ]
            if proximity_matches:
                site_id = proximity_matches[0]["site_id"]
                stats["matched_fuzzy"] += 1
            else:
                # Pass 4: Name-only match with strict threshold
                # NEVER accept when cities differ or names differ only by number
                name_only = [
                    m for m in matches
                    if m["match_type"] == "name_only_match"
                    and m["score"] >= FUZZY_NAME_ONLY_THRESHOLD
                    and not _names_differ_only_by_number(incoming_name, m["name"])
                ]
                incoming_city = (site_data.get("city") or "").lower().strip()
                if name_only and incoming_city:
                    # Filter to same-city matches only
                    same_city = [
                        m for m in name_only
                        if m.get("city") and m["city"].lower().strip() == incoming_city
                    ]
                    if same_city:
                        site_id = same_city[0]["site_id"]
                        stats["matched_fuzzy"] += 1
                    # If matched city differs, reject — different city = different site
                elif name_only and not incoming_city:
                    # No city on incoming record — only accept if matched also
                    # lacks a city (both unknown) or score is very high
                    no_city_matches = [
                        m for m in name_only if not m.get("city")
                    ]
                    if no_city_matches:
                        site_id = no_city_matches[0]["site_id"]
                        stats["matched_fuzzy"] += 1
                    elif name_only[0]["score"] >= 95:
                        site_id = name_only[0]["site_id"]
                        stats["matched_fuzzy"] += 1

                # Log candidates that didn't match
                if site_id is None and matches and matches[0]["score"] >= FUZZY_MATCH_CANDIDATE:
                    logger.info(
                        "[SHPO] %s: Candidate match (score=%d, type=%s): '%s' ~ '%s'",
                        state_code,
                        matches[0]["score"],
                        matches[0]["match_type"],
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
            # Pass 5: Insert as new record
            # Remove state_record_id before insert (not a sites table column)
            insert_data = {
                k: v for k, v in site_data.items() if k != "state_record_id"
            }
            site_id = upsert_site(conn, insert_data)
            stats["inserted"] += 1

            # Add to existing list, spatial index, and address index
            new_entry = {
                "id": site_id,
                "name": site_data.get("name", ""),
                "latitude": site_data.get("latitude"),
                "longitude": site_data.get("longitude"),
                "address": site_data.get("address"),
                "city": site_data.get("city"),
            }
            existing.append(new_entry)
            spatial_idx.add(new_entry)
            if new_entry.get("address") and new_entry.get("city"):
                key = (
                    _normalize_address(new_entry["address"])
                    + "|" + new_entry["city"].lower().strip()
                )
                addr_index.setdefault(key, []).append(new_entry)

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

        # Progress logging every 5,000 records + periodic commits every 10,000
        processed = idx + 1
        if processed % 5000 == 0 or processed == total_records:
            logger.info(
                "[SHPO] %s: %d/%d records merged "
                "(nris=%d, addr=%d, fuzzy=%d, inserted=%d, skipped=%d)",
                state_code,
                processed,
                total_records,
                stats["matched_nris"],
                stats["matched_address"],
                stats["matched_fuzzy"],
                stats["inserted"],
                stats["skipped"],
            )
        if processed % 10000 == 0:
            conn.commit()

    conn.commit()
    total_processed = sum(stats.values())
    update_source_metadata(conn, source_name, total_processed - stats["skipped"])
    complete_pipeline_run(conn, run_id, total_processed)
    logger.info("Merge %s: %s", source_name, stats)
    return stats
