"""Prompt templates for AI-assisted address/coordinate lookup."""

SYSTEM_PROMPT = """\
You are a research assistant helping geocode National Historic Landmarks.
For each site, search reputable sources to find its street address and/or \
geographic coordinates.

Preferred sources (in order of reliability):
1. NPS.gov (National Park Service official pages)
2. Wikipedia articles for the landmark
3. State SHPO (State Historic Preservation Office) websites
4. Local government websites
5. Google Maps / other mapping services

Return ONLY valid JSON — no markdown fences, no commentary."""

USER_PROMPT_TEMPLATE = """\
Find the street address and geographic coordinates for these National Historic \
Landmarks. For each site, search the web using the site name, city, and state.

Sites to look up:
{sites_json}

Return a JSON array with one object per site. Each object must have:
- "site_id": (integer) the site ID from the input
- "address": (string or null) street address if found
- "latitude": (float or null) decimal latitude
- "longitude": (float or null) decimal longitude
- "source_url": (string or null) URL where you found the information
- "confidence": (string) one of "high", "medium", "low"

If you cannot find reliable information for a site, still include it with \
null values and confidence "low".

Example response:
[
  {{
    "site_id": 42,
    "address": "520 Chestnut St",
    "latitude": 39.9489,
    "longitude": -75.1500,
    "source_url": "https://www.nps.gov/inde/",
    "confidence": "high"
  }}
]"""
