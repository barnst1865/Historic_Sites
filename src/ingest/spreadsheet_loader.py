"""
NHL/NRHP spreadsheet parser.

Parses the Excel spreadsheets available from NPS data downloads:
  - NHL spreadsheet: ~2,600 National Historic Landmarks
  - NRHP spreadsheet: ~95,000 National Register properties (Phase 9)

Extracts NRHP criteria (A-D), areas of significance, and site metadata.
The spreadsheet is the authoritative federal list — it has records that
may not appear in the ArcGIS layer.
"""

import logging
from pathlib import Path

import pandas as pd

from config.nrhp_taxonomy import AREAS_OF_SIGNIFICANCE

logger = logging.getLogger(__name__)

# Known column name variations across NPS spreadsheet versions
COLUMN_MAP = {
    # NRIS Reference Number
    "RefNum": "nris_refnum",
    "Ref#": "nris_refnum",
    "Reference Number": "nris_refnum",
    "Refnum": "nris_refnum",
    # Name
    "Resource Name": "name",
    "ResName": "name",
    "Property Name": "name",
    "Historic Name": "name",
    # Location
    "Address": "address",
    "City": "city",
    "County": "county",
    "State": "state",
    "ST": "state",
    # Dates
    "NHL Date": "nhl_designation_date",
    "NHL_Date": "nhl_designation_date",
    "Cert Date": "nrhp_cert_date",
    "CertDate": "nrhp_cert_date",
    "Date Listed": "nrhp_cert_date",
}

# Slugified names for matching areas of significance columns
_AREA_SLUGS = {a["name"].lower(): a["slug"] for a in AREAS_OF_SIGNIFICANCE}


def _normalize_column_name(col: str) -> str:
    """Map spreadsheet column names to our schema fields."""
    col_stripped = col.strip()
    if col_stripped in COLUMN_MAP:
        return COLUMN_MAP[col_stripped]
    return col_stripped


def _extract_criteria(row: pd.Series) -> list[str]:
    """Extract NRHP criteria A-D from a spreadsheet row.

    The spreadsheet typically has columns like 'CritA', 'CritB', etc.
    with 'X' or 'Y' marking that the criterion applies.
    """
    criteria = []
    for letter in ["A", "B", "C", "D"]:
        for col_pattern in [f"Crit{letter}", f"Criteria {letter}", f"Criterion{letter}"]:
            if col_pattern in row.index:
                val = str(row[col_pattern]).strip().upper()
                if val in ("X", "Y", "YES", "TRUE", "1"):
                    criteria.append(letter)
                break
    return criteria


def _extract_areas_of_significance(row: pd.Series) -> list[str]:
    """Extract NRHP areas of significance from a spreadsheet row.

    The spreadsheet may have individual columns per area (with X markers)
    or a single delimited column.
    """
    areas = []

    # Check for individual area columns (e.g., "Architecture", "Military")
    for area_name, slug in _AREA_SLUGS.items():
        for col in row.index:
            if col.strip().lower() == area_name:
                val = str(row[col]).strip().upper()
                if val in ("X", "Y", "YES", "TRUE", "1"):
                    areas.append(slug)
                break

    # Check for a combined "Areas of Significance" column
    if not areas:
        for col_name in ["Areas of Significance", "AreaOfSignificance", "AreasOfSig"]:
            if col_name in row.index:
                val = str(row[col_name]).strip()
                if val and val.lower() != "nan":
                    for part in val.replace(";", ",").split(","):
                        part_lower = part.strip().lower()
                        if part_lower in _AREA_SLUGS:
                            areas.append(_AREA_SLUGS[part_lower])

    return areas


def load_spreadsheet(filepath: Path, is_nhl: bool = True) -> list[dict]:
    """Parse an NPS NHL or NRHP spreadsheet into site records.

    Args:
        filepath: Path to the Excel (.xlsx/.xls) file.
        is_nhl: If True, treat all records as NHLs and extract NHL-specific fields.

    Returns:
        List of dicts with 'site_data', 'criteria', 'areas', and 'designation' keys.
    """
    logger.info("Loading spreadsheet: %s", filepath)

    if filepath.suffix in (".xlsx", ".xls"):
        df = pd.read_excel(filepath, dtype=str)
    elif filepath.suffix == ".csv":
        df = pd.read_csv(filepath, dtype=str)
    else:
        raise ValueError(f"Unsupported file format: {filepath.suffix}")

    logger.info("Loaded %d rows, columns: %s", len(df), list(df.columns))

    records = []
    for _, row in df.iterrows():
        # Map columns to our schema
        site_data = {}
        for col in row.index:
            mapped = _normalize_column_name(col)
            if mapped in (
                "nris_refnum", "name", "address", "city", "county", "state",
                "nhl_designation_date", "nrhp_cert_date",
            ):
                val = str(row[col]).strip() if pd.notna(row[col]) else None
                if val and val.lower() != "nan":
                    site_data[mapped] = val

        # Must have a name
        if not site_data.get("name"):
            continue

        # Ensure refnum is string
        if site_data.get("nris_refnum"):
            site_data["nris_refnum"] = str(site_data["nris_refnum"]).split(".")[0].strip()

        site_data["source_spreadsheet"] = True
        site_data["primary_source"] = "nhl_spreadsheet"

        # Extract NRHP classification
        criteria = _extract_criteria(row)
        areas = _extract_areas_of_significance(row)

        # Build designation info
        designation = None
        if is_nhl:
            designation = {
                "designation_type": "Federal NHL",
                "designation_date": site_data.get("nhl_designation_date"),
                "designating_authority": "Secretary of the Interior",
                "source": "spreadsheet",
            }

        records.append({
            "site_data": site_data,
            "criteria": criteria,
            "areas": areas,
            "designation": designation,
            "raw_row": {k: str(v) for k, v in row.items() if pd.notna(v)},
        })

    logger.info("Parsed %d valid records from spreadsheet", len(records))
    return records
