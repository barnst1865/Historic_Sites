"""Tests for enrichment and profiling modules."""

import sqlite3

import pytest

from src.db.queries import (
    add_nrhp_area,
    add_nrhp_period,
    upsert_site,
)
from src.db.schema import create_tables, seed_categories
from src.enrich.batch_processor import _is_data_rich
from src.enrich.claude_classifier import (
    derive_eras_from_periods,
    derive_events_from_areas,
    store_classifications,
)
from src.profiling.data_profiler import (
    detect_outliers,
    generate_profile,
    profile_completeness,
    profile_coordinate_coverage,
    profile_description_richness,
)


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    create_tables(conn)
    seed_categories(conn)
    yield conn
    conn.close()


class TestDeriveErasFromPeriods:
    def test_revolutionary_era(self, db):
        site_id = upsert_site(db, {"name": "Test", "state": "PA"})
        add_nrhp_period(db, site_id, 1770, 1790, "spreadsheet")

        eras = derive_eras_from_periods(db, site_id)
        slugs = [e["slug"] for e in eras]
        assert "revolutionary" in slugs

    def test_civil_war_era(self, db):
        site_id = upsert_site(db, {"name": "Battlefield", "state": "PA"})
        add_nrhp_period(db, site_id, 1861, 1865, "nomination")

        eras = derive_eras_from_periods(db, site_id)
        slugs = [e["slug"] for e in eras]
        assert "civil-war" in slugs

    def test_multi_era_span(self, db):
        site_id = upsert_site(db, {"name": "Long History", "state": "VA"})
        add_nrhp_period(db, site_id, 1750, 1900, "nomination")

        eras = derive_eras_from_periods(db, site_id)
        assert len(eras) >= 2  # Should span multiple eras

    def test_no_periods(self, db):
        site_id = upsert_site(db, {"name": "No Period", "state": "NY"})
        eras = derive_eras_from_periods(db, site_id)
        assert eras == []

    def test_ranks_assigned(self, db):
        site_id = upsert_site(db, {"name": "Multi-era", "state": "PA"})
        add_nrhp_period(db, site_id, 1700, 1900, "nomination")

        eras = derive_eras_from_periods(db, site_id)
        if len(eras) > 1:
            assert eras[0]["rank"] == 1
            assert eras[1]["rank"] == 2


class TestDeriveEventsFromAreas:
    def test_military_mapping(self, db):
        site_id = upsert_site(db, {"name": "Fort Test", "state": "VA"})
        add_nrhp_area(db, site_id, "military", "spreadsheet")

        events = derive_events_from_areas(db, site_id)
        slugs = [e["slug"] for e in events]
        assert "military" in slugs

    def test_politics_mapping(self, db):
        site_id = upsert_site(db, {"name": "Capitol", "state": "DC"})
        add_nrhp_area(db, site_id, "politics-government", "spreadsheet")

        events = derive_events_from_areas(db, site_id)
        slugs = [e["slug"] for e in events]
        assert "political" in slugs

    def test_multiple_areas(self, db):
        site_id = upsert_site(db, {"name": "Multi", "state": "PA"})
        add_nrhp_area(db, site_id, "architecture", "spreadsheet")
        add_nrhp_area(db, site_id, "politics-government", "spreadsheet")

        events = derive_events_from_areas(db, site_id)
        assert len(events) == 2

    def test_no_areas(self, db):
        site_id = upsert_site(db, {"name": "Empty", "state": "NY"})
        events = derive_events_from_areas(db, site_id)
        assert events == []


class TestStoreClassifications:
    def test_store_era(self, db):
        site_id = upsert_site(db, {"name": "Test", "state": "PA"})
        classifications = {
            "eras": [{"slug": "revolutionary", "rank": 1, "confidence": 0.9, "source": "ai"}],
            "event_natures": [{"slug": "military", "rank": 1, "confidence": 0.85, "source": "ai"}],
            "site_types": [{"slug": "battlefield", "rank": 1, "confidence": 0.95, "source": "ai"}],
            "ownership": [{"slug": "federal", "rank": 1, "confidence": 0.8, "source": "ai"}],
        }
        store_classifications(db, site_id, classifications)

        eras = db.execute("SELECT * FROM site_eras WHERE site_id = ?", (site_id,)).fetchall()
        assert len(eras) == 1
        assert eras[0]["confidence"] == 0.9

        events = db.execute("SELECT * FROM site_events WHERE site_id = ?", (site_id,)).fetchall()
        assert len(events) == 1

    def test_unknown_slug_skipped(self, db):
        site_id = upsert_site(db, {"name": "Test", "state": "PA"})
        classifications = {
            "eras": [{"slug": "nonexistent-era", "rank": 1, "confidence": 0.5}],
        }
        store_classifications(db, site_id, classifications)
        eras = db.execute("SELECT * FROM site_eras WHERE site_id = ?", (site_id,)).fetchall()
        assert len(eras) == 0


class TestDataRichness:
    def test_rich_site(self):
        assert _is_data_rich({"full_description": " ".join(["word"] * 60)}) is True

    def test_poor_site(self):
        assert _is_data_rich({"full_description": "Short"}) is False

    def test_no_description(self):
        assert _is_data_rich({}) is False


class TestProfiler:
    def test_completeness(self, db):
        upsert_site(db, {"name": "Full", "state": "PA", "latitude": 40.0, "longitude": -75.0})
        upsert_site(db, {"name": "Partial", "state": "NY"})
        db.commit()

        result = profile_completeness(db)
        assert result["name"]["non_null"] == 2
        assert result["latitude"]["non_null"] == 1

    def test_description_richness(self, db):
        upsert_site(db, {"name": "Rich", "full_description": " ".join(["word"] * 100)})
        upsert_site(db, {"name": "Moderate", "short_description": "A few words here"})
        upsert_site(db, {"name": "Poor"})
        db.commit()

        result = profile_description_richness(db)
        assert result["counts"]["data_rich"] == 1
        assert result["counts"]["data_poor"] >= 1

    def test_coordinate_coverage(self, db):
        upsert_site(db, {"name": "Has Coords", "latitude": 40.0, "longitude": -75.0, "state": "PA"})
        upsert_site(db, {"name": "No Coords", "state": "NY"})
        db.commit()

        result = profile_coordinate_coverage(db)
        assert result["with_coordinates"] == 1
        assert result["without_coordinates"] == 1

    def test_detect_outliers_zero_coords(self, db):
        upsert_site(db, {"name": "Zero", "latitude": 0.0, "longitude": -75.0})
        db.commit()

        outliers = detect_outliers(db)
        assert any("zero_coordinate" in o["issue"] for o in outliers)

    def test_generate_full_profile(self, db):
        upsert_site(db, {"name": "Test Site", "state": "PA", "latitude": 40.0, "longitude": -75.0})
        db.commit()

        profile = generate_profile(db)
        assert "completeness" in profile
        assert "summary" in profile
        assert profile["summary"]["total_sites"] == 1
