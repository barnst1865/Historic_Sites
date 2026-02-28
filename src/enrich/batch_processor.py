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

from config.settings import (
    ENRICHMENT_BATCH_SIZE_POOR,
    ENRICHMENT_BATCH_SIZE_RICH,
    ENRICHMENT_DESCRIPTION_RICH_THRESHOLD,
)
from src.db.queries import (
    complete_pipeline_run,
    get_sites_for_enrichment,
    start_pipeline_run,
    update_site,
)
from src.enrich.claude_classifier import (
    classify_with_claude,
    derive_eras_from_periods,
    derive_events_from_areas,
    store_classifications,
)

logger = logging.getLogger(__name__)


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


def enrich_batch(
    conn: sqlite3.Connection,
    sites: list[dict],
    batch_size: int,
) -> dict:
    """Enrich a batch of sites.

    Returns:
        Dict with 'enriched', 'failed' counts.
    """
    stats = {"enriched": 0, "failed": 0, "nrhp_derived": 0}

    for i in range(0, len(sites), batch_size):
        batch = sites[i:i + batch_size]
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
            for result in results:
                site_id = result.get("site_id")
                if site_id:
                    store_classifications(conn, site_id, result)
                    update_site(conn, site_id, {
                        "enrichment_status": "complete",
                        "enrichment_raw_json": json.dumps(result, default=str),
                    })
                    stats["enriched"] += 1
        else:
            # AI call failed — still mark NRHP-derived data as partial enrichment
            for site in batch:
                update_site(conn, site["id"], {"enrichment_status": "partial"})
                stats["failed"] += 1

        conn.commit()

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

    logger.info("Enriching %d sites", len(sites))

    # Split by data richness
    rich_sites = [s for s in sites if _is_data_rich(s)]
    poor_sites = [s for s in sites if not _is_data_rich(s)]
    logger.info(
        "Data-rich: %d (batched %d/call), Data-poor: %d (individual)",
        len(rich_sites), ENRICHMENT_BATCH_SIZE_RICH, len(poor_sites),
    )

    total_stats = {"total": len(sites), "enriched": 0, "failed": 0, "nrhp_derived": 0}

    # Enrich data-rich sites in larger batches
    if rich_sites:
        stats = enrich_batch(conn, rich_sites, ENRICHMENT_BATCH_SIZE_RICH)
        for k in ("enriched", "failed", "nrhp_derived"):
            total_stats[k] += stats[k]

    # Enrich data-poor sites individually
    if poor_sites:
        stats = enrich_batch(conn, poor_sites, ENRICHMENT_BATCH_SIZE_POOR)
        for k in ("enriched", "failed", "nrhp_derived"):
            total_stats[k] += stats[k]

    complete_pipeline_run(conn, run_id, total_stats["enriched"])
    logger.info("Enrichment complete: %s", total_stats)
    return total_stats
