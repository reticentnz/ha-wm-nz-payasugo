"""Tests for safe PayAsUGO diagnostics."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
import importlib.util
import json
from pathlib import Path
import sys
import types

from custom_components.payasugo.api import PayAsUGOClient
from custom_components.payasugo.models import Collection, PayAsUGOData


COMPONENT = Path(__file__).parents[1] / "custom_components" / "payasugo"


def _load_diagnostics_module():
    homeassistant = types.ModuleType("homeassistant")
    const = types.ModuleType("homeassistant.const")
    const.CONF_PASSWORD = "password"
    const.CONF_USERNAME = "username"
    previous = {
        "homeassistant": sys.modules.get("homeassistant"),
        "homeassistant.const": sys.modules.get("homeassistant.const"),
    }
    sys.modules.update({"homeassistant": homeassistant, "homeassistant.const": const})
    try:
        spec = importlib.util.spec_from_file_location(
            "custom_components.payasugo.diagnostics", COMPONENT / "diagnostics.py"
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


def test_client_diagnostics_exposes_shapes_not_private_values() -> None:
    client = object.__new__(PayAsUGOClient)
    client._context = {
        "mode": "secret-mode-value",
        "fwuid": "salesforce-runtime-id",
        "app": "secret-app-value",
        "loaded": {"customer-component-id": "component-secret"},
        "account-secret-key": "account-secret-value",
    }
    client._token = "token.header.signature"
    client._response_cookies = {"secret-cookie-name": "secret-cookie-value"}
    client._action_id = 8

    diagnostics = client.diagnostics()
    serialized = json.dumps(diagnostics)

    assert diagnostics["authenticated"] is True
    assert diagnostics["aura_context"]["loaded_component_count"] == 1
    assert diagnostics["token_state"] == "three_part"
    assert diagnostics["response_cookie_count"] == 1
    assert diagnostics["action_count"] == 7
    for secret in (
        "secret-mode-value",
        "salesforce-runtime-id",
        "secret-app-value",
        "customer-component-id",
        "component-secret",
        "account-secret-key",
        "account-secret-value",
        "token.header.signature",
        "secret-cookie-name",
        "secret-cookie-value",
    ):
        assert secret not in serialized


def test_config_entry_diagnostics_are_useful_and_identifier_free() -> None:
    module = _load_diagnostics_module()
    client = object.__new__(PayAsUGOClient)
    client._context = None
    client._token = "null"
    client._response_cookies = {}
    client._action_id = 1
    coordinator = types.SimpleNamespace(
        client=client,
        data=PayAsUGOData(
            collections=(
                Collection(
                    collection_id="collection-account-123",
                    collection_date=date(2026, 8, 11),
                    enabled=True,
                    status="Planned",
                    product_family="General waste",
                    product_id="product-account-456",
                ),
            )
        ),
        last_update_success=False,
        last_exception=RuntimeError("user@example.com at 1 Secret Street"),
        _consecutive_failures=2,
        update_interval=timedelta(minutes=15),
    )
    entry = types.SimpleNamespace(
        data={
            "username": "user@example.com",
            "password": "password-secret",
            "address": "1 Secret Street",
            "account_id": "account-789",
            "cookie": "cookie-secret",
            "token": "token-secret",
        },
        runtime_data=types.SimpleNamespace(coordinator=coordinator),
    )

    diagnostics = asyncio.run(
        module.async_get_config_entry_diagnostics(object(), entry)
    )
    serialized = json.dumps(diagnostics)

    assert diagnostics["configuration"] == {
        "username_configured": True,
        "password_configured": True,
        "address_configured": True,
    }
    assert diagnostics["coordinator"]["last_exception_type"] == "RuntimeError"
    assert diagnostics["coordinator"]["update_interval_seconds"] == 900
    assert diagnostics["collections"]["items"] == [
        {
            "date": "2026-08-11",
            "enabled": True,
            "status": "Planned",
            "product_family": "General waste",
            "within_long_pause": False,
        }
    ]
    for secret in (
        "user@example.com",
        "password-secret",
        "1 Secret Street",
        "account-789",
        "cookie-secret",
        "token-secret",
        "collection-account-123",
        "product-account-456",
    ):
        assert secret not in serialized
