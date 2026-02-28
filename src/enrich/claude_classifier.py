"""
Claude-based site classifier using structured outputs.

Sends site data to Claude for classification into our category system.
Maps NRHP data to our categories first, then AI fills gaps.
"""

import json
import logging
import sqlite3

from config.categories import ERA_YEAR_RANGES, NRHP_TO_EVENT_NATURE
from config.settings import ANTHROPIC_API_KEY, ENRICHMENT_MODEL
from src.enrich.prompt_templates import CLASSIFICATION_PROMPT, SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def derive_eras_from_periods(conn: sqlite3.Connection, site_id: int) -> list[dict]:
    """Map NRHP periods of significance to our historical eras.

    Returns:
        List of {'slug', 'rank', 'confidence', 'source'} dicts.
    """
    periods = conn.execute(
        "SELECT start_year, end_year FROM nrhp_periods_of_significance WHERE site_id = ?",
        (site_id,),
    ).fetchall()

    if not periods:
        return []

    eras = []
    for period in periods:
        start = period["start_year"]
        end = period["end_year"]
        if start is None and end is None:
            continue

        for era_slug, (era_start, era_end) in ERA_YEAR_RANGES.items():
            # Check if the period overlaps with this era
            period_start = start or 0
            period_end = end or 2026
            era_s = era_start or 0
            era_e = era_end or 2026

            if period_start <= era_e and period_end >= era_s:
                # Calculate how much of the period falls in this era
                overlap_start = max(period_start, era_s)
                overlap_end = min(period_end, era_e)
                total_span = period_end - period_start if period_end > period_start else 1
                overlap = max(0, overlap_end - overlap_start)
                fraction = overlap / total_span if total_span > 0 else 0

                if fraction > 0.1:  # At least 10% overlap
                    confidence = min(0.95, 0.6 + fraction * 0.35)
                    eras.append({
                        "slug": era_slug,
                        "confidence": round(confidence, 2),
                        "source": "nrhp_derived",
                    })

    # Sort by confidence descending and assign ranks
    eras.sort(key=lambda e: e["confidence"], reverse=True)
    for i, era in enumerate(eras[:3]):
        era["rank"] = i + 1

    return eras[:3]


def derive_events_from_areas(conn: sqlite3.Connection, site_id: int) -> list[dict]:
    """Map NRHP areas of significance to our event natures.

    Returns:
        List of {'slug', 'rank', 'confidence', 'source'} dicts.
    """
    areas = conn.execute(
        "SELECT area_slug FROM nrhp_areas_of_significance WHERE site_id = ?",
        (site_id,),
    ).fetchall()

    events = []
    seen = set()
    for area in areas:
        mapped = NRHP_TO_EVENT_NATURE.get(area["area_slug"])
        if mapped and mapped not in seen:
            seen.add(mapped)
            events.append({
                "slug": mapped,
                "confidence": 0.9,  # High confidence for direct NRHP mapping
                "source": "nrhp_derived",
            })

    # Assign ranks
    for i, event in enumerate(events[:3]):
        event["rank"] = i + 1

    return events[:3]


def classify_with_claude(
    sites_data: list[dict], nrhp_derived: list[dict] | None = None
) -> list[dict] | None:
    """Send sites to Claude for classification.

    Args:
        sites_data: List of site dicts with fields for classification.
        nrhp_derived: List of already-derived NRHP categories per site.

    Returns:
        List of classification result dicts, or None on failure.
    """
    if not ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set. Skipping AI classification.")
        return None

    import anthropic

    # Build the prompt
    sites_json = json.dumps(sites_data, indent=2, default=str)
    derived_json = json.dumps(nrhp_derived or [], indent=2, default=str)

    prompt = CLASSIFICATION_PROMPT.format(
        sites_json=sites_json,
        nrhp_derived=derived_json,
    )

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model=ENRICHMENT_MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = message.content[0].text

        # Extract JSON array from response
        json_start = response_text.find("[")
        json_end = response_text.rfind("]") + 1
        if json_start >= 0 and json_end > json_start:
            return json.loads(response_text[json_start:json_end])

    except json.JSONDecodeError as e:
        logger.warning("Failed to parse Claude classification response: %s", e)
    except Exception as e:
        logger.warning("Claude classification failed: %s", e)

    return None


def store_classifications(
    conn: sqlite3.Connection, site_id: int, classifications: dict
) -> None:
    """Store AI classification results in the database.

    Args:
        conn: Database connection.
        site_id: The site ID.
        classifications: Dict with 'eras', 'event_natures', 'site_types', 'ownership' lists.
    """
    from src.db.queries import add_site_category

    # Map category tables and their slug lookups
    category_tables = {
        "eras": ("site_eras", "historical_eras"),
        "event_natures": ("site_events", "event_natures"),
        "site_types": ("site_site_types", "site_types"),
        "ownership": ("site_ownership", "ownership_types"),
    }

    for key, (junction_table, dim_table) in category_tables.items():
        for item in classifications.get(key, []):
            slug = item.get("slug")
            if not slug:
                continue

            # Look up the dimension table ID
            row = conn.execute(
                f"SELECT id FROM {dim_table} WHERE slug = ?", (slug,)
            ).fetchone()
            if not row:
                logger.warning("Unknown %s slug: %s", dim_table, slug)
                continue

            add_site_category(
                conn,
                junction_table,
                site_id,
                row["id"],
                rank=item.get("rank", 1),
                confidence=item.get("confidence", 0.5),
                source=item.get("source", "ai"),
            )
