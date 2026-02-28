# CLAUDE.md
This file provides guidance to Claude Code when working with this repository.

## Build & Run Commands
- Install: `pip install -e ".[dev]"`
- Run full pipeline: `python scripts/run_pipeline.py`
- Run single stage: `python scripts/run_ingest.py --source nhl`
- Run tests: `pytest tests/`
- Run single test: `pytest tests/test_ingest.py::test_arcgis_fetch`
- Lint: `ruff check src/ scripts/ tests/`
- Format: `ruff format src/ scripts/ tests/`

## Architecture
- GeoPackage database (SQLite + spatial): `data/historic_sites.gpkg`
- 9-stage pipeline: Ingest → Validate → Nominations → Merge → Geocode → Profile → Enrich → Score → Export
- All pipeline stages are idempotent (safe to re-run)
- Manual review data (source='manual') is never overwritten by re-runs

## Key Design Decisions
- GeoPackage over plain SQLite for spatial query support (EPSG:4326)
- Official NRHP taxonomy (Areas of Significance, Criteria A-D) captured first; AI enrichment layers on top
- Multi-strategy PDF extraction: Claude native → OCR fallback → manual flag
- Many-to-many categories with rank (1=primary, 2=secondary, 3=tertiary)
- Sites can hold multiple designations (NHL + NRHP + State + Local simultaneously)

## Category System
- NRHP official: 31 Areas of Significance + Criteria A-D (from source data, authoritative)
- Our enrichment: historical_eras, event_natures, site_types, ownership_types (AI-assisted)
- Categories defined in config/categories.py and config/nrhp_taxonomy.py

## Data Sources
- ArcGIS: Is_NHL='X' (not 'Yes'). Geometry: {"x": lon, "y": lat}. Paginate with resultOffset.
- NPS Parks API: latLong is "lat:38.9, long:-77.0" string. Rate: 1000 req/hr.
- Census Geocoder: Batch API, 10K addresses/batch.

## Testing
- Fixtures in tests/fixtures/ contain sample API responses
- Tests use SQLite in-memory DB, no external API calls
- Run `pytest -x` to stop on first failure
