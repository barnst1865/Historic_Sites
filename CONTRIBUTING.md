# Contributing to Historic Sites Database

## Data Quality Standards

### Authoritative Sources
- Federal: NPS official databases, ArcGIS REST services, nomination documents
- State: Official SHPO databases and registers
- Local: Official municipal landmark commission records
- All data must have documented provenance (source URL, fetch date, original record ID)

### Source Documentation
Every ingest module must record in `site_sources`:
- `source_name` — identifier for the data source
- `source_record_id` — ID in the original system
- `source_url` — link to the original record (if available)
- `date_fetched` — when the data was retrieved
- `raw_data_json` — complete original record for audit

## Adding Data Sources

### Template for New Ingest Modules

1. Create `src/ingest/<source>_client.py`
2. Implement the standard interface:
   - `fetch()` — retrieve raw data, cache to `data/raw/`
   - `parse()` — transform to site records matching our schema
   - `validate()` — run through `validator.py`
3. Define field mapping (which source fields map to which `sites` columns)
4. Set source priority in `merger.py` (where does this source rank for each field?)
5. Add test fixtures in `tests/fixtures/<source>/`
6. Register in `config/settings.py`

### Required Fields
At minimum, every record must have:
- `name` — site name
- `state` — 2-letter state code
- At least one of: coordinates (lat/lon), address, or city

## Manual Review Guidelines

### When Reviewing AI Classifications
- Check that the primary era matches the site's main period of significance
- Verify event nature aligns with why the site is historically significant (not just what it is)
- Confirm site type matches the physical nature of the site
- Flag any obvious misclassifications (e.g., a church classified as "Military")

### Approval Criteria
- **Approve**: Classifications are accurate and appropriately ranked
- **Modify**: Adjust specific categories, ranks, or add missing ones
- **Flag**: Significant issues requiring deeper research

## Code Standards

### Style
- Formatter/linter: `ruff` (configured in `pyproject.toml`)
- Type hints on all public function signatures
- Docstrings on public functions (Google style)

### Testing
- All ingest modules must have tests with fixture data (no live API calls in tests)
- Tests use in-memory SQLite databases
- Run `pytest tests/` before submitting

## Pull Request Process

1. Branch from `develop` (never directly from `main`)
2. Use feature branch naming: `feature/<phase>-<description>`
3. Include tests for new functionality
4. Update `README.md` and `ARCHITECTURE.md` if schema or pipeline changes
5. Ensure `ruff check` and `pytest` pass
6. PR description should include: what changed, why, and how to verify

## Commit Convention

- `feat:` — New feature or pipeline stage
- `data:` — Data source additions or schema changes
- `fix:` — Bug fixes
- `docs:` — Documentation updates
- `refactor:` — Code restructuring
- `test:` — Test additions/modifications
