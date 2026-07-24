"""Data update coordinator for PayAsUGO."""

from __future__ import annotations

import logging
from datetime import date

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PayAsUGOAuthError, PayAsUGOClient, PayAsUGOError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .models import PayAsUGOData

_LOGGER = logging.getLogger(__name__)


class PayAsUGOCoordinator(DataUpdateCoordinator[PayAsUGOData]):
    """Coordinate PayAsUGO collection data."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: PayAsUGOClient,
    ) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
            config_entry=entry,
        )
        self.client = client

    async def _async_update_data(self) -> PayAsUGOData:
        try:
            collections = await self.client.async_get_collections(today=date.today())
        except PayAsUGOAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except PayAsUGOError as err:
            raise UpdateFailed(str(err)) from err
        return PayAsUGOData(collections=collections)

    async def async_set_next_collection_enabled(self, enabled: bool) -> None:
        """Update the next collection and refresh coordinator data."""
        next_collection = self.data.next_collection if self.data else None
        if next_collection is None:
            raise UpdateFailed("There is no upcoming collection to update")
        try:
            await self.client.async_set_collection_enabled(
                next_collection.collection_id, enabled
            )
        except PayAsUGOError as err:
            raise UpdateFailed(str(err)) from err
        await self.async_request_refresh()
