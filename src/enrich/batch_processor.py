"""
Batch orchestration for AI enrichment.

Routes sites through enrichment based on data richness:
  - Data-rich sites: batched 5-10 per Claude call
  - Data-poor sites: processed individually for better accuracy

First derives categories from NRHP data, then AI fills gaps.
Resume-capable: skips already-enriched sites.
"""

import json
import logging
import sqlite3
import time

from config.settings import (
    ENRICHMENT_BATCH_SIZE_POOR,
    ENRICHMENT_BATCH_SIZE_RICH,
    ENRICHMENT_DESCRIPTION_RICH_THRESHOLD,
    ENRICHMENT_MAX_CONSECUTIVE_FAILURES,
)
from src.db.queries import (
    complete_pipeline_run,
    get_sites_for_enrichment,
    start_pipeline_run,
    update_pipeline_run_progress,
    update_site,
)
from src.enrich.claude_classifier import (
    classify_with_claude,
    derive_eras_from_periods,
    derive_events_from_areas,
    store_classifications,
)

logger = logging.getLogger(__name__)


class CircuitBreakerTripped(Exception):
    """Raised when too many consecutive AI failures occur."""


def _is_data_rich(site: dict) -> bool:
    """Determine if a site has enough data for batched enrichment."""
    desc = site.get("full_description") or site.get("short_description") or ""
    return len(desc.split()) >= ENRICHMENT_DESCRIPTION_RICH_THRESHOLD


def _prepare_site_for_classification(site: dict) -> dict:
    """Extract relevant fields for the classification prompt."""
    return {
        "site_id": site["id"],
        "name": site["name"],
        "state": site.get("state"),
        "city": site.get("city"),
        "county": site.get("county"),
        "description": site.get("full_description") or site.get("short_description") or "",
        "date_constructed": site.get("date_constructed"),
        "nhl_designation_date": site.get("nhl_designation_date"),
    }


def _format_elapsed(seconds: float) -> str:
    """Format seconds into human-readable elapsed time."""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def enrich_batch(
    conn: sqlite3.Connection,
    sites: list[dict],
    batch_size: int,
    label: str = "",
    run_id: int | None = None,
    cumulative_enriched: int = 0,
) -> dict:
    """Enrich a batch of sites with progress logging and circuit breaker.

    Args:
        conn: Database connection.
        sites: List of site dicts to enrich.
        batch_size: Number of sites per Claude CLI call.
        label: Human-readable label for logging (e.g. "data-rich").
        run_id: Pipeline run ID for incremental progress updates.
        cumulative_enriched: Running count of previously enriched sites in this run.

    Returns:
        Dict with 'enriched', 'failed', 'nrhp_derived' counts.
    """
    stats = {"enriched": 0, "failed": 0, "nrhp_derived": 0}
    total_batches = (len(sites) + batch_size - 1) // batch_size
    consecutive_failures = 0
    start_time = time.monotonic()

    for i in range(0, len(sites), batch_size):
        batch = sites[i:i + batch_size]
        batch_num = i // batch_size + 1
        site_names = [s.get("name", f"id={s['id']}") for s in batch]

        logger.info(
            "[%s] Batch %d/%d: enriching %d site(s): %s",
            label,
            batch_num,
            total_batches,
            len(batch),
            ", ".join(site_names[:3]) + ("..." if len(site_names) > 3 else ""),
        )

        batch_data = []
        batch_derived = []

        for site in batch:
            site_id = site["id"]

            # Step 1: Derive from NRHP data
            derived_eras = derive_eras_from_periods(conn, site_id)
            derived_events = derive_events_from_areas(conn, site_id)

            if derived_eras or derived_events:
                # Store NRHP-derived categories
                store_classifications(conn, site_id, {
                    "eras": derived_eras,
                    "event_natures": derived_events,
                })
                stats["nrhp_derived"] += 1

            batch_data.append(_prepare_site_for_classification(site))
            batch_derived.append({
                "site_id": site_id,
                "derived_eras": derived_eras,
                "derived_events": derived_events,
            })

        # Step 2: AI classification for gaps
        results = classify_with_claude(batch_data, batch_derived)

        if results:
            consecutive_failures = 0
            for result in results:
                site_id = result.get("site_id")
                if site_id:
                    store_classifications(conn, site_id, result)
                    update_site(conn, site_id, {
                        "enrichment_status": "complete",
                        "enrichment_raw_json": json.dumps(result, default=str),
                    })
                    stats["enriched"] += 1
            logger.info(
                "[%s] Batch %d/%d: %d enriched",
                label, batch_num, total_batches, len(batch),
            )
        else:
            consecutive_failures += 1
            # AI call failed — still mark NRHP-derived data as partial enrichment
            for site in batch:
                update_site(conn, site["id"], {"enrichment_status": "partial"})
                stats["failed"] += 1
            logger.warning(
                "[%s] Batch %d/%d: AI classification failed for %d site(s) "
                "(consecutive failures: %d)",
                label, batch_num, total_batches, len(batch), consecutive_failures,
            )

        conn.commit()

        # Update pipeline run progress incrementally
        if run_id is not None:
            update_pipeline_run_progress(
                conn, run_id, cumulative_enriched + stats["enriched"]
            )
            conn.commit()

        # Circuit breaker
        if consecutive_failures >= ENRICHMENT_MAX_CONSECUTIVE_FAILURES:
            raise CircuitBreakerTripped(
                f"{consecutive_failures} consecutive AI failures — aborting enrichment. "
                "Check Claude CLI connectivity and logs."
            )

        # Progress summary every 10 batches
        if batch_num % 10 == 0 or batch_num == total_batches:
            elapsed = time.monotonic() - start_time
            avg_per_batch = elapsed / batch_num
            remaining = (total_batches - batch_num) * avg_per_batch
            logger.info(
                "[%s] Progress: %d/%d batches | %d enriched, %d failed | "
                "Elapsed: %s | ETA: %s",
                label,
                batch_num,
                total_batches,
                stats["enriched"],
                stats["failed"],
                _format_elapsed(elapsed),
                _format_elapsed(remaining),
            )

    return stats


