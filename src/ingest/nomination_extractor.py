"""
Multi-strategy extraction of structured data from NHL nomination PDFs.

Strategy 1: Send PDF directly to Claude API (native PDF reading)
Strategy 2: OCR fallback via pytesseract for scanned documents
Strategy 3: Flag for manual entry if both strategies fail

Extracted fields: period of significance, areas of significance,
statement of significance, associated persons, architectural style,
original/current function, acreage, condition.
"""

import json
import logging
from pathlib import Path

from pydantic import BaseModel, Field

from config.settings import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)


class NominationData(BaseModel):
    """Structured data extracted from a nomination document."""

    period_start_year: int | None = Field(None, description="Start of period of significance")
    period_end_year: int | None = Field(None, description="End of period of significance")
    areas_of_significance: list[str] = Field(
        default_factory=list,
        description="NRHP areas of significance (use standard slugs)",
    )
    criteria: list[str] = Field(
        default_factory=list,
        description="NRHP criteria (A, B, C, D)",
    )
    statement_of_significance: str | None = Field(
        None, description="Full text of the Statement of Significance section"
    )
    associated_persons: list[dict] = Field(
        default_factory=list,
        description="List of {name, role} dicts for associated persons",
    )
    architectural_style: str | None = None
    original_function: str | None = None
    current_function: str | None = None
    acreage: str | None = None
    condition: str | None = Field(
        None, description="Good, Fair, Poor, Ruins, or Unknown"
    )
    extraction_confidence: float = Field(
        0.0, description="Self-assessed confidence 0.0-1.0"
    )


EXTRACTION_PROMPT = """You are extracting structured data from a National Register of Historic Places / National Historic Landmark nomination document.

Extract the following fields. Use the exact format specified:

1. **Period of Significance**: Start year and end year (integers)
2. **Areas of Significance**: Use these standard NRHP slugs:
   agriculture, architecture, archaeology, art, commerce, communications,
   community-planning, conservation, economics, education, engineering,
   entertainment-recreation, ethnic-heritage, exploration-settlement,
   health-medicine, industry, invention, landscape-architecture, law,
   literature, maritime-history, military, performing-arts, philosophy,
   politics-government, religion, science, social-history, transportation, other
3. **Criteria**: A, B, C, and/or D
4. **Statement of Significance**: The full narrative text from Section 8
5. **Associated Persons**: Name and their role/significance
6. **Architectural Style**: If mentioned
7. **Original Function** and **Current Function**: From Section 7
8. **Acreage**: Property size
9. **Condition**: Good, Fair, Poor, Ruins, or Unknown

Return your response as a JSON object matching this schema:
{
  "period_start_year": int or null,
  "period_end_year": int or null,
  "areas_of_significance": ["slug1", "slug2"],
  "criteria": ["A", "C"],
  "statement_of_significance": "text...",
  "associated_persons": [{"name": "...", "role": "..."}],
  "architectural_style": "...",
  "original_function": "...",
  "current_function": "...",
  "acreage": "...",
  "condition": "Good|Fair|Poor|Ruins|Unknown",
  "extraction_confidence": 0.0-1.0
}

Rate your confidence based on document quality: 0.9+ for clear text,
0.5-0.8 for partially readable, below 0.5 for mostly illegible.
"""


def extract_with_claude(pdf_path: Path) -> tuple[NominationData | None, str]:
    """Extract nomination data using Claude's native PDF reading.

    Args:
        pdf_path: Path to the nomination PDF.

    Returns:
        Tuple of (extracted data or None, extraction method string).
    """
    if not ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set. Cannot extract nominations.")
        return None, "no_api_key"

    import anthropic
    import base64

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        # Read PDF as base64
        with open(pdf_path, "rb") as f:
            pdf_data = base64.standard_b64encode(f.read()).decode("utf-8")

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": EXTRACTION_PROMPT,
                        },
                    ],
                }
            ],
        )

        response_text = message.content[0].text

        # Parse JSON from response
        json_start = response_text.find("{")
        json_end = response_text.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            data = json.loads(response_text[json_start:json_end])
            nomination = NominationData(**data)

            if nomination.extraction_confidence < 0.3:
                logger.info("Low confidence extraction, may need OCR: %s", pdf_path.name)
                return nomination, "claude_pdf_low_confidence"

            return nomination, "claude_pdf"

    except json.JSONDecodeError as e:
        logger.warning("Failed to parse Claude response for %s: %s", pdf_path.name, e)
    except Exception as e:
        logger.warning("Claude extraction failed for %s: %s", pdf_path.name, e)

    return None, "claude_pdf_failed"


