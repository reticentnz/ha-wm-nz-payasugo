"""Data models for PayAsUGO."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class Collection:
    """A scheduled PayAsUGO collection."""

    collection_id: str
    collection_date: date
    enabled: bool
    status: str
    product_family: str | None = None
    product_id: str | None = None
    within_long_pause: bool = False


@dataclass(frozen=True, slots=True)
class PayAsUGOData:
    """Coordinator data."""

    collections: tuple[Collection, ...]

    @property
    def next_collection(self) -> Collection | None:
        """Return the earliest collection returned by the service."""
        return min(
            self.collections,
            key=lambda item: item.collection_date,
            default=None,
        )

