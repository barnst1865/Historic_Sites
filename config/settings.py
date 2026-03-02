"""
Project settings: paths, API URLs, thresholds, and data source configuration.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Project Paths ---
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
NOMINATIONS_DIR = DATA_DIR / "nominations"
OUTPUT_DIR = PROJECT_ROOT / "output"
GEOPACKAGE_PATH = DATA_DIR / "historic_sites.gpkg"

# Ensure directories exist
for d in [RAW_DIR, NOMINATIONS_DIR, OUTPUT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# --- API Keys ---
NPS_API_KEY = os.getenv("NPS_API_KEY", "")

# --- ArcGIS REST API ---
# NRHP spatial data service — Layer 0 is point locations
ARCGIS_BASE_URL = (
    "https://mapservices.nps.gov/arcgis/rest/services/"
    "cultural_resources/nrhp_locations/MapServer/0/query"
)
ARCGIS_PAGE_SIZE = 1000  # Max records per request
ARCGIS_NHL_FILTER = "Is_NHL = 'X'"  # NHL indicator value

# --- NPS Parks API ---
NPS_API_BASE_URL = "https://developer.nps.gov/api/v1"
NPS_API_RATE_LIMIT = 1000  # requests per hour
NPS_API_PAGE_SIZE = 50  # results per page

# --- NPGallery / NARA ---
# Post-2013 nominations
NPGALLERY_BASE_URL = "https://npgallery.nps.gov/NRHP"
# Pre-2013 via National Archives
NARA_BASE_URL = "https://catalog.archives.gov/api/v2"

# --- Census Bureau Geocoder ---
CENSUS_GEOCODER_URL = (
    "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
)
CENSUS_BATCH_SIZE = 10000  # Max addresses per batch

# --- Nominatim (OpenStreetMap) ---
NOMINATIM_USER_AGENT = "HistoricSitesDB/0.1 (research project)"
NOMINATIM_RATE_LIMIT = 1.0  # seconds between requests

# --- AI Enrichment (via Claude Code CLI) ---
ENRICHMENT_MODEL = "sonnet"
CLAUDE_CLI_TIMEOUT = 120  # seconds for subprocess timeout
ENRICHMENT_BATCH_SIZE_RICH = 10  # Sites per call for data-rich records
ENRICHMENT_BATCH_SIZE_POOR = 1  # Sites per call for data-poor records
ENRICHMENT_DESCRIPTION_RICH_THRESHOLD = 50  # Words for "data-rich" cutoff
ENRICHMENT_MAX_CONSECUTIVE_FAILURES = 5  # Abort after N consecutive AI failures

# --- Confidence Scoring Thresholds ---
SCORE_AUTO_APPROVE = 0.8
SCORE_FLAG_REVIEW = 0.5

# --- Entity Resolution ---
FUZZY_MATCH_THRESHOLD = 85  # thefuzz token_sort_ratio minimum
FUZZY_MATCH_CANDIDATE = 70  # Lower threshold for logging candidates
GEO_PROXIMITY_KM = 0.5  # Max distance for geographic proximity match

# --- US Bounding Box (including AK, HI, territories) ---
US_LAT_MIN = 17.9
US_LAT_MAX = 71.4
US_LON_MIN = -180.0
US_LON_MAX = -64.5

# --- Data Sources Registry ---
# Each source has: name, description, active status, priority (lower = higher authority)
DATA_SOURCES = {
    "arcgis": {
        "name": "NRHP ArcGIS REST API",
        "description": "NPS spatial data service for NRHP locations",
        "active": True,
        "priority": 2,  # Best for coordinates
    },
    "nhl_spreadsheet": {
        "name": "NHL Spreadsheet (NPS)",
        "description": "Official NHL list from NPS data downloads",
        "active": True,
        "priority": 1,  # Authoritative federal list
    },
    "nrhp_spreadsheet": {
        "name": "Full NRHP Spreadsheet (NPS)",
        "description": "Complete NRHP listing from NPS data downloads",
        "active": False,  # Phase 9
        "priority": 1,
    },
    "nps_parks": {
        "name": "NPS Parks API",
        "description": "NPS developer API for park information",
        "active": True,
        "priority": 3,  # Good for descriptions
    },
    "nominations": {
        "name": "NHL Nomination Documents",
        "description": "PDF nomination documents from NPGallery/NARA",
        "active": True,
        "priority": 1,  # Authoritative for NRHP classification
    },
    "shpo": {
        "name": "State SHPO Data",
        "description": "State Historic Preservation Office ArcGIS/CSV/custom sources",
        "active": True,
        "priority": 4,  # State-level, after federal
    },
}

# --- Field Priority ---
# When merging, which source wins for each field group (lower number = higher priority)
FIELD_PRIORITY = {
    "coordinates": ["arcgis", "nps_parks", "shpo", "nominations"],
    "name": ["nhl_spreadsheet", "arcgis", "nps_parks", "shpo"],
    "description": ["nominations", "nps_parks", "arcgis", "nhl_spreadsheet", "shpo"],
    "nrhp_classification": ["nominations", "nhl_spreadsheet"],
    "dates": ["nhl_spreadsheet", "arcgis", "shpo"],
}
