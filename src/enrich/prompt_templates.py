"""
Prompt templates for Claude-based AI enrichment.

Prompts are designed to:
  1. Map NRHP official data (areas of significance, criteria) to our categories first
  2. Have AI fill remaining gaps (site type, ownership, additional eras/events)
  3. Assign rank (1=primary, 2=secondary, 3=tertiary) to each category
"""

SYSTEM_PROMPT = """You are a historian and historic preservation specialist classifying US historic sites.

You will receive site data that may include:
- Official NRHP Areas of Significance and Criteria
- Location (state, city, county)
- Resource type (Building, District, Site, Structure, Object)
- Description text (from nomination documents or other sources)
- Dates (construction, designation)
- Associated persons

Your job is to classify each site into our category system. Categories already derived
from NRHP data will be provided — you should confirm or adjust those, then fill in gaps.

IMPORTANT RULES:
1. Assign rank: 1=primary (what the site is MOST known for), 2=secondary, 3=tertiary
2. Provide confidence (0.0-1.0) for each assignment
3. Be conservative — only assign categories you're reasonably confident about
4. A site should have 1-3 eras, 1-3 event natures, 1 primary site type, and 1-2 ownership types
5. For sites with minimal data, only assign the most obvious categories with lower confidence
"""

CLASSIFICATION_PROMPT = """Classify the following historic site(s) into our category system.

## Category Options

### Historical Eras
pre-columbian, colonial, revolutionary, early-republic, antebellum, civil-war,
reconstruction-gilded-age, progressive, interwar, wwii, postwar-cold-war, modern

### Event Natures
agricultural, architectural, civil-rights, cultural-societal, economic-industrial,
educational, exploration-settlement, indigenous-heritage, literary-artistic, maritime,
military, political, religious, science-technology, transportation

### Site Types
archaeological, battlefield, birth-death-home, bridge-infrastructure, camp-training,
cemetery, church-religious, fort-fortification, government-building, historic-building,
historic-district, historical-marker, industrial, monument-memorial, museum-library,
park-landscape, residence-estate, school-university, ship-vessel

### Ownership Types
federal, state, local, private, commercial, nonprofit, tribal, mixed, unknown

## Sites to Classify

{sites_json}

## Already Derived from NRHP Data (confirm or adjust)

{nrhp_derived}

## Response Format

Return a JSON array with one object per site:
```json
[
  {{
    "site_id": 123,
    "eras": [
      {{"slug": "revolutionary", "rank": 1, "confidence": 0.95}},
      {{"slug": "colonial", "rank": 2, "confidence": 0.7}}
    ],
    "event_natures": [
      {{"slug": "political", "rank": 1, "confidence": 0.9}},
      {{"slug": "architectural", "rank": 2, "confidence": 0.8}}
    ],
    "site_types": [
      {{"slug": "government-building", "rank": 1, "confidence": 0.95}}
    ],
    "ownership": [
      {{"slug": "federal", "rank": 1, "confidence": 0.9}}
    ]
  }}
]
```"""
