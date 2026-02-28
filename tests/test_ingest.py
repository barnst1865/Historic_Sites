"""Tests for ingest modules: ArcGIS client, spreadsheet loader, NPS Parks, validator, merger."""

import json
import sqlite3
from pathlib import Path

import pytest

from src.db.schema import create_tables, seed_categories
from src.ingest.arcgis_client import parse_features
from src.ingest.nps_parks_client import _parse_latlong, parse_parks
from src.ingest.validator import (
    normalize_date,
    normalize_state,
    validate_coordinates,
    validate_site,
    find_fuzzy_matches,
    run_validation,
)
from src.ingest.merger import merge_arcgis_records, merge_nps_parks_records

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
def arcgis_features():
    with open(FIXTURES / "arcgis_sample.json") as f:
        return json.load(f)


@pytest.fixture
def nps_parks_data():
    with open(FIXTURES / "nps_parks_sample.json") as f:
        return json.load(f)


class TestArcGISParser:
    def test_parse_features(self, arcgis_features):
        sites = parse_features(arcgis_features)
        assert len(sites) == 3

    def test_independence_hall(self, arcgis_features):
        sites = parse_features(arcgis_features)
        indep = next(s for s in sites if "Independence" in s["name"])
        assert indep["nris_refnum"] == "66000661"
        assert indep["state"] == "PA"
        assert indep["latitude"] == pytest.approx(39.9489, abs=0.01)
        assert indep["longitude"] == pytest.approx(-75.15, abs=0.01)
        assert indep["source_arcgis"] is True

    def test_geometry_mapping(self, arcgis_features):
        """ArcGIS geometry x=longitude, y=latitude."""
        sites = parse_features(arcgis_features)
        mv = next(s for s in sites if "Vernon" in s["name"])
        assert mv["longitude"] == pytest.approx(-77.0861, abs=0.001)
        assert mv["latitude"] == pytest.approx(38.7070, abs=0.001)

    def test_skips_null_geometry(self):
        features = [{"attributes": {"ResName": "Test", "RefNum": "999"}, "geometry": {}}]
        sites = parse_features(features)
        assert len(sites) == 0

    def test_skips_empty_name(self):
        features = [
            {"attributes": {"ResName": "", "RefNum": "999"}, "geometry": {"x": -75, "y": 40}}
        ]
        sites = parse_features(features)
        assert len(sites) == 0


class TestNPSParksParser:
    def test_parse_latlong(self):
        lat, lon = _parse_latlong("lat:39.94746, long:-75.14980")
        assert lat == pytest.approx(39.94746)
        assert lon == pytest.approx(-75.14980)

    def test_parse_latlong_empty(self):
        assert _parse_latlong("") == (None, None)
        assert _parse_latlong(None) == (None, None)

    def test_parse_parks(self, nps_parks_data):
        sites = parse_parks(nps_parks_data)
        assert len(sites) == 3

    def test_independence_park(self, nps_parks_data):
        sites = parse_parks(nps_parks_data)
        inde = next(s for s in sites if s["nps_park_code"] == "inde")
        assert "Independence" in inde["name"]
        assert inde["source_nps_parks"] is True
        assert inde["visiting_hours"] is not None
        assert "Free" in inde["admission_info"]

    def test_yellowstone_fee(self, nps_parks_data):
        sites = parse_parks(nps_parks_data)
        yell = next(s for s in sites if s["nps_park_code"] == "yell")
        assert "$35.00" in yell["admission_info"]


