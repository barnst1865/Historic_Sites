"""
Official NRHP taxonomy: Areas of Significance and Criteria A-D.

These are the authoritative classification categories used by the National Park Service
for the National Register of Historic Places. Source data from nominations and
spreadsheets uses these exact categories.

Reference: National Register Bulletin 15 — "How to Apply the National Register
Criteria for Evaluation"
"""

# The 31 standard NRHP Areas of Significance
# Used in nrhp_areas_of_significance table, keyed by slug
AREAS_OF_SIGNIFICANCE = [
    {"name": "Agriculture", "slug": "agriculture"},
    {"name": "Architecture", "slug": "architecture"},
    {"name": "Archaeology", "slug": "archaeology"},
    {"name": "Art", "slug": "art"},
    {"name": "Commerce", "slug": "commerce"},
    {"name": "Communications", "slug": "communications"},
    {"name": "Community Planning and Development", "slug": "community-planning"},
    {"name": "Conservation", "slug": "conservation"},
    {"name": "Economics", "slug": "economics"},
    {"name": "Education", "slug": "education"},
    {"name": "Engineering", "slug": "engineering"},
    {"name": "Entertainment/Recreation", "slug": "entertainment-recreation"},
    {"name": "Ethnic Heritage", "slug": "ethnic-heritage"},
    {"name": "Exploration/Settlement", "slug": "exploration-settlement"},
    {"name": "Health/Medicine", "slug": "health-medicine"},
    {"name": "Industry", "slug": "industry"},
    {"name": "Invention", "slug": "invention"},
    {"name": "Landscape Architecture", "slug": "landscape-architecture"},
    {"name": "Law", "slug": "law"},
    {"name": "Literature", "slug": "literature"},
    {"name": "Maritime History", "slug": "maritime-history"},
    {"name": "Military", "slug": "military"},
    {"name": "Performing Arts", "slug": "performing-arts"},
    {"name": "Philosophy", "slug": "philosophy"},
    {"name": "Politics/Government", "slug": "politics-government"},
    {"name": "Religion", "slug": "religion"},
    {"name": "Science", "slug": "science"},
    {"name": "Social History", "slug": "social-history"},
    {"name": "Transportation", "slug": "transportation"},
    {"name": "Other", "slug": "other"},
]

# NRHP Criteria for Evaluation
# A site is listed under one or more of these criteria
CRITERIA = {
    "A": "Associated with events that have made a significant contribution to the broad "
    "patterns of our history.",
    "B": "Associated with the lives of persons significant in our past.",
    "C": "Embody the distinctive characteristics of a type, period, or method of "
    "construction, or represent the work of a master, or possess high artistic values, "
    "or represent a significant and distinguishable entity whose components may lack "
    "individual distinction.",
    "D": "Have yielded, or may be likely to yield, information important in prehistory "
    "or history.",
}

# Valid NRHP resource types (from the NPS spreadsheet)
RESOURCE_TYPES = [
    "Building",
    "District",
    "Object",
    "Site",
    "Structure",
]

# Valid designation types for site_designations table
DESIGNATION_TYPES = [
    "Federal NHL",
    "Federal NRHP",
    "State Register",
    "Local Landmark",
    "Tribal",
    "NPS Unit",
    "Private/NGO",
]

# Name suffixes to strip during entity resolution
# These are common suffixes in official NPS names that create false negatives in fuzzy matching
NAME_SUFFIXES_TO_STRIP = [
    "National Historic Landmark",
    "National Historic Site",
    "National Historical Park",
    "National Monument",
    "National Memorial",
    "National Battlefield",
    "National Military Park",
    "National Seashore",
    "National Lakeshore",
    "National Recreation Area",
    "National Preserve",
    "National Park",
    "Historic Site",
    "Historic District",
    "Historic Park",
    "NHL",
    "NHS",
    "NHP",
    "NM",
    "NMP",
    "NB",
]
