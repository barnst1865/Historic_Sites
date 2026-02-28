# Architecture

Technical deep dive into the Historic Sites Database system.

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Data Sources                             │
│  ArcGIS API │ NHL Spreadsheet │ NPS Parks │ Nomination PDFs     │
└──────┬──────┴────────┬────────┴─────┬─────┴────────┬───────────┘
       │               │              │              │
       ▼               ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 1: INGEST                                                │
│  arcgis_client │ spreadsheet_loader │ nps_parks │ nom_extractor │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 2: VALIDATE                                              │
│  Coordinates │ Dates │ Entity Resolution │ State Cross-check    │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 3: NOMINATION EXTRACTION                                 │
│  Claude PDF → OCR Fallback → Manual Flag                        │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 4: MERGE (Idempotent Upsert)                             │
│  Dedup by NRIS refnum │ Fuzzy name + proximity │ Source priority │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 5: GEOCODE                                               │
│  Census Bureau Batch → Nominatim Fallback → Quality Scoring     │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 6: PROFILE                                               │
│  Completeness │ Distributions │ Outliers │ Richness Routing     │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 7: AI ENRICH                                             │
│  NRHP→Category Mapping │ Claude Classification │ Rank Assignment│
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 8: SCORE                                                 │
│  8-Factor Confidence │ Review Queue │ Priority Assignment        │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 9: EXPORT                                                │
│  KML/KMZ │ GeoJSON │ Folium HTML │ GeoPackage │ Review CSV      │
└─────────────────────────────────────────────────────────────────┘
```

## Database Schema

The database uses GeoPackage (.gpkg), an OGC standard built on SQLite with native spatial indexing. All coordinates are WGS84 (EPSG:4326).

### Core Tables

#### `sites` — One record per historic site

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| nris_refnum | TEXT UNIQUE | NRHP reference number (primary federal key) |
| property_id | TEXT | NPS property ID |
| cr_id | TEXT | Cultural resource ID |
| nps_park_code | TEXT | NPS park alpha code |
| name | TEXT NOT NULL | Official site name |
| alternate_names | TEXT | Pipe-delimited alternate names |
| address | TEXT | Street address |
| city | TEXT | City |
| county | TEXT | County |
| state | TEXT | 2-letter state code |
| latitude | REAL | WGS84 latitude |
| longitude | REAL | WGS84 longitude |
| coordinates_source | TEXT | Where coordinates came from |
| geocode_quality | TEXT | exact/interpolated/city_level/zip_level/manual |
| date_constructed | TEXT | ISO 8601 date or year |
| nhl_designation_date | TEXT | NHL designation date |
| nrhp_cert_date | TEXT | NRHP certification date |
| state_designation_date | TEXT | State register date |
| is_extant | BOOLEAN | Whether site still exists |
| nrhp_status | TEXT | NRHP listing status |
| condition | TEXT | Good/Fair/Poor/Ruins/Unknown |
| condition_notes | TEXT | Details on condition |
| active_threats | TEXT | Current threats to site |
| public_access | TEXT | Yes/Limited/No/Unknown |
| visiting_hours | TEXT | Operating hours |
| admission_info | TEXT | Fee/free info |
| website_url | TEXT | Official website |
| short_description | TEXT | Brief description |
| full_description | TEXT | Full narrative description |
| marker_inscription | TEXT | Wayside marker text |
| source_arcgis | BOOLEAN | Has ArcGIS data |
| source_spreadsheet | BOOLEAN | Has spreadsheet data |
| source_nps_parks | BOOLEAN | Has NPS Parks data |
| source_nomination | BOOLEAN | Has nomination data |
| source_shpo | BOOLEAN | Has SHPO data |
| source_other | BOOLEAN | Has other source data |
| primary_source | TEXT | Most authoritative source |
| source_url | TEXT | URL to source |
| enrichment_status | TEXT | pending/complete/failed |
| enrichment_raw_json | TEXT | Raw AI response for audit |
| confidence_score | REAL | 0.0-1.0 composite score |
| review_status | TEXT | auto_approved/unreviewed/flagged |
| review_priority | INTEGER | Lower = higher priority |
| reviewer_notes | TEXT | Manual reviewer notes |
| created_at | TIMESTAMP | Record creation time |
| updated_at | TIMESTAMP | Last modification time |
| data_checksum | TEXT | SHA256 for change detection |

#### `site_designations` — Multiple designations per site

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | |
| site_id | INTEGER FK | References sites.id |
| designation_type | TEXT | Federal NHL/NRHP, State, Local, Tribal, NPS Unit, Private/NGO |
| designation_date | TEXT | Date of designation |
| designating_authority | TEXT | Who designated it |
| source | TEXT | Data source |

#### NRHP Classification Tables

- **`nrhp_criteria`** — site_id, criterion (A/B/C/D), source
- **`nrhp_areas_of_significance`** — site_id, area_slug, source
- **`nrhp_periods_of_significance`** — site_id, start_year, end_year, source

#### Enrichment Category Tables

Dimension tables: `historical_eras`, `event_natures`, `site_types`, `ownership_types`
Each has: id, name, slug, sort_order

Junction tables: `site_eras`, `site_events`, `site_site_types`, `site_ownership`
Each has: site_id, category_id, rank (1-3), confidence (0.0-1.0), source

#### `site_relationships`

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | |
| site_id_a | INTEGER FK | |
| site_id_b | INTEGER FK | |
| relationship_type | TEXT | thematic_group/trail_network/campaign/parent_child/associated |
| relationship_name | TEXT | e.g. "Underground Railroad" |
| notes | TEXT | |

#### `site_sources` — Provenance tracking

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | |
| site_id | INTEGER FK | |
| source_name | TEXT | e.g. "arcgis", "nhl_spreadsheet" |
| source_record_id | TEXT | ID in original source |
| source_url | TEXT | URL to original record |
| date_fetched | TIMESTAMP | When data was retrieved |
| raw_data_json | TEXT | Original source record |

#### Pipeline Tracking

- **`pipeline_runs`** — id, stage, started_at, completed_at, records_processed, status, error_message
- **`data_source_metadata`** — source_name, last_fetch, record_count, checksum

### Indexes

- `sites.nris_refnum` (UNIQUE)
- `sites.state`
- `sites.name`
- `sites.confidence_score`
- `sites.review_status`
- All junction table `site_id` columns
- `site_sources.site_id`

## Data Flow Example

How a single NHL record flows through the pipeline:

1. **ArcGIS** returns `{"ResName": "Independence Hall", "Is_NHL": "X", "geometry": {"x": -75.15, "y": 39.95}, ...}`
2. **Spreadsheet** has the same site with NRIS refnum `66000661`, criteria A/C, areas: Architecture, Politics/Government
3. **Validator** checks coordinates fall in Pennsylvania, normalizes dates
4. **Nomination extractor** downloads the nomination PDF, Claude extracts period of significance (1732-1799), full description
5. **Merger** matches by NRIS refnum, upserts: coordinates from ArcGIS, criteria from spreadsheet, description from nomination
6. **Geocoder** skips (already has coordinates from ArcGIS)
7. **Profiler** categorizes as "data-rich" (has description, NRHP data, coordinates)
8. **Enricher** maps NRHP "Politics/Government" → event_nature "Political", infers era "Revolutionary". AI confirms site_type "Government Building"
9. **Scorer** calculates confidence 0.92 (rich data, multiple sources agree) → auto_approved
10. **Exporter** generates KML pin, GeoJSON feature, Folium marker with popup

## Entity Resolution

Cross-source matching uses two strategies:

1. **NRIS Reference Number** — Exact match for federal records. Authoritative.
2. **Fuzzy Name + Proximity** — For records without shared IDs:
   - Normalize names: strip suffixes ("National Historic Site", "NHS", "NHP", etc.)
   - `thefuzz.fuzz.token_sort_ratio` ≥ 85% AND geographic distance ≤ 0.5km → match
   - `token_sort_ratio` ≥ 70% AND distance ≤ 0.5km → candidate (logged for review)
   - All match decisions logged with scores

## Confidence Scoring

| Factor | Weight | Calculation |
|--------|--------|-------------|
| Data completeness | 0.10 | % of key fields non-NULL (coords, dates, address, state) |
| Description richness | 0.10 | Word count buckets: >100=1.0, 50-100=0.7, 5-50=0.4, <5=0.1 |
| NRHP official data | 0.15 | Has criteria + areas + period = 1.0, partial = 0.5, none = 0.0 |
| Nomination extraction | 0.10 | claude_pdf=1.0, ocr_then_claude=0.7, manual_needed=0.2, not_available=0.3 |
| AI confidence | 0.25 | Mean confidence across all assigned categories |
| Classification ambiguity | 0.10 | 1.0 - (std_dev of category confidences). Low variance = clear |
| Source agreement | 0.10 | Number of sources: 4+=1.0, 3=0.8, 2=0.6, 1=0.3 |
| Name specificity | 0.10 | Penalize generic names ("Historic District", "Site") |

**Thresholds**: ≥0.8 auto-approved, 0.5-0.8 unreviewed, <0.5 flagged

## Idempotency

All pipeline stages are safe to re-run:

- **Ingest**: Raw responses cached with timestamps and checksums. Only re-fetches if cache expired.
- **Merge**: Upsert keyed by `nris_refnum`. Checksums detect changed records. Fields with `source='manual'` never overwritten.
- **Geocode**: Skips sites that already have coordinates (unless `--force` flag).
- **Enrich**: Skips sites where `enrichment_status='complete'` (unless `--force` flag).
- **Score**: Always recalculates (fast, no external calls).
- **Export**: Always regenerates outputs.

## Export Format Details

- **KML**: `simplekml` uses `(lon, lat)` order. Split per state and per category for Google My Maps (<2,000 points each).
- **GeoJSON**: RFC 7946 standard. Flat properties (no nesting) for Leaflet/Mapbox compatibility.
- **Folium HTML**: MarkerCluster for performance. LayerControl with FeatureGroups by designation level and era.
- **GeoPackage**: Full database export for QGIS/ArcGIS professionals.

## Adding a New Data Source

1. Create `src/ingest/<source>_client.py` implementing the fetch interface
2. Define field mapping to the `sites` schema
3. Add source flag column if needed (`source_<name>` boolean on `sites`)
4. Register in `config/settings.py` under `DATA_SOURCES`
5. Add to `merger.py` merge order with appropriate field priority
6. Add test fixtures in `tests/fixtures/`
7. Update `scripts/run_ingest.py` `--source` choices
8. Update this document and `README.md`
