"""
Audit fuzzy matches across all SHPO states.

Replays the matching logic for every SHPO source against the current database
and flags potential false positives — cases where two differently-named sites
may have been incorrectly merged via fuzzy matching. Exact matches (same name,
NRIS refnum, or address) are excluded since those are high-confidence.

Output: output/fuzzy_match_audit.csv

Columns:
  source_key, state, incoming_name, incoming_city, incoming_address,
  incoming_refnum, matched_name, matched_city, matched_address, matched_id,
  score, distance_km, match_type, would_match, risk
"""

import csv
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import (
    FUZZY_MATCH_CANDIDATE,
    FUZZY_NAME_ONLY_THRESHOLD,
    OUTPUT_DIR,
)
from config.state_sources import STATE_SOURCES
from src.db.connection import db_connection
from src.ingest.shpo_dispatcher import fetch_state, parse_state
from src.ingest.validator import SpatialIndex, find_fuzzy_matches, validate_site

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _normalize_for_comparison(name: str) -> str:
    """Normalize a name for exact-duplicate detection."""
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9\s]", "", name)
    return re.sub(r"\s+", " ", name).strip()


def _assess_risk(incoming_name, matched_name, score, distance_km, match_type, incoming_city,
                 matched_city):
    """Classify risk level of a fuzzy match."""
    # Different cities with no proximity data is highest risk
    city_mismatch = (
        incoming_city and matched_city
        and incoming_city.lower().strip() != matched_city.lower().strip()
    )

    if match_type == "name_only_match" and city_mismatch:
        return "HIGH"
    if match_type == "name_only_match" and distance_km is None:
        return "HIGH" if score < 95 else "MEDIUM"
    if match_type == "proximity_match" and score < 80:
        return "MEDIUM"
    if city_mismatch and distance_km is not None and distance_km > 0.3:
        return "MEDIUM"
    if score < 85:
        return "MEDIUM"
    return "LOW"


def load_existing_sites(conn, state_code):
    """Load existing sites for a state from the database."""
    return [
        dict(row)
        for row in conn.execute(
            "SELECT id, name, latitude, longitude, address, city"
            " FROM sites WHERE state = ?",
            (state_code,),
        ).fetchall()
    ]


def audit_source(conn, source_key, writer, stats):
    """Replay matching for a single source and write suspicious fuzzy matches to CSV."""
    config = STATE_SOURCES[source_key].copy()
    config["_source_key"] = source_key
    config["_state_code"] = config.get("state_code", source_key.split("_")[0])
    state_code = config["_state_code"]

    # Skip multi-state national dataset — too large and matches are all proximity-based
    if config.get("multi_state"):
        logger.info("[AUDIT] Skipping multi-state source: %s", source_key)
        return

    logger.info("[AUDIT] Processing %s (state=%s)...", source_key, state_code)

    # Fetch and parse using cached data
    try:
        raw = fetch_state(source_key, use_cache=True)
        sites = parse_state(source_key, raw)
    except Exception:
        logger.exception("[AUDIT] Failed to load/parse %s", source_key)
        return

    # Load existing sites and build spatial index
    existing = load_existing_sites(conn, state_code)
    spatial_idx = SpatialIndex()
    for site in existing:
        spatial_idx.add(site)

    # Build lookup for existing sites by ID for detail retrieval
    existing_by_id = {s["id"]: s for s in existing}

    # Also load NRIS refnums to identify refnum matches (which we skip)
    refnum_set = set()
    for row in conn.execute(
        "SELECT nris_refnum FROM sites WHERE state = ? AND nris_refnum IS NOT NULL",
        (state_code,),
    ):
        refnum_set.add(row[0])

    fuzzy_count = 0
    skipped_exact = 0
    for site_data in sites:
        result = validate_site(site_data)
        site_data = result["site_data"]

        # Skip if this would be an NRIS refnum match
        refnum = site_data.get("nris_refnum")
        if refnum and refnum in refnum_set:
            continue

        name = site_data.get("name", "")
        if not name:
            continue

        matches = find_fuzzy_matches(
            name,
            site_data.get("latitude"),
            site_data.get("longitude"),
            existing,
            spatial_index=spatial_idx,
        )

        if not matches:
            continue

        best = matches[0]

        # Skip if score is below candidate threshold
        if best["score"] < FUZZY_MATCH_CANDIDATE:
            continue

        # Skip exact name matches (score 100 or normalized names identical)
        # These are self-matches or true duplicates, not false positives
        if best["score"] == 100:
            skipped_exact += 1
            continue
        incoming_norm = _normalize_for_comparison(name)
        matched_norm = _normalize_for_comparison(best.get("name", ""))
        if incoming_norm == matched_norm:
            skipped_exact += 1
            continue

        matched_site = existing_by_id.get(best["site_id"], {})

        distance = best.get("distance_km")
        incoming_city = site_data.get("city")
        matched_city = matched_site.get("city")

        risk = _assess_risk(
            name, best.get("name"), best["score"], distance,
            best["match_type"], incoming_city, matched_city,
        )

        writer.writerow({
            "source_key": source_key,
            "state": state_code,
            "incoming_name": name,
            "incoming_city": incoming_city,
            "incoming_address": site_data.get("address"),
            "incoming_refnum": refnum,
            "matched_name": best.get("name"),
            "matched_city": matched_city,
            "matched_address": matched_site.get("address"),
            "matched_id": best.get("site_id"),
            "score": best.get("score"),
            "distance_km": (
                f"{distance:.3f}" if distance is not None else ""
            ),
            "match_type": best.get("match_type"),
            "would_match": (
                "YES" if best["match_type"] == "proximity_match"
                else "YES" if (
                    best["match_type"] == "name_only_match"
                    and best["score"] >= FUZZY_NAME_ONLY_THRESHOLD
                )
                else "CANDIDATE"
            ),
            "risk": risk,
        })
        fuzzy_count += 1

    stats[source_key] = {
        "state": state_code, "records": len(sites),
        "fuzzy_flagged": fuzzy_count, "exact_skipped": skipped_exact,
    }
    logger.info(
        "[AUDIT] %s: %d records, %d exact skipped, %d fuzzy flagged",
        source_key, len(sites), skipped_exact, fuzzy_count,
    )


def main():
    output_file = OUTPUT_DIR / "fuzzy_match_audit.csv"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "risk", "source_key", "state",
        "incoming_name", "incoming_city", "incoming_address", "incoming_refnum",
        "matched_name", "matched_city", "matched_address", "matched_id",
        "score", "distance_km", "match_type", "would_match",
    ]

    active_sources = [
        key for key, cfg in STATE_SOURCES.items()
        if cfg.get("active", False)
    ]

    stats = {}

    with (
        db_connection() as conn,
        open(output_file, "w", newline="", encoding="utf-8") as f,
    ):
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for source_key in sorted(active_sources):
            audit_source(conn, source_key, writer, stats)

    # Print summary
    logger.info("=" * 60)
    logger.info("AUDIT SUMMARY")
    logger.info("=" * 60)
    total_flagged = 0
    for key in sorted(stats):
        s = stats[key]
        logger.info(
            "  %-15s  state=%-2s  records=%6d  exact=%5d  flagged=%5d",
            key, s["state"], s["records"], s["exact_skipped"], s["fuzzy_flagged"],
        )
        total_flagged += s["fuzzy_flagged"]
    logger.info("-" * 60)
    logger.info("  Total fuzzy matches to review: %d", total_flagged)
    logger.info("  Output: %s", output_file)


if __name__ == "__main__":
    main()
