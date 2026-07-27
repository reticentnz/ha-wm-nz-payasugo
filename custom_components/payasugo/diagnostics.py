"""Diagnostics support for PayAsUGO."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from .const import CONF_ADDRESS

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from . import PayAsUGOConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PayAsUGOConfigEntry
) -> dict[str, Any]:
    """Return safe diagnostics for a PayAsUGO config entry.

    This is an allowlist rather than a copy-and-redact operation. That prevents
    new private API fields from accidentally exposing customer data.
    """
    coordinator = entry.runtime_data.coordinator
    data = coordinator.data
    collections = data.collections if data is not None else ()
    update_interval = coordinator.update_interval
    last_exception = getattr(coordinator, "last_exception", None)

    return {
        "diagnostics_format": 1,
        "configuration": {
            "username_configured": bool(entry.data.get(CONF_USERNAME)),
            "password_configured": bool(entry.data.get(CONF_PASSWORD)),
            "address_configured": bool(entry.data.get(CONF_ADDRESS)),
        },
        "coordinator": {
            "last_update_success": getattr(
                coordinator, "last_update_success", None
            ),
            "last_exception_type": (
                type(last_exception).__name__ if last_exception is not None else None
            ),
            "consecutive_failures": coordinator._consecutive_failures,
            "update_interval_seconds": (
                update_interval.total_seconds()
                if update_interval is not None
                else None
            ),
        },
        "private_api": coordinator.client.diagnostics(),
        "collections": {
            "count": len(collections),
            "items": [
                {
                    "date": collection.collection_date.isoformat(),
                    "enabled": collection.enabled,
                    "status": collection.status,
                    "product_family": collection.product_family,
                    "within_long_pause": collection.within_long_pause,
                }
                for collection in collections
            ],
        },
    }
