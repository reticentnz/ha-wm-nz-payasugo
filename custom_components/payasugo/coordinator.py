"""Data update coordinator for PayAsUGO."""

from __future__ import annotations

import logging
from datetime import date

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PayAsUGOAuthError, PayAsUGOClient, PayAsUGOError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, RETRY_INTERVALS
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
        self._consecutive_failures = 0

    async def _async_update_data(self) -> PayAsUGOData:
        try:
            collections = await self.client.async_get_collections(today=date.today())
        except PayAsUGOAuthError as err:
            _LOGGER.warning(
                "PayAsUGO authentication failed; reauthentication is required: %s",
                err,
            )
            raise ConfigEntryAuthFailed(str(err)) from err
        except PayAsUGOError as err:
            self._consecutive_failures += 1
            retry_interval = RETRY_INTERVALS[
                min(self._consecutive_failures - 1, len(RETRY_INTERVALS) - 1)
            ]
            self.update_interval = retry_interval
            _LOGGER.warning(
                "PayAsUGO refresh failed (%s: %s); retry %d in %s",
                type(err).__name__,
                err,
                self._consecutive_failures,
                retry_interval,
            )
            raise UpdateFailed(str(err)) from err

        if self._consecutive_failures:
            _LOGGER.info(
                "PayAsUGO refresh recovered after %d failed attempt%s",
                self._consecutive_failures,
                "" if self._consecutive_failures == 1 else "s",
            )
        self._consecutive_failures = 0
        self.update_interval = DEFAULT_SCAN_INTERVAL
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
