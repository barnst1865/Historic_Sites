"""
Download NHL nomination PDFs from NPGallery (post-2013) and NARA (pre-2013).

Tracks download success/failure per record. Uses NRIS reference numbers
to locate documents. Downloads are cached in data/nominations/.
"""

import logging
import time
from pathlib import Path

import requests

from config.settings import NOMINATIONS_DIR, NPGALLERY_BASE_URL

logger = logging.getLogger(__name__)

# NPGallery direct PDF link pattern
NPGALLERY_PDF_URL = "https://npgallery.nps.gov/GetAsset/{asset_id}"

# Known URL patterns for nomination documents
NPGALLERY_SEARCH_URL = "https://npgallery.nps.gov/NRHP/GetAssets"


def _pdf_path(nris_refnum: str) -> Path:
    """Get the local path for a nomination PDF."""
    return NOMINATIONS_DIR / f"{nris_refnum}.pdf"


def download_nomination(
    nris_refnum: str, timeout: int = 30
) -> dict:
    """Attempt to download a nomination PDF for a given NRIS reference number.

    Tries NPGallery first. Returns status dict.

    Args:
        nris_refnum: The NRIS reference number.
        timeout: Request timeout in seconds.

    Returns:
        Dict with 'refnum', 'status' ('downloaded'/'cached'/'not_found'/'error'),
        'path', 'method'.
    """
    pdf_path = _pdf_path(nris_refnum)

    # Check cache
    if pdf_path.exists() and pdf_path.stat().st_size > 0:
        return {
            "refnum": nris_refnum,
            "status": "cached",
            "path": str(pdf_path),
            "method": "cache",
        }

    # Try NPGallery search
    try:
        search_url = f"{NPGALLERY_BASE_URL}/AssetDetail"
        params = {"assetID": nris_refnum}

        response = requests.get(search_url, params=params, timeout=timeout, allow_redirects=True)

        if response.status_code == 200 and "application/pdf" in response.headers.get(
            "Content-Type", ""
        ):
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            with open(pdf_path, "wb") as f:
                f.write(response.content)
            logger.info("Downloaded nomination PDF: %s", nris_refnum)
            return {
                "refnum": nris_refnum,
                "status": "downloaded",
                "path": str(pdf_path),
                "method": "npgallery",
            }

        # Try alternate NPGallery URL pattern
        alt_url = f"https://npgallery.nps.gov/NRHP/GetAsset/{nris_refnum}"
        response = requests.get(alt_url, timeout=timeout, allow_redirects=True)

        if response.status_code == 200 and len(response.content) > 1000:
            content_type = response.headers.get("Content-Type", "")
            if "pdf" in content_type or response.content[:4] == b"%PDF":
                pdf_path.parent.mkdir(parents=True, exist_ok=True)
                with open(pdf_path, "wb") as f:
                    f.write(response.content)
                logger.info("Downloaded nomination PDF (alt): %s", nris_refnum)
                return {
                    "refnum": nris_refnum,
                    "status": "downloaded",
                    "path": str(pdf_path),
                    "method": "npgallery_alt",
                }

    except requests.RequestException as e:
        logger.warning("Error downloading %s: %s", nris_refnum, e)
        return {
            "refnum": nris_refnum,
            "status": "error",
            "path": None,
            "method": None,
            "error": str(e),
        }

    return {
        "refnum": nris_refnum,
        "status": "not_found",
        "path": None,
        "method": None,
    }


def batch_download(
    refnums: list[str], delay: float = 1.0, limit: int | None = None
) -> list[dict]:
    """Download nomination PDFs for a batch of NRIS reference numbers.

    Args:
        refnums: List of NRIS reference numbers.
        delay: Seconds between requests.
        limit: Max number to download (None for all).

    Returns:
        List of status dicts from download_nomination().
    """
    results = []
    to_process = refnums[:limit] if limit else refnums

    for i, refnum in enumerate(to_process):
        if i > 0:
            time.sleep(delay)

        result = download_nomination(refnum)
        results.append(result)

        if (i + 1) % 50 == 0:
            downloaded = sum(1 for r in results if r["status"] in ("downloaded", "cached"))
            logger.info(
                "Progress: %d/%d processed, %d downloaded/cached",
                i + 1, len(to_process), downloaded,
            )

    # Summary
    statuses = {}
    for r in results:
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1
    logger.info("Batch download complete: %s", statuses)

    return results
