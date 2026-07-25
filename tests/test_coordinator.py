"""Tests for PayAsUGO coordinator refresh scheduling."""

from __future__ import annotations

import asyncio
import importlib.util
import logging
from pathlib import Path
import sys
import types
from unittest.mock import AsyncMock

import pytest

from custom_components.payasugo.api import PayAsUGOConnectionError
from custom_components.payasugo.const import DEFAULT_SCAN_INTERVAL, RETRY_INTERVALS


COMPONENT = Path(__file__).parents[1] / "custom_components" / "payasugo"


class UpdateFailed(Exception):
    """Test replacement for Home Assistant's UpdateFailed."""


class ConfigEntryAuthFailed(Exception):
    """Test replacement for Home Assistant's ConfigEntryAuthFailed."""


class DataUpdateCoordinator:
    """Minimal coordinator implementation used by these unit tests."""

    def __class_getitem__(cls, item):
        return cls

    def __init__(self, hass, *, update_interval, **kwargs) -> None:
        self.hass = hass
        self.update_interval = update_interval


def _load_coordinator_module():
    homeassistant = types.ModuleType("homeassistant")
    config_entries = types.ModuleType("homeassistant.config_entries")
    config_entries.ConfigEntry = object
    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = object
    exceptions = types.ModuleType("homeassistant.exceptions")
    exceptions.ConfigEntryAuthFailed = ConfigEntryAuthFailed
    helpers = types.ModuleType("homeassistant.helpers")
    update_coordinator = types.ModuleType(
        "homeassistant.helpers.update_coordinator"
    )
    update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
    update_coordinator.UpdateFailed = UpdateFailed

    modules = {
        "homeassistant": homeassistant,
        "homeassistant.config_entries": config_entries,
        "homeassistant.core": core,
        "homeassistant.exceptions": exceptions,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.update_coordinator": update_coordinator,
    }
    previous = {name: sys.modules.get(name) for name in modules}
    sys.modules.update(modules)
    try:
        spec = importlib.util.spec_from_file_location(
            "custom_components.payasugo.coordinator", COMPONENT / "coordinator.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        for name, old_module in previous.items():
            if old_module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old_module


def test_failed_refresh_backs_off_then_recovers(caplog) -> None:
    module = _load_coordinator_module()
    client = types.SimpleNamespace(
        async_get_collections=AsyncMock(
            side_effect=[
                PayAsUGOConnectionError("temporary outage"),
                PayAsUGOConnectionError("temporary outage"),
                (),
            ]
        )
    )
    coordinator = module.PayAsUGOCoordinator(object(), object(), client)

    with caplog.at_level(logging.INFO):
        with pytest.raises(UpdateFailed):
            asyncio.run(coordinator._async_update_data())
        assert coordinator.update_interval == RETRY_INTERVALS[0]

        with pytest.raises(UpdateFailed):
            asyncio.run(coordinator._async_update_data())
        assert coordinator.update_interval == RETRY_INTERVALS[1]

        data = asyncio.run(coordinator._async_update_data())

    assert data.collections == ()
    assert coordinator.update_interval == DEFAULT_SCAN_INTERVAL
    assert coordinator._consecutive_failures == 0
    assert "retry 1 in 0:05:00" in caplog.text
    assert "recovered after 2 failed attempts" in caplog.text


def test_retry_interval_is_capped() -> None:
    module = _load_coordinator_module()
    client = types.SimpleNamespace(
        async_get_collections=AsyncMock(
            side_effect=PayAsUGOConnectionError("temporary outage")
        )
    )
    coordinator = module.PayAsUGOCoordinator(object(), object(), client)

    for _ in range(len(RETRY_INTERVALS) + 2):
        with pytest.raises(UpdateFailed):
            asyncio.run(coordinator._async_update_data())

    assert coordinator.update_interval == RETRY_INTERVALS[-1]