class TestValidator:
    def test_normalize_state_abbreviation(self):
        assert normalize_state("PA") == "PA"
        assert normalize_state("pa") == "PA"

    def test_normalize_state_full_name(self):
        assert normalize_state("Pennsylvania") == "PA"
        assert normalize_state("new york") == "NY"
        assert normalize_state("District of Columbia") == "DC"

    def test_normalize_date_iso(self):
        assert normalize_date("2023-01-15") == "2023-01-15"

    def test_normalize_date_us_format(self):
        assert normalize_date("1/15/2023") == "2023-01-15"
        assert normalize_date("12/31/1999") == "1999-12-31"

    def test_normalize_date_year_only(self):
        assert normalize_date("1776") == "1776"

    def test_normalize_date_none(self):
        assert normalize_date(None) is None
        assert normalize_date("") is None

    def test_validate_coordinates_valid(self):
        result = validate_coordinates(39.95, -75.15)
        assert result["valid"] is True
        assert len(result["warnings"]) == 0

    def test_validate_coordinates_missing(self):
        result = validate_coordinates(None, None)
        assert result["valid"] is False

    def test_validate_coordinates_out_of_bounds(self):
        result = validate_coordinates(0.0, 0.0)
        assert result["valid"] is False

    def test_validate_coordinates_swapped(self):
        # lon in lat position, lat in lon position
        result = validate_coordinates(-75.15, 39.95)
        assert "swapped_lat_lon" in result["warnings"]
        assert result["lat"] == pytest.approx(39.95)
        assert result["lon"] == pytest.approx(-75.15)

    def test_validate_site_normalizes(self):
        site = {
            "name": "Test Site",
            "state": "Pennsylvania",
            "city": "PHILADELPHIA",
            "nrhp_cert_date": "1/15/1966",
            "latitude": 39.95,
            "longitude": -75.15,
        }
        result = validate_site(site)
        assert result["status"] == "pass"
        assert result["site_data"]["state"] == "PA"
        assert result["site_data"]["city"] == "Philadelphia"
        assert result["site_data"]["nrhp_cert_date"] == "1966-01-15"

    def test_run_validation_batch(self):
        sites = [
            {"name": "Good Site", "state": "PA", "latitude": 39.95, "longitude": -75.15},
            {"name": "No Coords", "state": "NY"},
            {"name": "Bad Coords", "state": "VA", "latitude": 0.0, "longitude": 0.0},
        ]
        report = run_validation(sites)
        assert report["passed"] == 1
        assert report["warnings"] >= 0
        assert report["failed"] >= 1

    def test_fuzzy_match_exact(self):
        existing = [
            {"id": 1, "name": "Independence Hall", "latitude": 39.95, "longitude": -75.15},
        ]
        matches = find_fuzzy_matches("Independence Hall", 39.95, -75.15, existing)
        assert len(matches) >= 1
        assert matches[0]["score"] >= 90

    def test_fuzzy_match_with_suffix(self):
        existing = [
            {"id": 1, "name": "Gettysburg National Military Park", "latitude": 39.81, "longitude": -77.23},
        ]
        matches = find_fuzzy_matches("Gettysburg", 39.81, -77.23, existing)
        assert len(matches) >= 1

    def test_fuzzy_match_no_match(self):
        existing = [
            {"id": 1, "name": "Independence Hall", "latitude": 39.95, "longitude": -75.15},
        ]
        matches = find_fuzzy_matches("Mount Rushmore", 43.88, -103.46, existing)
        assert len(matches) == 0


class TestMerger:
    def test_merge_arcgis(self, db, arcgis_features):
        sites = parse_features(arcgis_features)
        stats = merge_arcgis_records(db, sites)
        assert stats["inserted"] == 3
        total = db.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
        assert total == 3

    def test_merge_arcgis_idempotent(self, db, arcgis_features):
        sites = parse_features(arcgis_features)
        merge_arcgis_records(db, sites)
        merge_arcgis_records(db, sites)
        total = db.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
        assert total == 3

    def test_merge_nps_parks_with_matching(self, db, arcgis_features, nps_parks_data):
        # First merge ArcGIS data
        arcgis_sites = parse_features(arcgis_features)
        merge_arcgis_records(db, arcgis_sites)

        # Then merge NPS Parks — should match Gettysburg and Independence
        nps_sites = parse_parks(nps_parks_data)
        stats = merge_nps_parks_records(db, nps_sites)
        assert stats["matched"] >= 1  # At least Gettysburg should match

    def test_source_tracking(self, db, arcgis_features):
        sites = parse_features(arcgis_features)
        merge_arcgis_records(db, sites)
        sources = db.execute("SELECT COUNT(*) FROM site_sources").fetchone()[0]
        assert sources == 3

    def test_pipeline_run_recorded(self, db, arcgis_features):
        sites = parse_features(arcgis_features)
        merge_arcgis_records(db, sites)
        runs = db.execute(
            "SELECT * FROM pipeline_runs WHERE stage = 'merge_arcgis'"
        ).fetchall()
        assert len(runs) == 1
        assert runs[0]["status"] == "completed"
