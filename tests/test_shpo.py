"""Tests for SHPO adapter, dispatcher, and merge logic."""

import json
import sqlite3
from pathlib import Path

import pytest

from config.state_sources import STATE_SOURCES
from src.db.schema import create_tables, seed_categories
from src.ingest.merger import merge_shpo_records
from src.ingest.shpo_adapters.arcgis_adapter import ArcGISAdapter
from src.ingest.shpo_dispatcher import get_active_states, parse_state

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    create_tables(conn)
    seed_categories(conn)
    yield conn
    conn.close()


@pytest.fixture
def in_features():
    with open(FIXTURES / "shpo_in_sample.json") as f:
        return json.load(f)


@pytest.fixture
def mo_features():
    with open(FIXTURES / "shpo_mo_sample.json") as f:
        return json.load(f)


@pytest.fixture
def ut_features():
    with open(FIXTURES / "shpo_ut_sample.json") as f:
        return json.load(f)


# --- ArcGIS Adapter Tests ---


class TestArcGISAdapter:
    def test_parse_in_features(self, in_features):
        adapter = ArcGISAdapter()
        config = STATE_SOURCES["IN"].copy()
        config["_state_code"] = "IN"
        sites = adapter.parse(in_features["features"], config)
        # 4 features: 2 with name+geometry, 1 empty name, 1 null geometry
        assert len(sites) == 2

    def test_parse_in_field_mapping(self, in_features):
        adapter = ArcGISAdapter()
        config = STATE_SOURCES["IN"].copy()
        config["_state_code"] = "IN"
        sites = adapter.parse(in_features["features"], config)
        farmhouse = next(s for s in sites if "Conner" in s["name"])
        assert farmhouse["state"] == "IN"
        assert farmhouse["source_shpo"] is True
        assert farmhouse["primary_source"] == "shpo_in"
        assert farmhouse["latitude"] == pytest.approx(39.9956, abs=0.01)
        assert farmhouse["longitude"] == pytest.approx(-86.0052, abs=0.01)

    def test_parse_in_skips_null_geometry(self, in_features):
        adapter = ArcGISAdapter()
        config = STATE_SOURCES["IN"].copy()
        config["_state_code"] = "IN"
        sites = adapter.parse(in_features["features"], config)
        names = [s["name"] for s in sites]
        # Governor's Mansion has null geometry
        assert "Indiana Governor's Mansion" not in names

    def test_parse_in_skips_empty_name(self, in_features):
        adapter = ArcGISAdapter()
        config = STATE_SOURCES["IN"].copy()
        config["_state_code"] = "IN"
        sites = adapter.parse(in_features["features"], config)
        # Feature with empty historicname should be skipped
        assert len(sites) == 2
        for site in sites:
            assert site["name"] != ""

    def test_parse_mo_features(self, mo_features):
        adapter = ArcGISAdapter()
        config = STATE_SOURCES["MO"].copy()
        config["_state_code"] = "MO"
        sites = adapter.parse(mo_features["features"], config)
        # 3 features: 2 with name, 1 with empty HST_NAME
        assert len(sites) == 2

    def test_parse_mo_field_mapping(self, mo_features):
        adapter = ArcGISAdapter()
        config = STATE_SOURCES["MO"].copy()
        config["_state_code"] = "MO"
        sites = adapter.parse(mo_features["features"], config)
        school = next(s for s in sites if "Neosho" in s["name"])
        assert school["address"] == "West McCord and North Wood Streets"
        assert school["city"] == "Neosho"
        assert school["state"] == "MO"
        assert school["state_designation_date"] is not None

    def test_parse_mo_date_conversion(self, mo_features):
        adapter = ArcGISAdapter()
        config = STATE_SOURCES["MO"].copy()
        config["_state_code"] = "MO"
        sites = adapter.parse(mo_features["features"], config)
        school = next(s for s in sites if "Neosho" in s["name"])
        # 1030683600000 ms = 2002-08-30
        assert school["state_designation_date"] == "2002-08-30"

    def test_parse_ut_features(self, ut_features):
        adapter = ArcGISAdapter()
        config = STATE_SOURCES["UT"].copy()
        config["_state_code"] = "UT"
        sites = adapter.parse(ut_features["features"], config)
        # 3 features: 2 with name (propertyname or historicpropertyname), 1 with both null
        assert len(sites) == 2

    def test_parse_ut_compound_address(self, ut_features):
        adapter = ArcGISAdapter()
        config = STATE_SOURCES["UT"].copy()
        config["_state_code"] = "UT"
        sites = adapter.parse(ut_features["features"], config)
        beehive = next(s for s in sites if "Beehive" in s["name"])
        assert beehive["address"] == "67 E SOUTH TEMPLE"

    def test_parse_ut_nris_refnum(self, ut_features):
        adapter = ArcGISAdapter()
        config = STATE_SOURCES["UT"].copy()
        config["_state_code"] = "UT"
        sites = adapter.parse(ut_features["features"], config)
        beehive = next(s for s in sites if "Beehive" in s["name"])
        assert beehive["nris_refnum"] == "66000740"


# --- Dispatcher Tests ---


class TestDispatcher:
    def test_get_active_states(self):
        states = get_active_states()
        assert "IN" in states
        assert "MO" in states
        assert "UT" in states

    def test_get_active_states_filtered(self):
        states = get_active_states(filter_states=["IN", "UT"])
        assert states == ["IN", "UT"]

    def test_get_active_states_unknown_ignored(self):
        states = get_active_states(filter_states=["IN", "XX"])
        assert states == ["IN"]

    def test_parse_state_routes_correctly(self, in_features):
        sites = parse_state("IN", in_features["features"])
        assert len(sites) == 2
        assert all(s["state"] == "IN" for s in sites)

    def test_parse_state_unknown_raises(self):
        with pytest.raises(ValueError, match="No SHPO source"):
            parse_state("XX", [])


