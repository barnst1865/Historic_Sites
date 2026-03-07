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
from src.ingest.shpo_adapters.gdb_adapter import GDBAdapter

logger = logging.getLogger(__name__)

# Adapter instances (reusable, stateless)
_ADAPTERS = {
    "arcgis": ArcGISAdapter(),
    "gdb": GDBAdapter(),
}


def get_active_states(filter_states: list[str] | None = None) -> list[str]:
    """Return list of active source keys, optionally filtered by state code.

    Keys can be plain state codes ('TX') or composite keys ('TX_NR').
    Filtering by 'TX' matches both 'TX' and 'TX_*' entries.

    Args:
        filter_states: If provided, only return sources for these states.

    Returns:
        List of uppercase source keys.
    """
    active = [
        code
        for code, cfg in STATE_SOURCES.items()
        if cfg.get("active", False)
    ]

    if filter_states:
        requested = {s.upper() for s in filter_states}
        active = [
            key for key in active
            if key in requested or key.split("_")[0] in requested
        ]
        # Check for completely unknown state prefixes or exact keys
        known = set(STATE_SOURCES.keys()) | {k.split("_")[0] for k in STATE_SOURCES}
        unknown = requested - known
        if unknown:
            logger.warning(
                "[SHPO] Unknown state codes (not in STATE_SOURCES): %s",
                ", ".join(sorted(unknown)),
            )

    return sorted(active)


def _get_config(source_key: str) -> dict:
    """Get config for a source key, injecting state code and source key.

    For composite keys like 'TX_NR', the state code is taken from the
    config's 'state_code' field or the prefix before '_'.
    """
    source_key = source_key.upper()
    if source_key not in STATE_SOURCES:
        raise ValueError(f"No SHPO source configured for: {source_key}")
    config = STATE_SOURCES[source_key].copy()
    config["_source_key"] = source_key
    config["_state_code"] = config.get("state_code", source_key.split("_")[0])
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
