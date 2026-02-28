"""
Database schema DDL and category seed data.

Creates all tables for the Historic Sites GeoPackage database and seeds
the dimension tables (historical_eras, event_natures, site_types, ownership_types)
with canonical values from config/categories.py.
"""

import sqlite3
from pathlib import Path

from config.categories import EVENT_NATURES, HISTORICAL_ERAS, OWNERSHIP_TYPES, SITE_TYPES
from config.nrhp_taxonomy import AREAS_OF_SIGNIFICANCE
from src.db.connection import db_connection

# --- DDL Statements ---

SITES_TABLE = """
CREATE TABLE IF NOT EXISTS sites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Identifiers
    nris_refnum TEXT UNIQUE,
    property_id TEXT,
    cr_id TEXT,
    nps_park_code TEXT,
    -- Location
    name TEXT NOT NULL,
    alternate_names TEXT,
    address TEXT,
    city TEXT,
    county TEXT,
    state TEXT,
    latitude REAL,
    longitude REAL,
    coordinates_source TEXT,
    geocode_quality TEXT,
    -- Dates
    date_constructed TEXT,
    nhl_designation_date TEXT,
    nrhp_cert_date TEXT,
    state_designation_date TEXT,
    -- Status
    is_extant BOOLEAN DEFAULT 1,
    nrhp_status TEXT,
    -- Condition
    condition TEXT,
    condition_notes TEXT,
    active_threats TEXT,
    -- Visitor access
    public_access TEXT,
    visiting_hours TEXT,
    admission_info TEXT,
    website_url TEXT,
    -- Descriptions
    short_description TEXT,
    full_description TEXT,
    marker_inscription TEXT,
    -- Source tracking (boolean flags)
    source_arcgis BOOLEAN DEFAULT 0,
    source_spreadsheet BOOLEAN DEFAULT 0,
    source_nps_parks BOOLEAN DEFAULT 0,
    source_nomination BOOLEAN DEFAULT 0,
    source_shpo BOOLEAN DEFAULT 0,
    source_other BOOLEAN DEFAULT 0,
    -- Source authority
    primary_source TEXT,
    source_url TEXT,
    -- Enrichment
    enrichment_status TEXT DEFAULT 'pending',
    enrichment_raw_json TEXT,
    -- Review
    confidence_score REAL,
    review_status TEXT DEFAULT 'unreviewed',
    review_priority INTEGER,
    reviewer_notes TEXT,
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data_checksum TEXT
);
"""

