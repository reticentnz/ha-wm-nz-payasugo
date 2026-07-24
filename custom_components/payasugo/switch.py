"""Switch entities for PayAsUGO."""

from __future__ import annotations

from datetime import datetime, time, timedelta

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import PayAsUGOConfigEntry
from .const import CONF_ADDRESS
from .entity import PayAsUGOEntity


async def async_setup_entry(
    hass, entry: PayAsUGOConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the next collection switch."""
    async_add_entities(
        [
            PayAsUGONextCollectionSwitch(
                entry.runtime_data.coordinator,
                entry.data[CONF_ADDRESS],
            )
        ]
    )


class PayAsUGONextCollectionSwitch(PayAsUGOEntity, SwitchEntity):
    """Enable or pause the next PayAsUGO collection."""

    _attr_translation_key = "next_collection"
    _attr_icon = "mdi:delete-restore"

    def __init__(self, coordinator, address: str) -> None:
        super().__init__(coordinator, address)
        self._attr_unique_id = f"{self._address_hash}_next_collection_enabled"

    @property
    def is_on(self) -> bool | None:
        """Return whether the next collection is enabled."""
        collection = self.coordinator.data.next_collection
        return collection.enabled if collection else None

    @property
    def available(self) -> bool:
        """Return whether the collection can still be changed."""
        collection = self.coordinator.data.next_collection
        if collection is None:
            return False
        cutoff = datetime.combine(
            collection.collection_date,
            time(hour=7),
            tzinfo=dt_util.DEFAULT_TIME_ZONE,
        ) - timedelta(hours=48)
        return super().available and dt_util.now() < cutoff

    async def async_turn_on(self, **kwargs) -> None:
        """Re-enable the next collection."""
        await self.coordinator.async_set_next_collection_enabled(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Pause the next collection."""
        await self.coordinator.async_set_next_collection_enabled(False)

