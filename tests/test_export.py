"""Tests for export modules: KML, GeoJSON, Folium map, CSV."""

import json
import sqlite3
from pathlib import Path

import pytest

from src.db.schema import create_tables, seed_categories
from src.db.queries import add_designation, upsert_site
from src.export.kml_exporter import export_by_state, export_master_kmz
from src.export.geojson_exporter import export_all_sites, export_nhls, _site_to_feature
from src.export.folium_map import generate_map, _popup_html
from src.export.csv_exporter import export_review_csv, export_full_csv


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
def db_with_sites(db):
    """DB with sample sites for export testing."""
    s1 = upsert_site(db, {
        "name": "Independence Hall",
        "nris_refnum": "66000661",
        "state": "PA",
        "city": "Philadelphia",
        "latitude": 39.9489,
        "longitude": -75.1500,
        "short_description": "Where the Declaration of Independence was signed",
        "nhl_designation_date": "1960-10-15",
        "public_access": "Yes",
        "website_url": "https://www.nps.gov/inde",
    })
    add_designation(db, s1, {
        "designation_type": "Federal NHL",
        "source": "test",
    })

    s2 = upsert_site(db, {
        "name": "Gettysburg",
        "nris_refnum": "66000614",
        "state": "PA",
        "city": "Gettysburg",
        "latitude": 39.8131,
        "longitude": -77.2311,
        "short_description": "Civil War battlefield",
    })
    add_designation(db, s2, {
        "designation_type": "Federal NHL",
        "source": "test",
    })

    s3 = upsert_site(db, {
        "name": "Mount Vernon",
        "nris_refnum": "66000834",
        "state": "VA",
        "latitude": 38.7070,
        "longitude": -77.0861,
    })

    db.commit()
    return db


class TestGeoJSON:
    def test_site_to_feature(self):
        site = {
            "id": 1,
            "name": "Test Site",
            "nris_refnum": "12345",
            "state": "PA",
            "latitude": 39.95,
            "longitude": -75.15,
        }
        feature = _site_to_feature(site)
        assert feature["type"] == "Feature"
        assert feature["geometry"]["type"] == "Point"
        # GeoJSON uses [lon, lat] order
        assert feature["geometry"]["coordinates"] == [-75.15, 39.95]
        assert feature["properties"]["name"] == "Test Site"

    def test_export_all_sites(self, db_with_sites, tmp_path):
        import src.export.geojson_exporter as mod
        original = mod.GEOJSON_DIR
        mod.GEOJSON_DIR = tmp_path
        try:
            path = export_all_sites(db_with_sites)
            assert path.exists()
            with open(path) as f:
                data = json.load(f)
            assert data["type"] == "FeatureCollection"
            assert len(data["features"]) == 3
        finally:
            mod.GEOJSON_DIR = original

    def test_export_nhls(self, db_with_sites, tmp_path):
        import src.export.geojson_exporter as mod
        original = mod.GEOJSON_DIR
        mod.GEOJSON_DIR = tmp_path
        try:
            path = export_nhls(db_with_sites)
            assert path.exists()
            with open(path) as f:
                data = json.load(f)
            assert len(data["features"]) == 2  # Only NHLs with designation
        finally:
            mod.GEOJSON_DIR = original


class TestKML:
    def test_export_by_state(self, db_with_sites, tmp_path):
        import src.export.kml_exporter as mod
        original = mod.KML_DIR
        mod.KML_DIR = tmp_path
        try:
            files = export_by_state(db_with_sites)
            assert len(files) == 2  # PA and VA
            for f in files:
                assert f.exists()
                assert f.suffix == ".kml"
        finally:
            mod.KML_DIR = original

    def test_export_master_kmz(self, db_with_sites, tmp_path):
        import src.export.kml_exporter as mod
        original = mod.KML_DIR
        mod.KML_DIR = tmp_path
        try:
            path = export_master_kmz(db_with_sites)
            assert path.exists()
            assert path.suffix == ".kmz"
            assert path.stat().st_size > 0
        finally:
            mod.KML_DIR = original


class TestFoliumMap:
    def test_generate_map(self, db_with_sites, tmp_path):
        import src.export.folium_map as mod
        original = mod.MAP_DIR
        mod.MAP_DIR = tmp_path
        try:
            path = generate_map(db_with_sites)
            assert path.exists()
            content = path.read_text()
            assert "Independence Hall" in content
            assert "leaflet" in content.lower()
        finally:
            mod.MAP_DIR = original

    def test_popup_html(self):
        site = {
            "name": "Test Site",
            "city": "Philadelphia",
            "state": "PA",
            "short_description": "A historic place",
            "public_access": "Yes",
            "website_url": "https://example.com",
        }
        html = _popup_html(site)
        assert "Test Site" in html
        assert "Philadelphia" in html
        assert "example.com" in html


class TestCSV:
    def test_export_review_csv(self, db_with_sites, tmp_path):
        import src.export.csv_exporter as mod
        original_dir = mod.OUTPUT_DIR
        mod.OUTPUT_DIR = tmp_path
        try:
            # Flag a site for review
            db_with_sites.execute(
                "UPDATE sites SET review_status = 'flagged', review_priority = 1 "
                "WHERE name = 'Mount Vernon'"
            )
            db_with_sites.commit()

            path = export_review_csv(db_with_sites)
            assert path.exists()
            content = path.read_text()
            assert "Mount Vernon" in content
        finally:
            mod.OUTPUT_DIR = original_dir

    def test_export_full_csv(self, db_with_sites, tmp_path):
        import src.export.csv_exporter as mod
        original_dir = mod.OUTPUT_DIR
        mod.OUTPUT_DIR = tmp_path
        try:
            path = export_full_csv(db_with_sites)
            assert path.exists()
            lines = path.read_text().strip().split("\n")
            assert len(lines) == 4  # Header + 3 sites
        finally:
            mod.OUTPUT_DIR = original_dir
