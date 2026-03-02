# State-Level Historic Site Data Sources — Design

**Date:** 2026-03-02
**Status:** Approved

## Goal

Expand dataset coverage by ingesting state-designated historic sites that are not in the federal NHL/NRHP lists. Capture all designation levels: state registers, local landmarks, historic districts, and any other recognition.

## Approach

Hybrid adapters + per-state overrides (Approach C). Build generic adapters for common data patterns, allow per-state custom modules when needed. Research all 50 states + territories first, then build in order of easiest data access.

---

## Section 1: State Source Inventory

Before writing any code, produce a comprehensive inventory at `docs/plans/state-source-inventory.md` cataloging every state and territory's SHPO data availability.

For each entry:

| Field | Description |
|-------|-------------|
| State/territory | Name + postal code |
| SHPO website | URL of the State Historic Preservation Office |
| Data format | ArcGIS service, CSV download, searchable database, PDF-only, none found |
| Accessibility | Open (no auth), requires registration, FOIA-only, not available |
| Estimated record count | Rough site count if discoverable |
| Adapter type | `arcgis`, `csv`, `socrata`, `html_scraper`, `custom`, `manual` |
| URL/endpoint | Direct data URL if available |
| Notes | Quirks, rate limits, terms of use |

Build states in order of easiest adapter type: ArcGIS > CSV > Socrata > HTML scraper > custom.

---

## Section 2: Architecture

### Layer 1: Generic Adapters (`src/ingest/shpo_adapters/`)

Reusable adapters for common data source patterns. Each implements `fetch(config) -> raw_data` and `parse(raw_data, field_map) -> list[dict]`.

| Adapter | Covers | How it works |
|---------|--------|-------------|
| `arcgis_adapter.py` | States publishing via ArcGIS REST services | Paginated query against MapServer/FeatureServer. Config specifies URL, filter, field mapping. |
| `csv_adapter.py` | States offering downloadable CSV/Excel | Downloads file from URL or reads local copy, applies column mapping. |
| `socrata_adapter.py` | States using Socrata open data portals | SODA API with SoQL queries, pagination via `$offset`. |
| `html_adapter.py` | States with only a searchable web database | Paginated HTML fetch, parsed with BeautifulSoup. Last resort. |

### Layer 2: State Registry (`config/state_sources.py`)

Dict mapping state codes to source configuration:

```python
STATE_SOURCES = {
    "CA": {
        "adapter": "arcgis",
        "endpoint": "https://...",
        "field_map": {"name": "PROP_NAME", "address": "ADDRESS", ...},
        "designation_types": ["State Register", "Local Landmark"],
    },
    "NY": {
        "adapter": "custom",  # uses shpo_scrapers/new_york.py
    },
}
```

### Layer 3: Per-State Overrides (`src/ingest/shpo_scrapers/<state>.py`)

Custom modules for states that don't fit any adapter. Same `fetch()` / `parse()` interface. Only written when an adapter can't handle a state's quirks.

### Dispatcher (`src/ingest/shpo_dispatcher.py`)

Single entry point that reads the registry and routes to the right adapter or custom module:

```python
def fetch_state(state_code: str, use_cache: bool = True) -> list[dict]:
    config = STATE_SOURCES[state_code]
    if config["adapter"] == "custom":
        return import_scraper(state_code).fetch(use_cache)
    else:
        return get_adapter(config["adapter"]).fetch(config, use_cache)
```

---

## Section 3: Data Model

No new tables needed. State data maps to the existing schema:

**New sites** (state-only, no federal designation):
- `source_shpo = 1`
- `primary_source = 'shpo_<state_code>'` (e.g. `shpo_ca`)
- `state_designation_date` populated if available
- `nris_refnum` may be NULL

**Designations** via existing `site_designations` table:
- `designation_type`: `"State Register"`, `"Local Landmark"`, or state-specific (e.g. `"California Historical Landmark"`)
- `designating_authority`: state agency name
- `source`: `'shpo_<state_code>'`

**Dedup key:** Secondary match strategy for sites without `nris_refnum`:
1. Try `nris_refnum` if present
2. Fuzzy name match (token sort ratio >= 85) + geographic proximity (<= 0.5km)
3. If no match, insert as new

**Source registration:** Each state added to `DATA_SOURCES` with priority 4 (below all federal sources).

**Field priority:** State data ranks below federal, above AI enrichment:
```
"coordinates": ["arcgis", "nps_parks", "shpo_*", "nominations"]
"description": ["nominations", "nps_parks", "shpo_*", "arcgis"]
```

---

## Section 4: Pipeline Integration

SHPO ingest slots into Stage 1 after federal sources:

```
Stage 1: INGEST
  1a. NHL Spreadsheet     (existing)
  1b. ArcGIS NHLs         (existing)
  1c. NPS Parks            (existing)
  1d. SHPO State Sources   (NEW)
```

**CLI flags:**
- `run_pipeline.py`: `--skip-shpo`, `--shpo-states CA,NY,TX`
- `run_ingest.py`: `--source shpo`, `--source shpo --states CA`

**Execution:**
1. Dispatcher iterates active states in `STATE_SOURCES`
2. Each state: `fetch_state()` -> `parse_state()` -> `merge_shpo_records()`
3. Each state is its own `pipeline_runs` entry (failure in one doesn't block others)
4. File caching: `data/raw/shpo_<state_code>.json`
5. Progress logging: `[SHPO] CA: fetched 1,234 sites, merged 1,100 new / 134 matched existing`

**Rate limiting:** Default 1 req/second for HTML scrapers, no limit for open APIs. Per-state override in registry.

---

## Section 5: Merge Strategy

`merge_shpo_records()` in `src/ingest/merger.py`:

**Three-pass matching:**

1. **NRIS match** — If the state record has an NRHP reference number, match via `get_site_by_refnum()`. Update existing: set `source_shpo = 1`, add state designation, merge NULL fields.

2. **Fuzzy + proximity match** — No NRIS number: load all existing sites in that state, run `thefuzz` token sort ratio (>= 85) AND geographic proximity (<= 0.5km). Catches different-name variants of the same site.

3. **New insert** — No match: insert as new site with `primary_source = 'shpo_<state>'`.

**Field update rules:**
- State data never overwrites federal source fields (priority 4)
- State data fills NULL fields only
- `source='manual'` is untouchable
- State designations are always additive

**Conflict logging:**
- Fuzzy matches scoring 70-84 logged as candidates for manual review
- Coordinate discrepancies between state and federal data logged but federal coordinates kept

**Expected volume:** 200K-500K sites total across all states (from ~200 in small states to 30K+ in large ones).
