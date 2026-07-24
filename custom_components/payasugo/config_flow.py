"""Config flow for Waste Management New Zealand PayAsUGO."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import voluptuous as vol
from aiohttp import CookieJar

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import PayAsUGOAuthError, PayAsUGOClient, PayAsUGOError
from .const import CONF_ADDRESS, DOMAIN

_LOGGER = logging.getLogger(__name__)


STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class PayAsUGOConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PayAsUGO."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the PayAsUGO config flow."""
        self._credentials: dict[str, str] = {}
        self._addresses: tuple[str, ...] = ()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle initial setup."""
        errors: dict[str, str] = {}
        if user_input is not None:
            session = async_create_clientsession(
                self.hass,
                auto_cleanup=False,
                cookie_jar=CookieJar(),
            )
            client = PayAsUGOClient(
                session,
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                "",
            )
            try:
                await client.async_login()
                addresses = await client.async_get_service_addresses()
            except PayAsUGOAuthError as err:
                _LOGGER.debug("PayAsUGO authentication failed: %s", err)
                errors["base"] = "invalid_auth"
            except PayAsUGOError as err:
                _LOGGER.warning(
                    "Unable to connect to PayAsUGO: %s",
                    err,
                    exc_info=True,
                )
                errors["base"] = "cannot_connect"
            else:
                if not addresses:
                    errors["base"] = "no_addresses"
                else:
                    self._credentials = user_input
                    self._addresses = addresses
                    return await self.async_step_address()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    async def async_step_address(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Let the user select a service address returned by PayAsUGO."""
        if not self._credentials or not self._addresses:
            return self.async_abort(reason="cannot_connect")

        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            if address not in self._addresses:
                return self.async_abort(reason="cannot_connect")
            identity = (
                f"{self._credentials[CONF_USERNAME].casefold()}:"
                f"{address.casefold()}"
            )
            await self.async_set_unique_id(
                hashlib.sha256(identity.encode()).hexdigest()
            )
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="Waste Management NZ PayAsUGO",
                data={**self._credentials, CONF_ADDRESS: address},
            )

        return self.async_show_form(
            step_id="address",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): SelectSelector(
                        SelectSelectorConfig(
                            options=list(self._addresses),
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Start reauthentication."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Confirm new credentials."""
        errors: dict[str, str] = {}
        if user_input is not None:
            assert self._reauth_entry is not None
            data = {**self._reauth_entry.data, **user_input}
            session = async_create_clientsession(
                self.hass,
                auto_cleanup=False,
                cookie_jar=CookieJar(),
            )
            client = PayAsUGOClient(
                session,
                data[CONF_USERNAME],
                data[CONF_PASSWORD],
                data[CONF_ADDRESS],
            )
            try:
                await client.async_login()
            except PayAsUGOAuthError as err:
                _LOGGER.debug("PayAsUGO authentication failed: %s", err)
                errors["base"] = "invalid_auth"
            except PayAsUGOError as err:
                _LOGGER.warning(
                    "Unable to reconnect to PayAsUGO: %s",
                    err,
                    exc_info=True,
                )
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    self._reauth_entry,
                    data_updates=data,
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )
