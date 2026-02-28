"""Tests for nomination fetcher and extractor."""

import sqlite3

import pytest

from src.db.queries import upsert_site
from src.db.schema import create_tables, seed_categories
from src.ingest.nomination_extractor import (
    NominationData,
    store_extraction,
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


class TestNominationData:
    def test_model_creation(self):
        data = NominationData(
            period_start_year=1732,
            period_end_year=1799,
            areas_of_significance=["architecture", "politics-government"],
            criteria=["A", "C"],
            statement_of_significance="Important building",
            extraction_confidence=0.92,
        )
        assert data.period_start_year == 1732
        assert len(data.areas_of_significance) == 2
        assert data.extraction_confidence == 0.92

    def test_model_defaults(self):
        data = NominationData()
        assert data.period_start_year is None
        assert data.areas_of_significance == []
        assert data.criteria == []
        assert data.extraction_confidence == 0.0

    def test_model_serialization(self):
        data = NominationData(
            period_start_year=1861,
            criteria=["A"],
            areas_of_significance=["military"],
        )
        d = data.model_dump()
        assert d["period_start_year"] == 1861
        assert "military" in d["areas_of_significance"]


class TestStoreExtraction:
    def test_store_full_extraction(self, db):
        site_id = upsert_site(db, {"name": "Test Site", "nris_refnum": "12345", "state": "PA"})
        nomination = NominationData(
            period_start_year=1732,
            period_end_year=1799,
            areas_of_significance=["architecture", "politics-government"],
            criteria=["A", "C"],
            statement_of_significance="A very significant building",
            condition="Good",
            extraction_confidence=0.9,
        )
        store_extraction(db, site_id, nomination, "claude_pdf")

        # Check period was stored
        periods = db.execute(
            "SELECT * FROM nrhp_periods_of_significance WHERE site_id = ?", (site_id,)
        ).fetchall()
        assert len(periods) == 1
        assert periods[0]["start_year"] == 1732

        # Check areas were stored
        areas = db.execute(
            "SELECT * FROM nrhp_areas_of_significance WHERE site_id = ?", (site_id,)
        ).fetchall()
        assert len(areas) == 2

        # Check criteria were stored
        criteria = db.execute(
            "SELECT * FROM nrhp_criteria WHERE site_id = ?", (site_id,)
        ).fetchall()
        assert len(criteria) == 2

        # Check site was updated
        site = dict(db.execute("SELECT * FROM sites WHERE id = ?", (site_id,)).fetchone())
        assert site["source_nomination"] == 1
        assert site["full_description"] == "A very significant building"
        assert site["condition"] == "Good"

    def test_store_null_extraction(self, db):
        site_id = upsert_site(db, {"name": "Test", "nris_refnum": "99999", "state": "VA"})
        store_extraction(db, site_id, None, "manual_needed")

        site = dict(db.execute("SELECT * FROM sites WHERE id = ?", (site_id,)).fetchone())
        assert site["source_nomination"] == 1

    def test_store_partial_extraction(self, db):
        site_id = upsert_site(db, {"name": "Test", "nris_refnum": "88888", "state": "NY"})
        nomination = NominationData(
            criteria=["B"],
            statement_of_significance="Associated with a significant person",
            extraction_confidence=0.6,
        )
        store_extraction(db, site_id, nomination, "ocr_then_claude")

        criteria = db.execute(
            "SELECT * FROM nrhp_criteria WHERE site_id = ?", (site_id,)
        ).fetchall()
        assert len(criteria) == 1
        assert criteria[0]["criterion"] == "B"
