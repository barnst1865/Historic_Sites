"""Tests for geocoding pipeline."""

import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from src.db.queries import get_site_by_id, get_sites_for_geocoding, upsert_site
from src.db.schema import create_tables, seed_categories
from src.geocode.ai_address_lookup import _parse_ai_response, lookup_addresses
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

    @patch("src.ingest.geocoder.Nominatim")
    def test_landmark_quality_with_name(self, mock_nominatim_cls):
        """When no address but name is provided, first try returns landmark quality."""
        mock_geolocator = MagicMock()
        mock_location = MagicMock()
        mock_location.latitude = 39.9489
        mock_location.longitude = -75.1500
        mock_geolocator.geocode.return_value = mock_location
        mock_nominatim_cls.return_value = mock_geolocator

        result = geocode_nominatim_single(
            None, "Philadelphia", "PA", name="Independence Hall"
        )
        assert result is not None
        assert result["quality"] == "landmark"
        assert result["lat"] == pytest.approx(39.9489)

    @patch("src.ingest.geocoder.Nominatim")
    def test_landmark_fallback_to_city_level(self, mock_nominatim_cls):
        """When landmark lookup fails, falls back to city-level."""
        mock_geolocator = MagicMock()
        # First call (landmark) fails, second call (city) succeeds
        mock_city_location = MagicMock()
        mock_city_location.latitude = 40.0
        mock_city_location.longitude = -75.0
        mock_geolocator.geocode.side_effect = [None, mock_city_location]
        mock_nominatim_cls.return_value = mock_geolocator

        result = geocode_nominatim_single(
            None, "Philadelphia", "PA", name="Some Obscure Place"
        )
        assert result is not None
        assert result["quality"] == "city_level"

    @patch("src.ingest.geocoder.Nominatim")
    def test_address_geocode_ignores_name(self, mock_nominatim_cls):
        """When address is provided, name parameter is ignored (address path used)."""
        mock_geolocator = MagicMock()
        mock_location = MagicMock()
        mock_location.latitude = 39.9489
        mock_location.longitude = -75.1500
        mock_geolocator.geocode.return_value = mock_location
        mock_nominatim_cls.return_value = mock_geolocator

        result = geocode_nominatim_single(
            "520 Chestnut St", "Philadelphia", "PA", name="Independence Hall"
        )
        assert result is not None
        assert result["quality"] == "interpolated"


class TestGetSitesForGeocoding:
    def test_includes_city_only_sites(self, db):
        """Sites with city but no address should now be included."""
        upsert_site(db, {"name": "City Only Site", "city": "Boston", "state": "MA"})
        db.commit()

        sites = get_sites_for_geocoding(db)
        assert len(sites) == 1
        assert sites[0]["name"] == "City Only Site"

    def test_excludes_sites_with_coords(self, db):
        """Sites already geocoded should be excluded."""
        upsert_site(db, {
            "name": "Already Geocoded",
            "city": "Boston",
            "state": "MA",
            "latitude": 42.36,
            "longitude": -71.06,
        })
        db.commit()

        sites = get_sites_for_geocoding(db)
        assert len(sites) == 0

    def test_excludes_sites_with_no_location_info(self, db):
        """Sites with no address AND no city should be excluded."""
        upsert_site(db, {"name": "No Location Info", "state": "MA"})
        db.commit()

        sites = get_sites_for_geocoding(db)
        assert len(sites) == 0


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
            site_id: {
                "lat": 39.9489, "lon": -75.15, "quality": "exact", "source": "census_geocoder",
            }
        }
        mock_nominatim.return_value = None

        stats = run_geocoding(db)
        assert stats["census_matched"] == 1

        site = get_site_by_id(db, site_id)
        assert site["latitude"] == pytest.approx(39.9489)
        assert site["geocode_quality"] == "exact"

    @patch("src.ingest.geocoder.time.sleep")
    @patch("src.ingest.geocoder.geocode_census_batch")
    @patch("src.ingest.geocoder.geocode_nominatim_single")
    def test_city_only_sites_get_nominatim(self, mock_nominatim, mock_census, mock_sleep, db):
        """Sites with only city (no address) should skip Census and use Nominatim."""
        site_id = upsert_site(db, {
            "name": "Fort Ticonderoga",
            "city": "Ticonderoga",
            "state": "NY",
        })
        db.commit()

        mock_census.return_value = {}
        mock_nominatim.return_value = {
            "lat": 43.8423, "lon": -73.3890,
            "quality": "landmark", "source": "nominatim",
        }

        stats = run_geocoding(db)
        assert stats["landmark_matched"] == 1

        site = get_site_by_id(db, site_id)
        assert site["latitude"] == pytest.approx(43.8423)
        assert site["geocode_quality"] == "landmark"


