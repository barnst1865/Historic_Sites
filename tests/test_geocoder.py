"""Tests for geocoding pipeline."""

import sqlite3
from unittest.mock import patch, MagicMock

import pytest

from src.db.schema import create_tables, seed_categories
from src.db.queries import upsert_site, get_site_by_id
from src.ingest.geocoder import (
    _build_census_batch,
    geocode_nominatim_single,
    run_geocoding,
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


class TestCensusBatch:
    def test_build_batch_csv(self):
        sites = [
            {"id": 1, "address": "520 Chestnut St", "city": "Philadelphia", "state": "PA"},
            {"id": 2, "address": "1600 Pennsylvania Ave", "city": "Washington", "state": "DC"},
        ]
        csv_text = _build_census_batch(sites)
        assert "520 Chestnut St" in csv_text
        assert "1600 Pennsylvania Ave" in csv_text
        lines = csv_text.strip().split("\n")
        assert len(lines) == 2

    def test_build_batch_handles_missing_fields(self):
        sites = [
            {"id": 1, "city": "Boston", "state": "MA"},  # No address
        ]
        csv_text = _build_census_batch(sites)
        assert "Boston" in csv_text


class TestNominatimGeocode:
    @patch("src.ingest.geocoder.Nominatim")
    def test_successful_geocode(self, mock_nominatim_cls):
        mock_geolocator = MagicMock()
        mock_location = MagicMock()
        mock_location.latitude = 39.9489
        mock_location.longitude = -75.1500
        mock_geolocator.geocode.return_value = mock_location
        mock_nominatim_cls.return_value = mock_geolocator

        result = geocode_nominatim_single("520 Chestnut St", "Philadelphia", "PA")
        assert result is not None
        assert result["lat"] == pytest.approx(39.9489)
        assert result["lon"] == pytest.approx(-75.15)
        assert result["source"] == "nominatim"

    @patch("src.ingest.geocoder.Nominatim")
    def test_no_result(self, mock_nominatim_cls):
        mock_geolocator = MagicMock()
        mock_geolocator.geocode.return_value = None
        mock_nominatim_cls.return_value = mock_geolocator

        result = geocode_nominatim_single("Nonexistent Place", None, "ZZ")
        assert result is None

    @patch("src.ingest.geocoder.Nominatim")
    def test_city_level_quality(self, mock_nominatim_cls):
        mock_geolocator = MagicMock()
        mock_location = MagicMock()
        mock_location.latitude = 40.0
        mock_location.longitude = -75.0
        mock_geolocator.geocode.return_value = mock_location
        mock_nominatim_cls.return_value = mock_geolocator

        result = geocode_nominatim_single(None, "Philadelphia", "PA")
        assert result is not None
        assert result["quality"] == "city_level"


class TestRunGeocoding:
    def test_no_sites_needing_geocoding(self, db):
        # Insert site with coordinates already
        upsert_site(db, {
            "name": "Test",
            "state": "PA",
            "latitude": 39.95,
            "longitude": -75.15,
        })
        db.commit()

        stats = run_geocoding(db)
        assert stats["census_matched"] == 0
        assert stats["nominatim_matched"] == 0

    @patch("src.ingest.geocoder.geocode_census_batch")
    @patch("src.ingest.geocoder.geocode_nominatim_single")
    def test_geocode_sites_without_coords(self, mock_nominatim, mock_census, db):
        # Insert site without coordinates but with address
        site_id = upsert_site(db, {
            "name": "Independence Hall",
            "address": "520 Chestnut St",
            "city": "Philadelphia",
            "state": "PA",
        })
        db.commit()

        mock_census.return_value = {
            site_id: {"lat": 39.9489, "lon": -75.15, "quality": "exact", "source": "census_geocoder"}
        }
        mock_nominatim.return_value = None

        stats = run_geocoding(db)
        assert stats["census_matched"] == 1

        site = get_site_by_id(db, site_id)
        assert site["latitude"] == pytest.approx(39.9489)
        assert site["geocode_quality"] == "exact"
