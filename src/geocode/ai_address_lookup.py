"""
Tier 2 geocoding: AI-assisted address and coordinate lookup.

Uses Claude CLI with web search to find street addresses and coordinates
for National Historic Landmarks that Nominatim couldn't precisely locate.

Follows the same batching, circuit-breaker, and progress patterns as
src/enrich/batch_processor.py.
"""

import json
import logging
import sqlite3
import time

from config.settings import ENRICHMENT_MAX_CONSECUTIVE_FAILURES
from src.claude_cli import call_claude
from src.db.queries import (
    add_site_source,
    complete_pipeline_run,
    get_sites_for_ai_geocoding,
    start_pipeline_run,
    update_pipeline_run_progress,
    update_site,
)
from src.geocode.prompt_templates import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from src.ingest.validator import validate_coordinates

logger = logging.getLogger(__name__)

AI_GEOCODE_BATCH_SIZE = 5  # Sites per Claude call
AI_GEOCODE_TIMEOUT = 120  # seconds


class CircuitBreakerTripped(Exception):
    """Raised when too many consecutive AI failures occur."""


def _format_elapsed(seconds: float) -> str:
    """Format seconds into human-readable elapsed time."""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def _build_sites_json(sites: list[dict]) -> str:
    """Build the JSON payload for the prompt."""
    items = []
    for site in sites:
        items.append({
            "site_id": site["id"],
            "name": site["name"],
            "city": site.get("city") or "",
            "county": site.get("county") or "",
            "state": site.get("state") or "",
        })
    return json.dumps(items, indent=2)


def _parse_ai_response(response_text: str) -> list[dict] | None:
    """Parse the JSON array from Claude's response.

    Handles responses that may include markdown fences or extra text.
    """
    if not response_text:
        return None

    text = response_text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last fence lines
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines)

    # Find the JSON array
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        logger.warning("No JSON array found in AI response")
        return None

    try:
        data = json.loads(text[start:end + 1])
        if not isinstance(data, list):
            return None
        return data
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse AI response JSON: %s", e)
        return None


def _apply_result(conn: sqlite3.Connection, site_id: int, result: dict) -> bool:
    """Validate and apply a single AI lookup result to the database.

    Returns True if coordinates were updated.
    """
    lat = result.get("latitude")
    lon = result.get("longitude")
    address = result.get("address")
    source_url = result.get("source_url")
    confidence = result.get("confidence", "low")

    # Must have at least coordinates
    if lat is None or lon is None:
        return False

    try:
        lat = float(lat)
        lon = float(lon)
    except (ValueError, TypeError):
        logger.warning("Invalid coordinates for site %d: lat=%s, lon=%s", site_id, lat, lon)
        return False

    coord_check = validate_coordinates(lat, lon)
    if not coord_check["valid"]:
        logger.warning(
            "AI coordinates failed validation for site %d: %s",
            site_id,
            coord_check["warnings"],
        )
        return False

    # Use possibly-corrected coordinates (e.g. swapped lat/lon)
    lat = coord_check["lat"]
    lon = coord_check["lon"]

    updates = {
        "latitude": lat,
        "longitude": lon,
        "coordinates_source": "ai_lookup",
        "geocode_quality": "ai_lookup",
    }
    if address:
        updates["address"] = address.strip()

    update_site(conn, site_id, updates)

    # Record provenance
    if source_url:
        add_site_source(conn, site_id, {
            "source_name": "ai_geocode",
            "source_url": source_url,
            "raw_data": {
                "confidence": confidence,
                "method": "claude_web_search",
            },
        })

    return True