# --- Merge Tests ---


class TestSHPOMerge:
    def _make_config(self, state_code):
        config = STATE_SOURCES[state_code].copy()
        config["_state_code"] = state_code
        return config

    def test_new_inserts(self, db, in_features):
        adapter = ArcGISAdapter()
        config = self._make_config("IN")
        sites = adapter.parse(in_features["features"], config)
        stats = merge_shpo_records(db, sites, "IN", config)
        assert stats["inserted"] == 2
        total = db.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
        assert total == 2

    def test_source_shpo_flag_set(self, db, in_features):
        adapter = ArcGISAdapter()
        config = self._make_config("IN")
        sites = adapter.parse(in_features["features"], config)
        merge_shpo_records(db, sites, "IN", config)
        row = db.execute(
            "SELECT source_shpo FROM sites WHERE name LIKE '%Conner%'"
        ).fetchone()
        assert row["source_shpo"] == 1

    def test_designations_added(self, db, in_features):
        adapter = ArcGISAdapter()
        config = self._make_config("IN")
        sites = adapter.parse(in_features["features"], config)
        merge_shpo_records(db, sites, "IN", config)
        desigs = db.execute("SELECT COUNT(*) FROM site_designations").fetchone()[0]
        assert desigs >= 2  # One designation per inserted site

    def test_provenance_tracked(self, db, in_features):
        adapter = ArcGISAdapter()
        config = self._make_config("IN")
        sites = adapter.parse(in_features["features"], config)
        merge_shpo_records(db, sites, "IN", config)
        sources = db.execute(
            "SELECT COUNT(*) FROM site_sources WHERE source_name = 'shpo_in'"
        ).fetchone()[0]
        assert sources == 2

    def test_pipeline_run_recorded(self, db, in_features):
        adapter = ArcGISAdapter()
        config = self._make_config("IN")
        sites = adapter.parse(in_features["features"], config)
        merge_shpo_records(db, sites, "IN", config)
        runs = db.execute(
            "SELECT * FROM pipeline_runs WHERE stage = 'merge_shpo_in'"
        ).fetchall()
        assert len(runs) == 1
        assert runs[0]["status"] == "completed"

    def test_nris_match(self, db, ut_features):
        """A SHPO record with nris_refnum should match an existing federal site."""
        # Insert a federal site with the same refnum
        from src.db.queries import upsert_site

        upsert_site(db, {
            "nris_refnum": "66000740",
            "name": "Beehive House",
            "state": "UT",
            "latitude": 40.77,
            "longitude": -111.89,
            "source_arcgis": True,
            "primary_source": "arcgis",
        })
        db.commit()

        adapter = ArcGISAdapter()
        config = self._make_config("UT")
        sites = adapter.parse(ut_features["features"], config)
        stats = merge_shpo_records(db, sites, "UT", config)

        assert stats["matched_nris"] == 1
        # Beehive matched, Old Deseret inserted (no refnum, no existing UT sites to match)
        assert stats["inserted"] == 1

        # Federal data should not be overwritten
        row = db.execute(
            "SELECT primary_source, source_shpo FROM sites WHERE nris_refnum = '66000740'"
        ).fetchone()
        assert row["primary_source"] == "arcgis"  # Not overwritten
        assert row["source_shpo"] == 1  # Flag set

    def test_fuzzy_match(self, db, mo_features):
        """A SHPO record should fuzzy-match an existing site by name + proximity."""
        from src.db.queries import upsert_site

        # Insert an existing site close to the SHPO record
        upsert_site(db, {
            "name": "Neosho High School",
            "state": "MO",
            "latitude": 36.871,
            "longitude": -94.369,
            "primary_source": "arcgis",
        })
        db.commit()

        adapter = ArcGISAdapter()
        config = self._make_config("MO")
        sites = adapter.parse(mo_features["features"], config)
        stats = merge_shpo_records(db, sites, "MO", config)

        assert stats["matched_fuzzy"] == 1
        # Mark Twain inserted as new (no existing match)
        assert stats["inserted"] == 1

    def test_federal_data_not_overwritten(self, db, ut_features):
        """SHPO merge should not overwrite federal data fields."""
        from src.db.queries import upsert_site

        upsert_site(db, {
            "nris_refnum": "66000740",
            "name": "Beehive House",
            "state": "UT",
            "city": "Salt Lake City",
            "address": "67 E South Temple St",
            "latitude": 40.77,
            "longitude": -111.89,
            "primary_source": "arcgis",
        })
        db.commit()

        adapter = ArcGISAdapter()
        config = self._make_config("UT")
        sites = adapter.parse(ut_features["features"], config)
        merge_shpo_records(db, sites, "UT", config)

        row = db.execute(
            "SELECT city, address FROM sites WHERE nris_refnum = '66000740'"
        ).fetchone()
        # Existing federal city/address should not be overwritten
        assert row["city"] == "Salt Lake City"
        assert row["address"] == "67 E South Temple St"

    def test_idempotency(self, db, in_features):
        """Running merge twice should not duplicate records."""
        adapter = ArcGISAdapter()
        config = self._make_config("IN")
        sites = adapter.parse(in_features["features"], config)

        merge_shpo_records(db, sites, "IN", config)
        merge_shpo_records(db, sites, "IN", config)

        total = db.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
        assert total == 2