class TestAIResponseParsing:
    def test_parse_valid_json_array(self):
        response = json.dumps([
            {
                "site_id": 1,
                "address": "520 Chestnut St",
                "latitude": 39.9489,
                "longitude": -75.15,
                "source_url": "https://www.nps.gov/inde/",
                "confidence": "high",
            }
        ])
        result = _parse_ai_response(response)
        assert result is not None
        assert len(result) == 1
        assert result[0]["site_id"] == 1

    def test_parse_json_with_markdown_fences(self):
        response = (
            '```json\n[{"site_id": 1, "address": null, "latitude": 40.0,'
            ' "longitude": -75.0, "source_url": null, "confidence": "low"}]\n```'
        )
        result = _parse_ai_response(response)
        assert result is not None
        assert len(result) == 1

    def test_parse_empty_response(self):
        assert _parse_ai_response("") is None
        assert _parse_ai_response(None) is None

    def test_parse_invalid_json(self):
        assert _parse_ai_response("not json at all") is None

    def test_parse_json_with_surrounding_text(self):
        response = (
            'Here are the results:\n[{"site_id": 42, "address": "123 Main St",'
            ' "latitude": 39.0, "longitude": -75.0, "source_url": null,'
            ' "confidence": "medium"}]\nDone!'
        )
        result = _parse_ai_response(response)
        assert result is not None
        assert result[0]["site_id"] == 42

    def test_parse_null_values(self):
        response = json.dumps([
            {
                "site_id": 5,
                "address": None,
                "latitude": None,
                "longitude": None,
                "source_url": None,
                "confidence": "low",
            }
        ])
        result = _parse_ai_response(response)
        assert result is not None
        assert result[0]["latitude"] is None


class TestAILookup:
    @patch("src.geocode.ai_address_lookup.call_claude")
    def test_lookup_with_no_sites(self, mock_claude, db):
        """Empty batch should complete without calling Claude."""
        stats = lookup_addresses(db)
        assert stats["total"] == 0
        mock_claude.assert_not_called()

    @patch("src.geocode.ai_address_lookup.call_claude")
    def test_lookup_applies_valid_result(self, mock_claude, db):
        """Valid AI results should update the database."""
        site_id = upsert_site(db, {
            "name": "Fort Ticonderoga",
            "city": "Ticonderoga",
            "state": "NY",
        })
        db.commit()

        mock_claude.return_value = json.dumps([{
            "site_id": site_id,
            "address": "102 Fort Ti Rd",
            "latitude": 43.8423,
            "longitude": -73.389,
            "source_url": "https://www.nps.gov/",
            "confidence": "high",
        }])

        stats = lookup_addresses(db)
        assert stats["geocoded"] == 1

        site = get_site_by_id(db, site_id)
        assert site["latitude"] == pytest.approx(43.8423)
        assert site["address"] == "102 Fort Ti Rd"
        assert site["geocode_quality"] == "ai_lookup"

    @patch("src.geocode.ai_address_lookup.call_claude")
    def test_lookup_rejects_invalid_coords(self, mock_claude, db):
        """AI results with invalid coordinates should be skipped."""
        site_id = upsert_site(db, {
            "name": "Bad Coords Site",
            "city": "Somewhere",
            "state": "XX",
        })
        db.commit()

        mock_claude.return_value = json.dumps([{
            "site_id": site_id,
            "address": None,
            "latitude": 999.0,
            "longitude": -999.0,
            "source_url": None,
            "confidence": "low",
        }])

        stats = lookup_addresses(db)
        assert stats["geocoded"] == 0
        assert stats["skipped"] == 1

        site = get_site_by_id(db, site_id)
        assert site["latitude"] is None

    @patch("src.geocode.ai_address_lookup.call_claude")
    def test_lookup_handles_claude_failure(self, mock_claude, db):
        """When Claude returns None, sites should be marked as failed."""
        upsert_site(db, {
            "name": "Test Site",
            "city": "TestCity",
            "state": "TS",
        })
        db.commit()

        mock_claude.return_value = None

        stats = lookup_addresses(db)
        assert stats["failed"] == 1
        assert stats["geocoded"] == 0

    @patch("src.geocode.ai_address_lookup.call_claude")
    def test_lookup_respects_limit(self, mock_claude, db):
        """Limit parameter should cap the number of sites processed."""
        for i in range(5):
            upsert_site(db, {
                "name": f"Site {i}",
                "nris_refnum": f"REF{i:04d}",
                "city": "TestCity",
                "state": "TS",
            })
        db.commit()

        mock_claude.return_value = json.dumps([{
            "site_id": 1,
            "address": None,
            "latitude": 40.0,
            "longitude": -75.0,
            "source_url": None,
            "confidence": "medium",
        }])

        stats = lookup_addresses(db, limit=2)
        assert stats["total"] == 2
