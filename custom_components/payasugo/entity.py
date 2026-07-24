"""Base entity for PayAsUGO."""

from __future__ import annotations

import hashlib

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PayAsUGOCoordinator


class PayAsUGOEntity(CoordinatorEntity[PayAsUGOCoordinator]):
    """Base PayAsUGO entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PayAsUGOCoordinator, address: str) -> None:
        super().__init__(coordinator)
        address_hash = hashlib.sha256(address.encode()).hexdigest()[:16]
        self._address_hash = address_hash
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address_hash)},
            name="Waste Management NZ PayAsUGO",
            manufacturer="Waste Management New Zealand",
            model="PayAsUGO",
            configuration_url="https://payasugo.wastemanagement.co.nz/s/",
        )