def run_enrichment(
    conn: sqlite3.Connection,
    limit: int | None = None,
    force: bool = False,
) -> dict:
    """Run the full enrichment pipeline.

    Args:
        conn: Database connection.
        limit: Max sites to enrich (None for all).
        force: If True, re-enrich already-enriched sites.

    Returns:
        Dict with 'total', 'enriched', 'failed', 'nrhp_derived' counts.
    """
    run_id = start_pipeline_run(conn, "enrichment")
    total_stats = {"total": 0, "enriched": 0, "failed": 0, "nrhp_derived": 0}

    try:
        if force:
            sites = [
                dict(row)
                for row in conn.execute("SELECT * FROM sites ORDER BY id").fetchall()
            ]
        else:
            sites = get_sites_for_enrichment(conn, limit)

        if not sites:
            logger.info("No sites need enrichment")
            complete_pipeline_run(conn, run_id, 0)
            return {"total": 0, "enriched": 0, "failed": 0, "nrhp_derived": 0}

        total_stats["total"] = len(sites)
        logger.info("Enriching %d sites", len(sites))

        # Split by data richness
        rich_sites = [s for s in sites if _is_data_rich(s)]
        poor_sites = [s for s in sites if not _is_data_rich(s)]
        logger.info(
            "Data-rich: %d (batched %d/call), Data-poor: %d (individual)",
            len(rich_sites), ENRICHMENT_BATCH_SIZE_RICH, len(poor_sites),
        )

        # Enrich data-rich sites in larger batches
        if rich_sites:
            stats = enrich_batch(
                conn, rich_sites, ENRICHMENT_BATCH_SIZE_RICH,
                label="rich", run_id=run_id,
            )
            for k in ("enriched", "failed", "nrhp_derived"):
                total_stats[k] += stats[k]

        # Enrich data-poor sites individually
        if poor_sites:
            stats = enrich_batch(
                conn, poor_sites, ENRICHMENT_BATCH_SIZE_POOR,
                label="poor", run_id=run_id,
                cumulative_enriched=total_stats["enriched"],
            )
            for k in ("enriched", "failed", "nrhp_derived"):
                total_stats[k] += stats[k]

        complete_pipeline_run(conn, run_id, total_stats["enriched"])
        logger.info("Enrichment complete: %s", total_stats)

    except CircuitBreakerTripped as e:
        logger.error("CIRCUIT BREAKER: %s", e)
        complete_pipeline_run(
            conn, run_id, total_stats["enriched"],
            status="failed", error_message=str(e),
        )
    except Exception as e:
        logger.error("Enrichment crashed: %s: %s", type(e).__name__, e)
        complete_pipeline_run(
            conn, run_id, total_stats["enriched"],
            status="failed", error_message=f"{type(e).__name__}: {e}",
        )
        raise

    return total_stats