def lookup_addresses(
    conn: sqlite3.Connection,
    limit: int | None = None,
) -> dict:
    """Run AI-assisted address lookup on sites needing better geocoding.

    Args:
        conn: Database connection.
        limit: Max sites to process (None for all).

    Returns:
        Dict with 'total', 'geocoded', 'failed', 'skipped' counts.
    """
    run_id = start_pipeline_run(conn, "ai_geocoding")
    stats = {"total": 0, "geocoded": 0, "failed": 0, "skipped": 0}

    try:
        sites = get_sites_for_ai_geocoding(conn)
        if limit:
            sites = sites[:limit]

        if not sites:
            logger.info("No sites need AI geocoding")
            complete_pipeline_run(conn, run_id, 0)
            return stats

        stats["total"] = len(sites)
        total_batches = (len(sites) + AI_GEOCODE_BATCH_SIZE - 1) // AI_GEOCODE_BATCH_SIZE
        consecutive_failures = 0
        start_time = time.monotonic()

        logger.info(
            "AI geocoding %d sites in %d batches (%d sites/batch)",
            len(sites),
            total_batches,
            AI_GEOCODE_BATCH_SIZE,
        )

        for i in range(0, len(sites), AI_GEOCODE_BATCH_SIZE):
            batch = sites[i:i + AI_GEOCODE_BATCH_SIZE]
            batch_num = i // AI_GEOCODE_BATCH_SIZE + 1
            site_names = [s.get("name", f"id={s['id']}") for s in batch]

            logger.info(
                "AI batch %d/%d: looking up %d site(s): %s",
                batch_num,
                total_batches,
                len(batch),
                ", ".join(site_names[:3]) + ("..." if len(site_names) > 3 else ""),
            )

            # Build prompt
            sites_json = _build_sites_json(batch)
            prompt = USER_PROMPT_TEMPLATE.format(sites_json=sites_json)

            # Call Claude
            response = call_claude(
                prompt,
                system_prompt=SYSTEM_PROMPT,
                model="sonnet",
                timeout=AI_GEOCODE_TIMEOUT,
            )

            results = _parse_ai_response(response)

            if results:
                consecutive_failures = 0
                batch_geocoded = 0

                # Index results by site_id for lookup
                results_by_id = {}
                for r in results:
                    sid = r.get("site_id")
                    if sid is not None:
                        results_by_id[int(sid)] = r

                for site in batch:
                    result = results_by_id.get(site["id"])
                    if result and _apply_result(conn, site["id"], result):
                        batch_geocoded += 1
                        stats["geocoded"] += 1
                    else:
                        stats["skipped"] += 1

                logger.info(
                    "AI batch %d/%d: %d/%d geocoded",
                    batch_num,
                    total_batches,
                    batch_geocoded,
                    len(batch),
                )
            else:
                consecutive_failures += 1
                stats["failed"] += len(batch)
                logger.warning(
                    "AI batch %d/%d: Claude call failed (consecutive: %d)",
                    batch_num,
                    total_batches,
                    consecutive_failures,
                )

            # Commit after each batch
            conn.commit()

            # Update pipeline progress
            update_pipeline_run_progress(
                conn, run_id, stats["geocoded"]
            )
            conn.commit()

            # Circuit breaker
            if consecutive_failures >= ENRICHMENT_MAX_CONSECUTIVE_FAILURES:
                raise CircuitBreakerTripped(
                    f"{consecutive_failures} consecutive AI failures — aborting. "
                    "Check Claude CLI connectivity and logs."
                )

            # Progress summary every 5 batches
            if batch_num % 5 == 0 or batch_num == total_batches:
                elapsed = time.monotonic() - start_time
                avg_per_batch = elapsed / batch_num
                remaining = (total_batches - batch_num) * avg_per_batch
                logger.info(
                    "AI geocoding progress: %d/%d batches | "
                    "geocoded=%d, failed=%d, skipped=%d | "
                    "Elapsed: %s | ETA: %s",
                    batch_num,
                    total_batches,
                    stats["geocoded"],
                    stats["failed"],
                    stats["skipped"],
                    _format_elapsed(elapsed),
                    _format_elapsed(remaining),
                )

        complete_pipeline_run(conn, run_id, stats["geocoded"])
        logger.info("AI geocoding complete: %s", stats)

    except CircuitBreakerTripped as e:
        logger.error("CIRCUIT BREAKER: %s", e)
        complete_pipeline_run(
            conn, run_id, stats["geocoded"],
            status="failed", error_message=str(e),
        )
    except Exception as e:
        logger.error("AI geocoding crashed: %s: %s", type(e).__name__, e)
        complete_pipeline_run(
            conn, run_id, stats["geocoded"],
            status="failed", error_message=f"{type(e).__name__}: {e}",
        )
        raise

    return stats
