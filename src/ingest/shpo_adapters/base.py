"""Abstract base class for SHPO data source adapters."""

from abc import ABC, abstractmethod


class SHPOAdapter(ABC):
    """Base adapter for state historic preservation office data sources."""

    @abstractmethod
    def fetch(self, config: dict, use_cache: bool = True) -> list[dict]:
        """Fetch raw records from the data source.

        Args:
            config: State source configuration from STATE_SOURCES.
            use_cache: If True and cache exists, return cached data.

        Returns:
            List of raw feature dicts from the source.
        """

    @abstractmethod
    def parse(self, raw_data: list[dict], config: dict) -> list[dict]:
        """Parse raw features into site records matching our schema.

        Args:
            raw_data: Raw feature dicts from fetch().
            config: State source configuration from STATE_SOURCES.

        Returns:
            List of dicts ready for merge_shpo_records().
        """
