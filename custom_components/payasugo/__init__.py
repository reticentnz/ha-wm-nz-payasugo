"""Waste Management New Zealand PayAsUGO integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from aiohttp import CookieJar

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import PayAsUGOClient
from .const import CONF_ADDRESS, PLATFORMS
from .coordinator import PayAsUGOCoordinator


@dataclass(slots=True)
class PayAsUGORuntimeData:
    """Runtime data for a PayAsUGO config entry."""

    coordinator: PayAsUGOCoordinator


PayAsUGOConfigEntry: TypeAlias = ConfigEntry[PayAsUGORuntimeData]


async def async_setup_entry(
    hass: HomeAssistant, entry: PayAsUGOConfigEntry
) -> bool:
    """Set up PayAsUGO from a config entry."""
    session = async_create_clientsession(
        hass,
        cookie_jar=CookieJar(),
    )
    client = PayAsUGOClient(
        session,
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        entry.data[CONF_ADDRESS],
    )
    coordinator = PayAsUGOCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = PayAsUGORuntimeData(coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: PayAsUGOConfigEntry
) -> bool:
    """Unload a PayAsUGO config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
