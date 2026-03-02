"""
SHPO dispatcher — routes state codes to the appropriate adapter.

Single entry point for all state SHPO data ingestion. Reads adapter type
from config/state_sources.py and dispatches to the correct adapter class,
or dynamically imports a custom scraper from src.ingest.shpo_scrapers.
"""

import importlib
import logging

from config.state_sources import STATE_SOURCES
from src.ingest.shpo_adapters.arcgis_adapter import ArcGISAdapter

logger = logging.getLogger(__name__)

# Adapter instances (reusable, stateless)
_ADAPTERS = {
    "arcgis": ArcGISAdapter(),
}


def get_active_states(filter_states: list[str] | None = None) -> list[str]:
    """Return list of active state codes, optionally filtered.

    Args:
        filter_states: If provided, only return these states (must also be active).

    Returns:
        List of uppercase state codes.
    """
    active = [
        code
        for code, cfg in STATE_SOURCES.items()
        if cfg.get("active", False)
    ]

    if filter_states:
        requested = {s.upper() for s in filter_states}
        active = [s for s in active if s in requested]
        unknown = requested - set(STATE_SOURCES.keys())
        if unknown:
            logger.warning(
                "[SHPO] Unknown state codes (not in STATE_SOURCES): %s",
                ", ".join(sorted(unknown)),
            )

    return sorted(active)


def _get_config(state_code: str) -> dict:
    """Get config for a state, injecting the state code."""
    state_code = state_code.upper()
    if state_code not in STATE_SOURCES:
        raise ValueError(f"No SHPO source configured for state: {state_code}")
    config = STATE_SOURCES[state_code].copy()
    config["_state_code"] = state_code
    return config


def fetch_state(state_code: str, use_cache: bool = True) -> list[dict]:
    """Fetch raw data for a state, routing to the appropriate adapter.

    Args:
        state_code: Two-letter state code (e.g., 'IN').
        use_cache: If True and cache exists, return cached data.

    Returns:
        List of raw feature dicts.
    """
    config = _get_config(state_code)
    adapter_type = config["adapter"]

    if adapter_type == "custom":
        module = importlib.import_module(
            f"src.ingest.shpo_scrapers.{state_code.lower()}"
        )
        return module.fetch(config, use_cache=use_cache)

    adapter = _ADAPTERS.get(adapter_type)
    if not adapter:
        raise ValueError(f"Unknown adapter type: {adapter_type}")

    return adapter.fetch(config, use_cache=use_cache)


def parse_state(state_code: str, raw_data: list[dict]) -> list[dict]:
    """Parse raw data for a state, routing to the appropriate adapter.

    Args:
        state_code: Two-letter state code.
        raw_data: Raw feature dicts from fetch_state().

    Returns:
        List of site record dicts ready for merge.
    """
    config = _get_config(state_code)
    adapter_type = config["adapter"]

    if adapter_type == "custom":
        module = importlib.import_module(
            f"src.ingest.shpo_scrapers.{state_code.lower()}"
        )
        return module.parse(raw_data, config)

    adapter = _ADAPTERS.get(adapter_type)
    if not adapter:
        raise ValueError(f"Unknown adapter type: {adapter_type}")

    return adapter.parse(raw_data, config)