SITE_DESIGNATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS site_designations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    designation_type TEXT NOT NULL,
    designation_date TEXT,
    designating_authority TEXT,
    source TEXT,
    UNIQUE(site_id, designation_type)
);
"""

NRHP_CRITERIA_TABLE = """
CREATE TABLE IF NOT EXISTS nrhp_criteria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    criterion TEXT NOT NULL CHECK(criterion IN ('A', 'B', 'C', 'D')),
    source TEXT,
    UNIQUE(site_id, criterion)
);
"""

NRHP_AREAS_TABLE = """
CREATE TABLE IF NOT EXISTS nrhp_areas_of_significance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    area_slug TEXT NOT NULL,
    source TEXT,
    UNIQUE(site_id, area_slug)
);
"""

NRHP_PERIODS_TABLE = """
CREATE TABLE IF NOT EXISTS nrhp_periods_of_significance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    start_year INTEGER,
    end_year INTEGER,
    source TEXT
);
"""

# --- Enrichment Category Dimension Tables ---

HISTORICAL_ERAS_TABLE = """
CREATE TABLE IF NOT EXISTS historical_eras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    slug TEXT NOT NULL UNIQUE,
    sort_order INTEGER NOT NULL
);
"""

EVENT_NATURES_TABLE = """
CREATE TABLE IF NOT EXISTS event_natures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    slug TEXT NOT NULL UNIQUE,
    sort_order INTEGER NOT NULL
);
"""

SITE_TYPES_TABLE = """
CREATE TABLE IF NOT EXISTS site_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    slug TEXT NOT NULL UNIQUE,
    sort_order INTEGER NOT NULL
);
"""

OWNERSHIP_TYPES_TABLE = """
CREATE TABLE IF NOT EXISTS ownership_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    slug TEXT NOT NULL UNIQUE,
    sort_order INTEGER NOT NULL
);
"""

# --- Junction Tables (Many-to-Many with rank and confidence) ---

SITE_ERAS_TABLE = """
CREATE TABLE IF NOT EXISTS site_eras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    era_id INTEGER NOT NULL REFERENCES historical_eras(id) ON DELETE CASCADE,
    rank INTEGER DEFAULT 1 CHECK(rank BETWEEN 1 AND 3),
    confidence REAL DEFAULT 1.0 CHECK(confidence BETWEEN 0.0 AND 1.0),
    source TEXT DEFAULT 'ai',
    UNIQUE(site_id, era_id)
);
"""

SITE_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS site_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    event_id INTEGER NOT NULL REFERENCES event_natures(id) ON DELETE CASCADE,
    rank INTEGER DEFAULT 1 CHECK(rank BETWEEN 1 AND 3),
    confidence REAL DEFAULT 1.0 CHECK(confidence BETWEEN 0.0 AND 1.0),
    source TEXT DEFAULT 'ai',
    UNIQUE(site_id, event_id)
);
"""

SITE_SITE_TYPES_TABLE = """
CREATE TABLE IF NOT EXISTS site_site_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    type_id INTEGER NOT NULL REFERENCES site_types(id) ON DELETE CASCADE,
    rank INTEGER DEFAULT 1 CHECK(rank BETWEEN 1 AND 3),
    confidence REAL DEFAULT 1.0 CHECK(confidence BETWEEN 0.0 AND 1.0),
    source TEXT DEFAULT 'ai',
    UNIQUE(site_id, type_id)
);
"""

SITE_OWNERSHIP_TABLE = """
CREATE TABLE IF NOT EXISTS site_ownership (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    ownership_id INTEGER NOT NULL REFERENCES ownership_types(id) ON DELETE CASCADE,
    rank INTEGER DEFAULT 1 CHECK(rank BETWEEN 1 AND 3),
    confidence REAL DEFAULT 1.0 CHECK(confidence BETWEEN 0.0 AND 1.0),
    source TEXT DEFAULT 'ai',
    UNIQUE(site_id, ownership_id)
);
"""

# --- Relationships ---

SITE_RELATIONSHIPS_TABLE = """
CREATE TABLE IF NOT EXISTS site_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id_a INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    site_id_b INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL,
    relationship_name TEXT,
    notes TEXT,
    UNIQUE(site_id_a, site_id_b, relationship_type)
);
"""

# --- Provenance & Audit ---

SITE_SOURCES_TABLE = """
CREATE TABLE IF NOT EXISTS site_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    source_name TEXT NOT NULL,
    source_record_id TEXT,
    source_url TEXT,
    date_fetched TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    raw_data_json TEXT
);
"""

