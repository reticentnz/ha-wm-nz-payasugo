"""Sensor entities for PayAsUGO."""

from __future__ import annotations

from datetime import datetime, time

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import PayAsUGOConfigEntry
from .const import CONF_ADDRESS
from .entity import PayAsUGOEntity


async def async_setup_entry(
    hass, entry: PayAsUGOConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the next collection sensor."""
    async_add_entities(
        [
            PayAsUGONextCollectionSensor(
                entry.runtime_data.coordinator,
                entry.data[CONF_ADDRESS],
            )
        ]
    )


class PayAsUGONextCollectionSensor(PayAsUGOEntity, SensorEntity):
    """Timestamp of the next PayAsUGO collection."""

    _attr_translation_key = "next_collection"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:delete-clock"

    def __init__(self, coordinator, address: str) -> None:
        super().__init__(coordinator, address)
        self._attr_unique_id = f"{self._address_hash}_next_collection"

    @property
    def native_value(self) -> datetime | None:
        """Return the next collection as a local timestamp."""
        collection = self.coordinator.data.next_collection
        if collection is None:
            return None
        return dt_util.as_local(
            datetime.combine(
                collection.collection_date,
                time.min,
                tzinfo=dt_util.DEFAULT_TIME_ZONE,
            )
        )

    @property
    def extra_state_attributes(self):
        """Return useful collection details."""
        collection = self.coordinator.data.next_collection
        if collection is None:
            return {}
        return {
            "enabled": collection.enabled,
            "status": collection.status,
            "product_family": collection.product_family,
            "within_long_pause": collection.within_long_pause,
        }

