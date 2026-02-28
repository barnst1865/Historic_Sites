"""Tests for database schema creation and category seeding."""

import sqlite3

import pytest

from src.db.schema import create_tables, seed_categories
from src.db.queries import (
    add_designation,
    add_nrhp_area,
    add_nrhp_criterion,
    add_nrhp_period,
    add_site_category,
    add_site_source,
    count_sites,
    get_site_by_id,
    get_site_by_refnum,
    upsert_site,
    update_site,
    start_pipeline_run,
    complete_pipeline_run,
)


@pytest.fixture
def db():
    """Create an in-memory database with schema and seed data."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    create_tables(conn)
    seed_categories(conn)
    yield conn
    conn.close()


class TestSchemaCreation:
    def test_all_tables_exist(self, db):
        tables = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        expected = {
            "sites",
            "site_designations",
            "nrhp_criteria",
            "nrhp_areas_of_significance",
            "nrhp_periods_of_significance",
            "historical_eras",
            "event_natures",
            "site_types",
            "ownership_types",
            "site_eras",
            "site_events",
            "site_site_types",
            "site_ownership",
            "site_relationships",
            "site_sources",
            "pipeline_runs",
            "data_source_metadata",
        }
        assert expected.issubset(tables)

    def test_historical_eras_seeded(self, db):
        count = db.execute("SELECT COUNT(*) FROM historical_eras").fetchone()[0]
        assert count == 12

    def test_event_natures_seeded(self, db):
        count = db.execute("SELECT COUNT(*) FROM event_natures").fetchone()[0]
        assert count == 15

    def test_site_types_seeded(self, db):
        count = db.execute("SELECT COUNT(*) FROM site_types").fetchone()[0]
        assert count == 19

    def test_ownership_types_seeded(self, db):
        count = db.execute("SELECT COUNT(*) FROM ownership_types").fetchone()[0]
        assert count == 9

    def test_seed_is_idempotent(self, db):
        seed_categories(db)
        seed_categories(db)
        count = db.execute("SELECT COUNT(*) FROM historical_eras").fetchone()[0]
        assert count == 12


class TestSitesCRUD:
    def test_insert_site(self, db):
        site_id = upsert_site(db, {"name": "Independence Hall", "state": "PA"})
        assert site_id == 1
        assert count_sites(db) == 1

    def test_upsert_updates_existing(self, db):
        site_id_1 = upsert_site(
            db, {"name": "Independence Hall", "nris_refnum": "66000661", "state": "PA"}
        )
        site_id_2 = upsert_site(
            db,
            {
                "name": "Independence Hall",
                "nris_refnum": "66000661",
                "latitude": 39.9489,
                "longitude": -75.1500,
            },
        )
        assert site_id_1 == site_id_2
        assert count_sites(db) == 1

        site = get_site_by_id(db, site_id_1)
        assert site["latitude"] == 39.9489

    def test_upsert_skips_unchanged(self, db):
        data = {"name": "Test Site", "nris_refnum": "99999999", "state": "NY"}
        upsert_site(db, data)
        # Second call with same data should skip (checksum match)
        upsert_site(db, data)
        assert count_sites(db) == 1

    def test_get_by_refnum(self, db):
        upsert_site(db, {"name": "Gettysburg", "nris_refnum": "66000614", "state": "PA"})
        site = get_site_by_refnum(db, "66000614")
        assert site is not None
        assert site["name"] == "Gettysburg"

    def test_get_nonexistent_returns_none(self, db):
        assert get_site_by_refnum(db, "00000000") is None
        assert get_site_by_id(db, 999) is None

    def test_update_site(self, db):
        site_id = upsert_site(db, {"name": "Test", "state": "VA"})
        update_site(db, site_id, {"confidence_score": 0.85, "review_status": "auto_approved"})
        site = get_site_by_id(db, site_id)
        assert site["confidence_score"] == 0.85
        assert site["review_status"] == "auto_approved"


class TestDesignations:
    def test_add_designation(self, db):
        site_id = upsert_site(db, {"name": "Test NHL", "state": "DC"})
        add_designation(
            db,
            site_id,
            {
                "designation_type": "Federal NHL",
                "designation_date": "1960-10-15",
                "designating_authority": "Secretary of the Interior",
                "source": "spreadsheet",
            },
        )
        rows = db.execute(
            "SELECT * FROM site_designations WHERE site_id = ?", (site_id,)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["designation_type"] == "Federal NHL"

    def test_designation_idempotent(self, db):
        site_id = upsert_site(db, {"name": "Test", "state": "DC"})
        desig = {"designation_type": "Federal NHL", "source": "test"}
        add_designation(db, site_id, desig)
        add_designation(db, site_id, desig)
        count = db.execute(
            "SELECT COUNT(*) FROM site_designations WHERE site_id = ?", (site_id,)
        ).fetchone()[0]
        assert count == 1


class TestNRHPClassification:
    def test_add_criteria(self, db):
        site_id = upsert_site(db, {"name": "Test", "state": "PA"})
        add_nrhp_criterion(db, site_id, "A", "spreadsheet")
        add_nrhp_criterion(db, site_id, "C", "spreadsheet")
        rows = db.execute(
            "SELECT criterion FROM nrhp_criteria WHERE site_id = ? ORDER BY criterion",
            (site_id,),
        ).fetchall()
        assert [r["criterion"] for r in rows] == ["A", "C"]

    def test_add_areas_of_significance(self, db):
        site_id = upsert_site(db, {"name": "Test", "state": "PA"})
        add_nrhp_area(db, site_id, "architecture", "spreadsheet")
        add_nrhp_area(db, site_id, "politics-government", "nomination")
        rows = db.execute(
            "SELECT area_slug FROM nrhp_areas_of_significance WHERE site_id = ?",
            (site_id,),
        ).fetchall()
        assert len(rows) == 2

    def test_add_period_of_significance(self, db):
        site_id = upsert_site(db, {"name": "Test", "state": "PA"})
        add_nrhp_period(db, site_id, 1732, 1799, "nomination")
        rows = db.execute(
            "SELECT * FROM nrhp_periods_of_significance WHERE site_id = ?",
            (site_id,),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["start_year"] == 1732
        assert rows[0]["end_year"] == 1799


class TestEnrichmentCategories:
    def test_add_era(self, db):
        site_id = upsert_site(db, {"name": "Test", "state": "PA"})
        era_id = db.execute(
            "SELECT id FROM historical_eras WHERE slug = 'revolutionary'"
        ).fetchone()[0]
        add_site_category(db, "site_eras", site_id, era_id, rank=1, confidence=0.95)
        rows = db.execute(
            "SELECT * FROM site_eras WHERE site_id = ?", (site_id,)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["rank"] == 1
        assert rows[0]["confidence"] == 0.95

    def test_add_event_nature(self, db):
        site_id = upsert_site(db, {"name": "Test", "state": "PA"})
        event_id = db.execute(
            "SELECT id FROM event_natures WHERE slug = 'political'"
        ).fetchone()[0]
        add_site_category(db, "site_events", site_id, event_id, rank=1, confidence=0.9)
        rows = db.execute(
            "SELECT * FROM site_events WHERE site_id = ?", (site_id,)
        ).fetchall()
        assert len(rows) == 1

    def test_junction_idempotent(self, db):
        site_id = upsert_site(db, {"name": "Test", "state": "PA"})
        era_id = db.execute(
            "SELECT id FROM historical_eras WHERE slug = 'civil-war'"
        ).fetchone()[0]
        add_site_category(db, "site_eras", site_id, era_id)
        add_site_category(db, "site_eras", site_id, era_id)
        count = db.execute(
            "SELECT COUNT(*) FROM site_eras WHERE site_id = ?", (site_id,)
        ).fetchone()[0]
        assert count == 1


class TestSiteSources:
    def test_add_source(self, db):
        site_id = upsert_site(db, {"name": "Test", "state": "PA"})
        add_site_source(
            db,
            site_id,
            {
                "source_name": "arcgis",
                "source_record_id": "12345",
                "source_url": "https://example.com",
                "raw_data": {"ResName": "Test"},
            },
        )
        rows = db.execute(
            "SELECT * FROM site_sources WHERE site_id = ?", (site_id,)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["source_name"] == "arcgis"


class TestPipelineTracking:
    def test_pipeline_run_lifecycle(self, db):
        run_id = start_pipeline_run(db, "ingest")
        complete_pipeline_run(db, run_id, records_processed=2600)
        row = db.execute(
            "SELECT * FROM pipeline_runs WHERE id = ?", (run_id,)
        ).fetchone()
        assert row["status"] == "completed"
        assert row["records_processed"] == 2600

    def test_pipeline_run_error(self, db):
        run_id = start_pipeline_run(db, "enrich")
        complete_pipeline_run(db, run_id, 0, status="failed", error_message="API error")
        row = db.execute(
            "SELECT * FROM pipeline_runs WHERE id = ?", (run_id,)
        ).fetchone()
        assert row["status"] == "failed"
        assert row["error_message"] == "API error"