def extract_with_ocr(pdf_path: Path) -> tuple[NominationData | None, str]:
    """OCR fallback: convert PDF to images, OCR, then send text to Claude.

    Args:
        pdf_path: Path to the nomination PDF.

    Returns:
        Tuple of (extracted data or None, extraction method string).
    """
    if not ANTHROPIC_API_KEY:
        return None, "no_api_key"

    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError as e:
        logger.warning("OCR dependencies not available: %s", e)
        return None, "ocr_deps_missing"

    try:
        # Convert PDF pages to images
        images = convert_from_path(pdf_path, dpi=300, first_page=1, last_page=30)
        if not images:
            return None, "ocr_no_pages"

        # OCR each page
        ocr_text = ""
        for i, img in enumerate(images):
            page_text = pytesseract.image_to_string(img)
            ocr_text += f"\n--- Page {i + 1} ---\n{page_text}"

        if len(ocr_text.strip()) < 100:
            logger.warning("OCR produced very little text for %s", pdf_path.name)
            return None, "ocr_insufficient_text"

        # Send OCR text to Claude for structured extraction
        import anthropic

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "The following text was extracted via OCR from a National Register "
                        "nomination document. It may contain OCR errors.\n\n"
                        f"--- OCR TEXT ---\n{ocr_text[:50000]}\n--- END ---\n\n"
                        f"{EXTRACTION_PROMPT}"
                    ),
                }
            ],
        )

        response_text = message.content[0].text
        json_start = response_text.find("{")
        json_end = response_text.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            data = json.loads(response_text[json_start:json_end])
            nomination = NominationData(**data)
            return nomination, "ocr_then_claude"

    except Exception as e:
        logger.warning("OCR extraction failed for %s: %s", pdf_path.name, e)

    return None, "ocr_failed"


def extract_nomination(pdf_path: Path) -> tuple[NominationData | None, str]:
    """Multi-strategy extraction from a nomination PDF.

    Tries: Claude PDF → OCR fallback → flag for manual entry.

    Args:
        pdf_path: Path to the nomination PDF.

    Returns:
        Tuple of (extracted data or None, extraction method).
        Method is one of: 'claude_pdf', 'ocr_then_claude', 'manual_needed'.
    """
    # Strategy 1: Claude native PDF reading
    data, method = extract_with_claude(pdf_path)
    if data and data.extraction_confidence >= 0.3:
        return data, method

    # Strategy 2: OCR fallback
    logger.info("Trying OCR fallback for %s", pdf_path.name)
    data, method = extract_with_ocr(pdf_path)
    if data:
        return data, method

    # Strategy 3: Flag for manual entry
    logger.warning("All extraction strategies failed for %s", pdf_path.name)
    return None, "manual_needed"


def store_extraction(
    conn, site_id: int, nomination: NominationData | None, method: str
) -> None:
    """Store extracted nomination data into the database.

    Args:
        conn: Database connection.
        site_id: The site ID to update.
        nomination: Extracted data (or None if extraction failed).
        method: Extraction method string.
    """
    from src.db.queries import (
        add_nrhp_area,
        add_nrhp_criterion,
        add_nrhp_period,
        update_site,
    )

    updates = {"source_nomination": True}

    if nomination:
        # Store period of significance
        if nomination.period_start_year or nomination.period_end_year:
            add_nrhp_period(
                conn, site_id,
                nomination.period_start_year,
                nomination.period_end_year,
                "nomination",
            )

        # Store areas of significance
        for area in nomination.areas_of_significance:
            add_nrhp_area(conn, site_id, area, "nomination")

        # Store criteria
        for criterion in nomination.criteria:
            if criterion in ("A", "B", "C", "D"):
                add_nrhp_criterion(conn, site_id, criterion, "nomination")

        # Update site description
        if nomination.statement_of_significance:
            updates["full_description"] = nomination.statement_of_significance

        if nomination.condition:
            updates["condition"] = nomination.condition

        # Store raw extraction for audit
        updates["enrichment_raw_json"] = json.dumps(nomination.model_dump(), default=str)

    update_site(conn, site_id, updates)
