"""
Canonical category definitions for AI-assisted enrichment.

These categories supplement the official NRHP taxonomy (in nrhp_taxonomy.py)
with our own classification system for historical eras, event natures,
site types, and ownership types.

Each category has:
  - name: Human-readable display name
  - slug: Machine-friendly identifier (used in DB and exports)
  - sort_order: Display ordering (chronological for eras, alphabetical otherwise)
"""

HISTORICAL_ERAS = [
    {"name": "Pre-Columbian", "slug": "pre-columbian", "sort_order": 1},
    {"name": "Colonial (1492-1763)", "slug": "colonial", "sort_order": 2},
    {"name": "Revolutionary (1763-1789)", "slug": "revolutionary", "sort_order": 3},
    {"name": "Early Republic (1789-1830)", "slug": "early-republic", "sort_order": 4},
    {"name": "Antebellum (1830-1860)", "slug": "antebellum", "sort_order": 5},
    {"name": "Civil War (1861-1865)", "slug": "civil-war", "sort_order": 6},
    {
        "name": "Reconstruction & Gilded Age (1865-1900)",
        "slug": "reconstruction-gilded-age",
        "sort_order": 7,
    },
    {"name": "Progressive Era (1900-1917)", "slug": "progressive", "sort_order": 8},
    {"name": "Interwar (1918-1940)", "slug": "interwar", "sort_order": 9},
    {"name": "World War II (1941-1945)", "slug": "wwii", "sort_order": 10},
    {"name": "Postwar & Cold War (1945-1991)", "slug": "postwar-cold-war", "sort_order": 11},
    {"name": "Modern (1991-present)", "slug": "modern", "sort_order": 12},
]

EVENT_NATURES = [
    {"name": "Agricultural", "slug": "agricultural", "sort_order": 1},
    {"name": "Architectural", "slug": "architectural", "sort_order": 2},
    {"name": "Civil Rights", "slug": "civil-rights", "sort_order": 3},
    {"name": "Cultural & Societal", "slug": "cultural-societal", "sort_order": 4},
    {"name": "Economic & Industrial", "slug": "economic-industrial", "sort_order": 5},
    {"name": "Educational", "slug": "educational", "sort_order": 6},
    {"name": "Exploration & Settlement", "slug": "exploration-settlement", "sort_order": 7},
    {"name": "Indigenous Heritage", "slug": "indigenous-heritage", "sort_order": 8},
    {"name": "Literary & Artistic", "slug": "literary-artistic", "sort_order": 9},
    {"name": "Maritime", "slug": "maritime", "sort_order": 10},
    {"name": "Military", "slug": "military", "sort_order": 11},
    {"name": "Political", "slug": "political", "sort_order": 12},
    {"name": "Religious", "slug": "religious", "sort_order": 13},
    {"name": "Science & Technology", "slug": "science-technology", "sort_order": 14},
    {"name": "Transportation", "slug": "transportation", "sort_order": 15},
]

SITE_TYPES = [
    {"name": "Archaeological Site", "slug": "archaeological", "sort_order": 1},
    {"name": "Battlefield", "slug": "battlefield", "sort_order": 2},
    {"name": "Birth/Death Home", "slug": "birth-death-home", "sort_order": 3},
    {"name": "Bridge / Infrastructure", "slug": "bridge-infrastructure", "sort_order": 4},
    {"name": "Camp / Training Area", "slug": "camp-training", "sort_order": 5},
    {"name": "Cemetery", "slug": "cemetery", "sort_order": 6},
    {"name": "Church / Religious Site", "slug": "church-religious", "sort_order": 7},
    {"name": "Fort / Fortification", "slug": "fort-fortification", "sort_order": 8},
    {"name": "Government Building", "slug": "government-building", "sort_order": 9},
    {"name": "Historic Building", "slug": "historic-building", "sort_order": 10},
    {"name": "Historic District", "slug": "historic-district", "sort_order": 11},
    {"name": "Historical Marker / Wayside", "slug": "historical-marker", "sort_order": 12},
    {"name": "Industrial Site", "slug": "industrial", "sort_order": 13},
    {"name": "Monument / Memorial", "slug": "monument-memorial", "sort_order": 14},
    {"name": "Museum / Library", "slug": "museum-library", "sort_order": 15},
    {"name": "Park / Landscape", "slug": "park-landscape", "sort_order": 16},
    {"name": "Residence / Estate", "slug": "residence-estate", "sort_order": 17},
    {"name": "School / University", "slug": "school-university", "sort_order": 18},
    {"name": "Ship / Vessel", "slug": "ship-vessel", "sort_order": 19},
]

OWNERSHIP_TYPES = [
    {"name": "Federal Government", "slug": "federal", "sort_order": 1},
    {"name": "State Government", "slug": "state", "sort_order": 2},
    {"name": "Local Government", "slug": "local", "sort_order": 3},
    {"name": "Private Citizen", "slug": "private", "sort_order": 4},
    {"name": "Commercial / Corporate", "slug": "commercial", "sort_order": 5},
    {"name": "Nonprofit / Organization", "slug": "nonprofit", "sort_order": 6},
    {"name": "Tribal", "slug": "tribal", "sort_order": 7},
    {"name": "Mixed / Multiple", "slug": "mixed", "sort_order": 8},
    {"name": "Unknown", "slug": "unknown", "sort_order": 9},
]

# Mapping from NRHP Areas of Significance to our event_natures
# Used in Stage 7 (AI Enrichment) to derive categories from official data
NRHP_TO_EVENT_NATURE = {
    "agriculture": "agricultural",
    "architecture": "architectural",
    "archaeology": None,  # Not a direct event nature mapping
    "art": "literary-artistic",
    "commerce": "economic-industrial",
    "communications": "science-technology",
    "community-planning": "cultural-societal",
    "conservation": "cultural-societal",
    "economics": "economic-industrial",
    "education": "educational",
    "engineering": "science-technology",
    "entertainment-recreation": "cultural-societal",
    "ethnic-heritage": "indigenous-heritage",  # Context-dependent
    "exploration-settlement": "exploration-settlement",
    "health-medicine": "science-technology",
    "industry": "economic-industrial",
    "invention": "science-technology",
    "landscape-architecture": "architectural",
    "law": "political",
    "literature": "literary-artistic",
    "maritime-history": "maritime",
    "military": "military",
    "performing-arts": "literary-artistic",
    "philosophy": "cultural-societal",
    "politics-government": "political",
    "religion": "religious",
    "science": "science-technology",
    "social-history": "civil-rights",  # Often maps to civil rights; context-dependent
    "transportation": "transportation",
    "other": None,
}

# Year ranges for mapping periods of significance to historical eras
ERA_YEAR_RANGES = {
    "pre-columbian": (None, 1492),
    "colonial": (1492, 1763),
    "revolutionary": (1763, 1789),
    "early-republic": (1789, 1830),
    "antebellum": (1830, 1860),
    "civil-war": (1861, 1865),
    "reconstruction-gilded-age": (1865, 1900),
    "progressive": (1900, 1917),
    "interwar": (1918, 1940),
    "wwii": (1941, 1945),
    "postwar-cold-war": (1945, 1991),
    "modern": (1991, None),
}
