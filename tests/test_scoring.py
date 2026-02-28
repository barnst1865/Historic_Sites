"""Tests for confidence scoring and review queue."""

import sqlite3

import pytest

from src.db.schema import create_tables, seed_categories
from src.db.queries import (
    add_nrhp_area,
    add_nrhp_criterion,
    add_nrhp_period,
    add_site_category,
    upsert_site,
)
from src.scoring.confidence import (
    _score_data_completeness,
    _score_description_richness,
    _score_name_specificity,
    _score_source_agreement,
    calculate_confidence,
    run_scoring,
)
from src.scoring.review_queue import (
    approve_site,
    get_review_queue,
    get_review_stats,
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


class TestIndividualFactors:
    def test_data_completeness_full(self):
        site = {
            "latitude": 39.95, "longitude": -75.15, "state": "PA",
            "address": "520 Chestnut", "city": "Philadelphia",
            "date_constructed": "1753", "nhl_designation_date": "1960-10-15",
        }
        assert _score_data_completeness(site) == 1.0

    def test_data_completeness_partial(self):
        site = {"state": "PA", "latitude": 39.95, "longitude": -75.15}
        score = _score_data_completeness(site)
        assert 0.0 < score < 1.0

    def test_description_richness_rich(self):
        site = {"full_description": " ".join(["word"] * 150)}
        assert _score_description_richness(site) == 1.0

    def test_description_richness_poor(self):
        site = {}
        assert _score_description_richness(site) == 0.1

    def test_name_specificity_specific(self):
        site = {"name": "Independence Hall"}
        assert _score_name_specificity(site) == 1.0

    def test_name_specificity_generic(self):
        site = {"name": "Historic District"}
        assert _score_name_specificity(site) == 0.2

    def test_source_agreement_multi(self):
        site = {"source_arcgis": True, "source_spreadsheet": True, "source_nps_parks": True}
        assert _score_source_agreement(site) == 0.8

    def test_source_agreement_single(self):
        site = {"source_arcgis": True}
        assert _score_source_agreement(site) == 0.3


class TestCompositeScore:
    def test_well_documented_site(self, db):
        site_id = upsert_site(db, {
            "name": "Independence Hall",
            "state": "PA",
            "city": "Philadelphia",
            "address": "520 Chestnut St",
            "latitude": 39.95,
            "longitude": -75.15,
            "date_constructed": "1753",
            "nhl_designation_date": "1960-10-15",
            "full_description": " ".join(["significant"] * 100),
            "source_arcgis": True,
            "source_spreadsheet": True,
            "source_nps_parks": True,
            "source_nomination": True,
        })
        add_nrhp_criterion(db, site_id, "A", "spreadsheet")
        add_nrhp_criterion(db, site_id, "C", "spreadsheet")
        add_nrhp_area(db, site_id, "architecture", "spreadsheet")
        add_nrhp_area(db, site_id, "politics-government", "spreadsheet")
        add_nrhp_period(db, site_id, 1732, 1799, "nomination")

        era_id = db.execute(
            "SELECT id FROM historical_eras WHERE slug = 'revolutionary'"
        ).fetchone()["id"]
        add_site_category(db, "site_eras", site_id, era_id, rank=1, confidence=0.95)

        db.commit()
        site = dict(db.execute("SELECT * FROM sites WHERE id = ?", (site_id,)).fetchone())
        score, factors = calculate_confidence(db, site)

        assert score >= 0.7  # Well-documented site should score high
        assert factors["data_completeness"] == 1.0
        assert factors["nrhp_official_data"] == 1.0

    def test_poorly_documented_site(self, db):
        site_id = upsert_site(db, {
            "name": "Historic District",
            "source_spreadsheet": True,
        })
        db.commit()
        site = dict(db.execute("SELECT * FROM sites WHERE id = ?", (site_id,)).fetchone())
        score, factors = calculate_confidence(db, site)

        assert score < 0.5  # Poorly documented site should score low
        assert factors["name_specificity"] == 0.2


class TestRunScoring:
    def test_scoring_assigns_statuses(self, db):
        # High-quality site
        upsert_site(db, {
            "name": "Good Site",
            "state": "PA",
            "latitude": 40.0,
            "longitude": -75.0,
            "date_constructed": "1800",
            "nhl_designation_date": "1960-01-01",
            "full_description": " ".join(["word"] * 100),
            "source_arcgis": True,
            "source_spreadsheet": True,
            "source_nps_parks": True,
            "source_nomination": True,
        })
        # Low-quality site
        upsert_site(db, {"name": "Site"})
        db.commit()

        stats = run_scoring(db)
        assert stats["scored"] == 2
        assert stats["scored"] == stats["auto_approved"] + stats["unreviewed"] + stats["flagged"]


class TestReviewQueue:
    def test_get_review_stats(self, db):
        upsert_site(db, {"name": "Test1"})
        upsert_site(db, {"name": "Test2"})
        db.commit()

        stats = get_review_stats(db)
        assert "unreviewed" in stats

    def test_approve_site(self, db):
        site_id = upsert_site(db, {"name": "Test"})
        db.execute(
            "UPDATE sites SET review_status = 'flagged', review_priority = 1 WHERE id = ?",
            (site_id,),
        )
        db.commit()

        approve_site(db, site_id, notes="Looks correct")
        site = dict(db.execute("SELECT * FROM sites WHERE id = ?", (site_id,)).fetchone())
        assert site["review_status"] == "approved"
        assert site["reviewer_notes"] == "Looks correct"