PIPELINE_RUNS_TABLE = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stage TEXT NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    records_processed INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running',
    error_message TEXT
);
"""

DATA_SOURCE_METADATA_TABLE = """
CREATE TABLE IF NOT EXISTS data_source_metadata (
    source_name TEXT PRIMARY KEY,
    last_fetch TIMESTAMP,
    record_count INTEGER DEFAULT 0,
    checksum TEXT
);
"""

# --- Indexes ---

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_sites_state ON sites(state);",
    "CREATE INDEX IF NOT EXISTS idx_sites_name ON sites(name);",
    "CREATE INDEX IF NOT EXISTS idx_sites_confidence ON sites(confidence_score);",
    "CREATE INDEX IF NOT EXISTS idx_sites_review ON sites(review_status);",
    "CREATE INDEX IF NOT EXISTS idx_designations_site ON site_designations(site_id);",
    "CREATE INDEX IF NOT EXISTS idx_nrhp_criteria_site ON nrhp_criteria(site_id);",
    "CREATE INDEX IF NOT EXISTS idx_nrhp_areas_site ON nrhp_areas_of_significance(site_id);",
    "CREATE INDEX IF NOT EXISTS idx_nrhp_periods_site ON nrhp_periods_of_significance(site_id);",
    "CREATE INDEX IF NOT EXISTS idx_site_eras_site ON site_eras(site_id);",
    "CREATE INDEX IF NOT EXISTS idx_site_events_site ON site_events(site_id);",
    "CREATE INDEX IF NOT EXISTS idx_site_types_site ON site_site_types(site_id);",
    "CREATE INDEX IF NOT EXISTS idx_site_ownership_site ON site_ownership(site_id);",
    "CREATE INDEX IF NOT EXISTS idx_site_sources_site ON site_sources(site_id);",
    "CREATE INDEX IF NOT EXISTS idx_relationships_a ON site_relationships(site_id_a);",
    "CREATE INDEX IF NOT EXISTS idx_relationships_b ON site_relationships(site_id_b);",
]

# All DDL statements in creation order
ALL_TABLES = [
    SITES_TABLE,
    SITE_DESIGNATIONS_TABLE,
    NRHP_CRITERIA_TABLE,
    NRHP_AREAS_TABLE,
    NRHP_PERIODS_TABLE,
    HISTORICAL_ERAS_TABLE,
    EVENT_NATURES_TABLE,
    SITE_TYPES_TABLE,
    OWNERSHIP_TYPES_TABLE,
    SITE_ERAS_TABLE,
    SITE_EVENTS_TABLE,
    SITE_SITE_TYPES_TABLE,
    SITE_OWNERSHIP_TABLE,
    SITE_RELATIONSHIPS_TABLE,
    SITE_SOURCES_TABLE,
    PIPELINE_RUNS_TABLE,
    DATA_SOURCE_METADATA_TABLE,
]


def create_tables(conn: sqlite3.Connection) -> None:
    """Create all database tables."""
    cursor = conn.cursor()
    for ddl in ALL_TABLES:
        cursor.executescript(ddl)
    for idx in INDEXES:
        cursor.execute(idx)
    conn.commit()


def seed_categories(conn: sqlite3.Connection) -> None:
    """Seed dimension tables with canonical category values.

    Uses INSERT OR IGNORE so it's safe to call repeatedly (idempotent).
    """
    cursor = conn.cursor()

    for era in HISTORICAL_ERAS:
        cursor.execute(
            "INSERT OR IGNORE INTO historical_eras (name, slug, sort_order) VALUES (?, ?, ?)",
            (era["name"], era["slug"], era["sort_order"]),
        )

    for event in EVENT_NATURES:
        cursor.execute(
            "INSERT OR IGNORE INTO event_natures (name, slug, sort_order) VALUES (?, ?, ?)",
            (event["name"], event["slug"], event["sort_order"]),
        )

    for st in SITE_TYPES:
        cursor.execute(
            "INSERT OR IGNORE INTO site_types (name, slug, sort_order) VALUES (?, ?, ?)",
            (st["name"], st["slug"], st["sort_order"]),
        )

    for ot in OWNERSHIP_TYPES:
        cursor.execute(
            "INSERT OR IGNORE INTO ownership_types (name, slug, sort_order) VALUES (?, ?, ?)",
            (ot["name"], ot["slug"], ot["sort_order"]),
        )

    conn.commit()


def create_database(db_path: Path | None = None) -> None:
    """Create the database with all tables and seed data.

    Args:
        db_path: Path to the GeoPackage file. Defaults to GEOPACKAGE_PATH.
    """
    with db_connection(db_path) as conn:
        create_tables(conn)
        seed_categories(conn)
