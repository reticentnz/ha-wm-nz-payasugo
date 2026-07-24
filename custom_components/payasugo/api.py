"""Client for Waste Management New Zealand's PayAsUGO application."""

from __future__ import annotations

import json
import re
from calendar import monthrange
from collections.abc import Mapping
from datetime import date
from typing import Any
from urllib.parse import urljoin

from aiohttp import ClientResponse, ClientSession

from .const import BASE_URL
from .models import Collection


class PayAsUGOError(Exception):
    """Base error raised by the PayAsUGO client."""


class PayAsUGOAuthError(PayAsUGOError):
    """Authentication failed."""


class PayAsUGOConnectionError(PayAsUGOError):
    """The PayAsUGO service could not be reached."""


class PayAsUGOProtocolError(PayAsUGOError):
    """The PayAsUGO site returned an unexpected response."""


class PayAsUGOClient:
    """Client for Waste Management New Zealand's private PayAsUGO API."""

    _LOGIN_PAGE = "/s/login/"
    _APP_PAGE = "/s/"
    _AURA_ENDPOINT = "/s/sfsites/aura"

    def __init__(
        self,
        session: ClientSession,
        username: str,
        password: str,
        address: str,
        *,
        base_url: str = BASE_URL,
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._address = address
        self._base_url = base_url.rstrip("/")
        self._context: dict[str, Any] | None = None
        self._token = "null"
        self._page_uri = self._APP_PAGE
        self._action_id = 1

    async def async_login(self) -> None:
        """Create an authenticated Aura session."""
        login_response = await self._get(self._LOGIN_PAGE)
        login_html = await login_response.text()
        self._context, self._token = _extract_aura_bootstrap(login_html)
        self._page_uri = login_response.url.path_qs

        result = await self._aura_action(
            descriptor="apex://LightningLoginFormController/ACTION$login",
            calling_descriptor="markup://c:loginForm",
            params={
                "username": self._username,
                "password": self._password,
                "startUrl": self._APP_PAGE,
            },
        )
        if not isinstance(result, str) or not result:
            raise PayAsUGOAuthError("PayAsUGO rejected the supplied credentials")

        redirect = urljoin(self._base_url, result)
        redirect_response = await self._get(redirect)
        await redirect_response.read()

        app_response = await self._get(self._APP_PAGE)
        app_html = await app_response.text()
        self._context, self._token = _extract_aura_bootstrap(app_html)
        self._page_uri = self._APP_PAGE

    async def async_get_collections(
        self,
        *,
        months: int = 3,
        today: date | None = None,
    ) -> tuple[Collection, ...]:
        """Return upcoming collections across the requested number of months."""
        await self._ensure_authenticated()
        current = (today or date.today()).replace(day=1)
        events: dict[str, Collection] = {}

        for offset in range(months):
            month = _add_months(current, offset)
            value = await self._execute_apex(
                "getUsersSDE",
                {
                    "jsonMap": json.dumps(
                        {
                            "monthFirstDateStr": (
                                f"{month.year}-{month.month}-{month.day}"
                            ),
                            "address": self._address,
                        },
                        separators=(",", ":"),
                    )
                },
            )
            payload = _unwrap_return_value(value)
            for raw_event in payload.get("currentEvents", []):
                collection = _parse_collection(raw_event)
                if collection.collection_date >= (today or date.today()):
                    events[collection.collection_id] = collection

        return tuple(sorted(events.values(), key=lambda item: item.collection_date))

    async def async_set_collection_enabled(
        self, collection_id: str, enabled: bool
    ) -> None:
        """Pause or re-enable one collection."""
        await self._ensure_authenticated()
        await self._execute_apex(
            "updateSDEFromCalendar",
            {
                "eventJSON": json.dumps(
                    {collection_id: enabled}, separators=(",", ":")
                )
            },
        )

    async def _ensure_authenticated(self) -> None:
        if self._context is None:
            await self.async_login()

    async def _execute_apex(
        self, method: str, params: Mapping[str, Any]
    ) -> Any:
        return await self._aura_action(
            descriptor="aura://ApexActionController/ACTION$execute",
            calling_descriptor="UNKNOWN",
            params={
                "namespace": "",
                "classname": "PaytAppController",
                "method": method,
                "params": dict(params),
                "cacheable": False,
                "isContinuation": False,
            },
        )

    async def _aura_action(
        self,
        *,
        descriptor: str,
        calling_descriptor: str,
        params: Mapping[str, Any],
    ) -> Any:
        if self._context is None:
            raise PayAsUGOProtocolError("Aura context has not been initialised")

        action_id = f"{self._action_id};a"
        self._action_id += 1
        message = {
            "actions": [
                {
                    "id": action_id,
                    "descriptor": descriptor,
                    "callingDescriptor": calling_descriptor,
                    "params": dict(params),
                }
            ]
        }
        response = await self._post(
            self._AURA_ENDPOINT,
            data={
                "message": json.dumps(message, separators=(",", ":")),
                "aura.context": json.dumps(
                    self._context, separators=(",", ":")
                ),
                "aura.pageURI": self._page_uri,
                "aura.token": self._token,
            },
        )
        try:
            payload = await response.json(content_type=None)
        except (json.JSONDecodeError, ValueError) as err:
            raise PayAsUGOProtocolError("PayAsUGO returned invalid JSON") from err

        actions = payload.get("actions", [])
        if not actions:
            raise PayAsUGOProtocolError("PayAsUGO returned no Aura action")
        response_context = payload.get("context")
        if isinstance(response_context, dict):
            self._context = response_context
        action = actions[0]
        state = action.get("state")
        if state != "SUCCESS":
            errors = action.get("error") or []
            message_text = _error_message(errors)
            if "login" in message_text.lower() or "credential" in message_text.lower():
                self._context = None
                raise PayAsUGOAuthError(message_text)
            raise PayAsUGOProtocolError(message_text or f"Aura action failed: {state}")
        return action.get("returnValue")

    async def _get(self, path_or_url: str) -> ClientResponse:
        url = urljoin(f"{self._base_url}/", path_or_url)
        try:
            response = await self._session.get(url, allow_redirects=True)
            response.raise_for_status()
            return response
        except PayAsUGOError:
            raise
        except Exception as err:
            raise PayAsUGOConnectionError("Unable to reach PayAsUGO") from err

    async def _post(self, path: str, **kwargs: Any) -> ClientResponse:
        url = urljoin(f"{self._base_url}/", path)
        try:
            response = await self._session.post(url, **kwargs)
            response.raise_for_status()
            return response
        except PayAsUGOError:
            raise
        except Exception as err:
            raise PayAsUGOConnectionError("Unable to reach PayAsUGO") from err


def _extract_aura_bootstrap(html: str) -> tuple[dict[str, Any], str]:
    """Extract Aura context and CSRF token from a Salesforce bootstrap page."""
    markers = (
        "auraConfig",
        "Aura.bootstrap",
        "auraInitConfig",
    )
    candidates: list[dict[str, Any]] = []
    for marker in markers:
        start = 0
        while (position := html.find(marker, start)) != -1:
            brace = html.find("{", position)
            if brace == -1:
                break
            try:
                candidate = _decode_balanced_json(html, brace)
            except (json.JSONDecodeError, ValueError):
                start = position + len(marker)
                continue
            if isinstance(candidate, dict):
                candidates.append(candidate)
            start = brace + 1

    for candidate in candidates:
        context = candidate.get("context")
        if isinstance(context, dict):
            token = candidate.get("token") or candidate.get("csrfToken") or "null"
            return context, str(token)

    context_match = re.search(r'"context"\s*:', html)
    if context_match:
        brace = html.find("{", context_match.end())
        if brace != -1:
            context = _decode_balanced_json(html, brace)
            if isinstance(context, dict) and "fwuid" in context:
                token_match = re.search(
                    r'"(?:token|csrfToken)"\s*:\s*"([^"]+)"', html
                )
                return context, token_match.group(1) if token_match else "null"

    raise PayAsUGOProtocolError("Could not find Salesforce Aura bootstrap data")


def _decode_balanced_json(text: str, start: int) -> Any:
    decoder = json.JSONDecoder()
    value, _ = decoder.raw_decode(text[start:])
    return value


def _unwrap_return_value(value: Any) -> dict[str, Any]:
    while isinstance(value, dict) and set(value).issuperset({"returnValue"}):
        value = value["returnValue"]
    if not isinstance(value, dict):
        raise PayAsUGOProtocolError("Unexpected PayAsUGO response structure")
    return value


def _parse_collection(raw: Mapping[str, Any]) -> Collection:
    collection_id = raw.get("Id")
    date_value = raw.get("Calendar_Event_Date_Final__c") or raw.get("EventDate__c")
    if not isinstance(collection_id, str) or not isinstance(date_value, str):
        raise PayAsUGOProtocolError("Collection response is missing an ID or date")
    status = str(raw.get("Status__c") or "")
    return Collection(
        collection_id=collection_id,
        collection_date=date.fromisoformat(date_value[:10]),
        enabled=status.casefold() != "paused",
        status=status,
        product_family=raw.get("Product_Family__c"),
        product_id=raw.get("Product__c"),
        within_long_pause=bool(raw.get("Within_Long_Pause_Period__c", False)),
    )


def _error_message(errors: Any) -> str:
    if not isinstance(errors, list):
        return str(errors)
    messages = []
    for error in errors:
        if isinstance(error, dict):
            messages.append(str(error.get("message") or error.get("exceptionMessage") or ""))
        else:
            messages.append(str(error))
    return "; ".join(message for message in messages if message)


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)
