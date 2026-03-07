"""
California OHP Listed Resources scraper.

Scrapes the Office of Historic Preservation's Listed Resources website
(ohp.parks.ca.gov) to build a statewide inventory of California Register
properties. Two-phase fetch: county listing pages, then individual detail pages.
"""

import json
import logging
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from config.settings import RAW_DIR

logger = logging.getLogger(__name__)

BASE_URL = "https://ohp.parks.ca.gov/listedresources"
COUNTY_URL = f"{BASE_URL}/?view=county&criteria="
DETAIL_URL = f"{BASE_URL}/Detail/"
NUM_COUNTIES = 58
COUNTY_RATE_LIMIT = 0.5  # seconds between county page requests
DETAIL_RATE_LIMIT = 0.3  # seconds between detail page requests
DETAIL_LOG_INTERVAL = 100
DETAIL_CHECKPOINT_INTERVAL = 500  # Save progress every N detail pages
REQUEST_TIMEOUT = 30


def _cache_path(source_key: str, suffix: str = "") -> Path:
    """Return cache file path for a given stage."""
    name = f"shpo_{source_key.lower()}{suffix}.json"
    return RAW_DIR / name


def _save_json(path: Path, data) -> None:
    """Write data to JSON file, ensuring parent directory exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def _load_json(path: Path):
    """Load data from a JSON file."""
    with open(path) as f:
        return json.load(f)


def fetch(config: dict, use_cache: bool = True) -> list[dict]:
    """Fetch all California OHP listed resources.

    Phase 1: Scrape county listing pages (58 requests)
    Phase 2: Scrape detail pages for each resource (~4K requests)

    Caching strategy (all under data/raw/):
      - shpo_ca.json          — final complete cache (Phase 1 + Phase 2 done)
      - shpo_ca_listings.json — Phase 1 checkpoint (county listings only)
      - shpo_ca_progress.json — Phase 2 checkpoint (records with partial details)

    On resume: skips completed phases and continues detail fetches from where
    it left off.

    Args:
        config: Source config from STATE_SOURCES.
        use_cache: If True and cache exists, return cached data.

    Returns:
        List of raw resource dicts.
    """
    source_key = config.get("_source_key", "CA")
    final_cache = _cache_path(source_key)
    listings_cache = _cache_path(source_key, "_listings")
    progress_cache = _cache_path(source_key, "_progress")

    # Final cache exists — all done
    if use_cache and final_cache.exists():
        logger.info("[SHPO] %s: Loading from cache: %s", source_key, final_cache)
        return _load_json(final_cache)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "HistoricSitesDB/0.1 (research project)",
    })

    # --- Phase 1: County listing pages ---
    if use_cache and progress_cache.exists():
        # Phase 2 was in progress — resume from checkpoint
        logger.info("[SHPO] %s: Resuming from Phase 2 checkpoint", source_key)
        records = _load_json(progress_cache)
    elif use_cache and listings_cache.exists():
        # Phase 1 complete, Phase 2 not started
        logger.info("[SHPO] %s: Loading Phase 1 from cache, starting Phase 2", source_key)
        records = _load_json(listings_cache)
    else:
        # Fresh start
        records = _fetch_all_counties(session, source_key)
        _save_json(listings_cache, records)
        logger.info(
            "[SHPO] %s: Phase 1 saved to %s", source_key, listings_cache,
        )

    # --- Phase 2: Detail pages ---
    # Count how many already have detail data (from a previous partial run)
    already_fetched = sum(1 for r in records if r.get("_detail_fetched"))
    remaining = len(records) - already_fetched

    if remaining > 0:
        logger.info(
            "[SHPO] %s: Phase 2 — %d detail pages remaining (%d already done)",
            source_key, remaining, already_fetched,
        )
        checkpoints_since_save = 0
        for i, record in enumerate(records):
            if record.get("_detail_fetched"):
                continue

            refnum = record.get("refnum")
            if not refnum:
                record["_detail_fetched"] = True
                continue

            try:
                detail = _fetch_detail_page(session, refnum, source_key)
                record.update(detail)
            except Exception:
                logger.debug("[SHPO] %s: Error fetching detail for %s", source_key, refnum)
            record["_detail_fetched"] = True
            checkpoints_since_save += 1

            fetched_total = already_fetched + checkpoints_since_save
            if fetched_total % DETAIL_LOG_INTERVAL == 0:
                logger.info(
                    "[SHPO] %s: Fetched %d/%d detail pages",
                    source_key, fetched_total, len(records),
                )

            # Periodic checkpoint
            if checkpoints_since_save % DETAIL_CHECKPOINT_INTERVAL == 0:
                _save_json(progress_cache, records)
                logger.info(
                    "[SHPO] %s: Checkpoint saved (%d/%d details)",
                    source_key, fetched_total, len(records),
                )

            time.sleep(DETAIL_RATE_LIMIT)

        logger.info("[SHPO] %s: Phase 2 complete", source_key)
    else:
        logger.info("[SHPO] %s: Phase 2 already complete (all details fetched)", source_key)

    # Strip internal marker before saving final cache
    for record in records:
        record.pop("_detail_fetched", None)

    # Save final cache and clean up intermediate files
    _save_json(final_cache, records)
    logger.info("[SHPO] %s: Cached %d records to %s", source_key, len(records), final_cache)

    for intermediate in (listings_cache, progress_cache):
        if intermediate.exists():
            intermediate.unlink()
            logger.debug("[SHPO] %s: Removed intermediate cache %s", source_key, intermediate)

    return records


def _fetch_all_counties(session: requests.Session, source_key: str) -> list[dict]:
    """Fetch all 58 county listing pages (Phase 1)."""
    logger.info(
        "[SHPO] %s: Phase 1 — Fetching %d county listing pages",
        source_key, NUM_COUNTIES,
    )
    records = []
    for county_id in range(1, NUM_COUNTIES + 1):
        try:
            county_records = _fetch_county_page(session, county_id, source_key)
            records.extend(county_records)
            if county_id % 10 == 0:
                logger.info(
                    "[SHPO] %s: Fetched %d/%d counties (%d records so far)",
                    source_key, county_id, NUM_COUNTIES, len(records),
                )
        except Exception:
            logger.exception("[SHPO] %s: Error fetching county %d", source_key, county_id)
        time.sleep(COUNTY_RATE_LIMIT)

    logger.info(
        "[SHPO] %s: Phase 1 complete — %d records from %d counties",
        source_key, len(records), NUM_COUNTIES,
    )
    return records


def _fetch_county_page(session: requests.Session, county_id: int, source_key: str) -> list[dict]:
    """Fetch and parse a single county listing page."""
    url = f"{COUNTY_URL}{county_id}"
    response = session.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    records = []

    # Find the results table — look for table rows with resource data
    table = soup.find("table")
    if not table:
        logger.debug("[SHPO] %s: No table found for county %d", source_key, county_id)
        return records

    rows = table.find_all("tr")
    for row in rows:
        cells = row.find_all("td")
        if not cells or len(cells) < 2:
            continue

        record = _parse_listing_row(cells, county_id)
        if record:
            records.append(record)

    return records


def _parse_listing_row(cells: list, county_id: int) -> dict | None:
    """Parse a single table row from the county listing page.

    Expected cell layout: [name(refnum), NR, SL, CR, POI, date_listed, city(county)]
    The first cell typically contains an anchor tag with the resource name and
    reference number.
    """
    first_cell = cells[0]

    # Extract name and refnum from first cell
    link = first_cell.find("a")
    if link:
        name_text = link.get_text(strip=True)
        href = link.get("href", "")
    else:
        name_text = first_cell.get_text(strip=True)
        href = ""

    if not name_text:
        return None

    # Extract refnum from href (e.g., "Detail/N2410") or from parentheses
    refnum = None
    if href:
        match = re.search(r"Detail/([^/?]+)", href)
        if match:
            refnum = match.group(1)

    # Try to extract refnum from name text if not in href
    if not refnum:
        match = re.search(r"\(([A-Z]?\d+)\)\s*$", name_text)
        if match:
            refnum = match.group(1)
            name_text = name_text[:match.start()].strip()

    # Extract date_listed (typically second-to-last or last meaningful cell)
    date_listed = None
    city = None
    county = None

    # Try to find date and city/county from remaining cells
    for cell in cells[1:]:
        text = cell.get_text(strip=True)
        if not text:
            continue
        # Date pattern: MM/DD/YYYY or similar
        if re.match(r"\d{1,2}/\d{1,2}/\d{4}", text):
            date_listed = text
        # City (County) pattern
        elif "(" in text and ")" in text:
            city_match = re.match(r"(.+?)\s*\((.+?)\)", text)
            if city_match:
                city = city_match.group(1).strip()
                county = city_match.group(2).strip()
        elif not date_listed and not city:
            # Could be city or other field
            if len(text) > 1 and text[0].isupper() and not text.isdigit():
                city = text

    return {
        "name": name_text,
        "refnum": refnum,
        "date_listed": date_listed,
        "city": city,
        "county": county,
        "county_id": county_id,
    }


def _fetch_detail_page(session: requests.Session, refnum: str, source_key: str) -> dict:
    """Fetch and parse a resource detail page."""
    url = f"{DETAIL_URL}{refnum}"
    response = session.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    detail = {}

    # Look for definition list or labeled fields
    # Common patterns: "NPS Number:", "Location:", "Criterion:", etc.
    text = soup.get_text()

    # Extract NPS Number (maps to nris_refnum)
    nps_match = re.search(r"NPS\s*(?:Number|#|Ref)[:\s]+(\d{8})", text)
    if nps_match:
        detail["nps_number"] = nps_match.group(1)

    # Extract location/address
    loc_match = re.search(r"Location[:\s]+(.+?)(?:\n|Registration|Criterion|Year)", text)
    if loc_match:
        detail["address"] = loc_match.group(1).strip()

    # Extract Registration Date
    reg_match = re.search(r"Registration\s*Date[:\s]+(.+?)(?:\n|Criterion|Year|Architect)", text)
    if reg_match:
        detail["registration_date"] = reg_match.group(1).strip()

    # Extract Criterion
    crit_match = re.search(r"Criteri(?:on|a)[:\s]+(.+?)(?:\n|Architect|Year|Location)", text)
    if crit_match:
        detail["criteria"] = crit_match.group(1).strip()

    # Extract Architect
    arch_match = re.search(r"Architect[:\s]+(.+?)(?:\n|Year|$)", text)
    if arch_match:
        detail["architect"] = arch_match.group(1).strip()

    # Extract Year Built
    year_match = re.search(r"Year\s*(?:Built)?[:\s]+(\d{4})", text)
    if year_match:
        detail["year_built"] = year_match.group(1)

    # Try structured approach — look for dl/dt/dd or table-based layout
    for dt in soup.find_all(["dt", "th", "label", "strong", "b"]):
        label = dt.get_text(strip=True).rstrip(":").lower()
        # Get the next sibling with content
        sibling = dt.find_next_sibling(["dd", "td", "span"])
        if not sibling:
            continue
        value = sibling.get_text(strip=True)
        if not value:
            continue

        if "nps" in label and "number" in label:
            nps = re.search(r"\d{8}", value)
            if nps:
                detail["nps_number"] = nps.group()
        elif "location" in label or "address" in label:
            detail["address"] = value
        elif "registration" in label and "date" in label:
            detail["registration_date"] = value
        elif "criteri" in label:
            detail["criteria"] = value
        elif "architect" in label:
            detail["architect"] = value
        elif "year" in label:
            year = re.search(r"\d{4}", value)
            if year:
                detail["year_built"] = year.group()

    return detail


def parse(raw_data: list[dict], config: dict) -> list[dict]:
    """Convert raw OHP records to site dicts for merge.

    Args:
        raw_data: Raw resource dicts from fetch().
        config: Source config from STATE_SOURCES.

    Returns:
        List of site record dicts ready for merge_shpo_records().
    """
    source_key = config.get("_source_key", "CA")
    sites = []

    for record in raw_data:
        name = record.get("name")
        if not name:
            continue

        site = {
            "name": name,
            "state": "CA",
            "source_shpo": True,
            "primary_source": f"shpo_{source_key.lower()}",
        }

        # Address from detail page
        if record.get("address"):
            site["address"] = record["address"]

        # City and county from listing
        if record.get("city"):
            site["city"] = record["city"]
        if record.get("county"):
            site["county"] = record["county"]

        # NPS number maps to nris_refnum for NRHP matching
        if record.get("nps_number"):
            site["nris_refnum"] = record["nps_number"]

        # State record ID
        if record.get("refnum"):
            site["state_record_id"] = record["refnum"]

        # Date listed
        if record.get("date_listed"):
            site["state_designation_date"] = record["date_listed"]

        # Year built → date_constructed
        if record.get("year_built"):
            site["date_constructed"] = record["year_built"]

        # No coordinates — these will be matched by NRHP refnum or fuzzy name
        # Latitude/longitude remain None

        sites.append(site)

    logger.info(
        "[SHPO] %s: Parsed %d site records from %d raw resources",
        source_key, len(sites), len(raw_data),
    )
    return sites
