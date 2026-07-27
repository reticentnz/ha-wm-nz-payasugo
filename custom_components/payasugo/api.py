"""Client for Waste Management New Zealand's PayAsUGO application."""

from __future__ import annotations

import json
import re
from calendar import monthrange
from collections.abc import Mapping
from datetime import date
from typing import Any
from urllib.parse import urljoin
from uuid import uuid4

from aiohttp import ClientResponse, ClientSession
from yarl import URL

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
        self._response_cookies: dict[str, str] = {}
        self._page_uri = self._APP_PAGE
        self._action_id = 1
        self._page_scope_id = str(uuid4())

    def diagnostics(self) -> dict[str, Any]:
        """Return an identifier-free summary of the private API session.

        Diagnostics deliberately describe only protocol state and value shapes.
        Raw Aura values, URLs, cookie names and values, tokens, credentials, and
        Salesforce identifiers must never be added here.
        """
        context = self._context
        loaded = context.get("loaded") if context is not None else None
        known_context_keys = (
            "app",
            "dn",
            "fwuid",
            "globals",
            "loaded",
            "mode",
            "uad",
        )
        present_context_keys = (
            [key for key in known_context_keys if key in context]
            if context is not None
            else []
        )
        token_state = "unset"
        if self._token != "null":
            token_state = (
                "three_part" if len(self._token.split(".")) == 3 else "other"
            )
        return {
            "authenticated": context is not None,
            "aura_context": {
                "present": context is not None,
                "keys": present_context_keys,
                "value_types": (
                    {key: type(context[key]).__name__ for key in present_context_keys}
                    if context is not None
                    else {}
                ),
                "loaded_component_count": (
                    len(loaded) if isinstance(loaded, dict) else 0
                ),
            },
            "token_state": token_state,
            "response_cookie_count": len(self._response_cookies),
            "action_count": max(self._action_id - 1, 0),
        }

    async def async_login(self) -> None:
        """Create an authenticated Aura session."""
        login_response = await self._get(self._LOGIN_PAGE)
        login_html = await login_response.text()
        login_bootstrap = await self._async_load_bootstrap(login_html)
        self._set_aura_bootstrap(login_bootstrap)
        self._page_uri = login_response.url.path_qs

        await self._async_prepare_login()
        result = await self._aura_action(
            descriptor="apex://LightningLoginFormController/ACTION$login",
            calling_descriptor="markup://c:loginForm",
            params={
                "username": self._username,
                "password": self._password,
                "startUrl": "",
            },
        )
        redirect = urljoin(self._base_url, _login_redirect(result))
        redirect_response = await self._get(redirect)
        await redirect_response.read()

        app_response = await self._get(self._APP_PAGE)
        app_html = await app_response.text()
        app_bootstrap = await self._async_load_bootstrap(app_html)
        self._set_aura_bootstrap(app_bootstrap)
        self._page_uri = self._APP_PAGE
        self._page_scope_id = str(uuid4())

    async def _async_prepare_login(self) -> None:
        """Run the guest-session actions performed before browser login."""
        actions = (
            (
                "serviceComponent://ui.communities.components.aura.components."
                "forceCommunity.navigationMenu.NavigationMenuDataProviderController/"
                "ACTION$getNavigationMenu",
                "markup://forceCommunity:navigationMenuBase",
                {
                    "navigationLinkSetIdOrName": "",
                    "includeImageUrl": False,
                    "addHomeMenuItem": True,
                    "menuItemTypesToSkip": ["SystemLink", "Event", "Modal"],
                    "masterLabel": "Default Navigation",
                },
            ),
            (
                "serviceComponent://ui.self.service.components.profileMenu."
                "ProfileMenuController/ACTION$getProfileMenuResponse",
                "markup://selfService:profileMenuAPI",
                {},
            ),
            (
                "serviceComponent://ui.force.components.controllers.hostConfig."
                "HostConfigController/ACTION$getConfigData",
                "UNKNOWN",
                {},
            ),
            (
                "apex://LightningLoginFormController/ACTION$isGuestUser",
                "markup://c:loginForm",
                {},
            ),
            (
                "apex://LightningLoginFormController/ACTION$getForgotPasswordUrl",
                "markup://c:loginForm",
                {},
            ),
        )
        for descriptor, calling_descriptor, params in actions:
            await self._aura_action(
                descriptor=descriptor,
                calling_descriptor=calling_descriptor,
                params=params,
            )

    async def _async_load_bootstrap(self, html: str) -> str:
        """Return content containing Aura's runtime bootstrap configuration."""
        try:
            _extract_aura_bootstrap(html)
        except PayAsUGOProtocolError:
            bootstrap_path = _extract_bootstrap_script_url(html)
            bootstrap_response = await self._get(bootstrap_path)
            return await bootstrap_response.text()
        return html

    def _set_aura_bootstrap(self, content: str) -> None:
        """Apply Aura context and resolve its short-lived CSRF cookie."""
        context, token, cookie_name = _extract_aura_bootstrap(content)
        if cookie_name:
            cookies = self._session.cookie_jar.filter_cookies(URL(self._base_url))
            cookie = cookies.get(cookie_name)
            if cookie is not None:
                token = cookie.value
            elif cookie_name in self._response_cookies:
                token = self._response_cookies[cookie_name]
        if len(token.split(".")) != 3:
            cookies = self._session.cookie_jar.filter_cookies(URL(self._base_url))
            token_candidates = {
                cookie.value
                for cookie in cookies.values()
                if len(cookie.value) > 100
                and len(cookie.value.split(".")) == 3
            }
            token_candidates.update(
                value
                for value in self._response_cookies.values()
                if len(value) > 100 and len(value.split(".")) == 3
            )
            if len(token_candidates) == 1:
                token = next(iter(token_candidates))
        if (
            len(token.split(".")) != 3
            and context.get("app") == "siteforce:communityApp"
        ):
            raise PayAsUGOProtocolError(
                "PayAsUGO did not provide its authenticated Aura security token "
                f"(declared_parts={len(token.split('.'))}, "
                f"response_cookies={len(self._response_cookies)}, "
                f"token_candidates={len(token_candidates)}, "
                f"named_cookie_seen={cookie_name in self._response_cookies})"
            )
        self._context = _compact_aura_context(context)
        self._token = token

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
            if events:
                break

        return tuple(sorted(events.values(), key=lambda item: item.collection_date))

    async def async_get_service_addresses(self) -> tuple[str, ...]:
        """Return active PayAsUGO service addresses for the signed-in account."""
        await self._ensure_authenticated()
        user_details = await self._aura_action(
            descriptor="apex://PaytAppController/ACTION$getUserDetails",
            calling_descriptor="markup://c:paytAppContainerCmp",
            params={},
        )
        if not isinstance(user_details, str):
            raise PayAsUGOProtocolError("Unexpected PayAsUGO account response")
        try:
            account = json.loads(user_details).get("userAccount", {})
        except (json.JSONDecodeError, AttributeError) as err:
            raise PayAsUGOProtocolError(
                "PayAsUGO returned invalid account details"
            ) from err
        account_id = account.get("Id")
        if not isinstance(account_id, str) or not account_id:
            raise PayAsUGOProtocolError(
                "PayAsUGO account has no service account identifier"
            )

        value = await self._execute_apex(
            "getUsersOrderAddress",
            {
                "accId": account_id,
                "statusList": ["Activated", "Processed"],
            },
        )
        addresses = _unwrap_return_value(value)
        return tuple(
            sorted(
                address
                for address, active in addresses.items()
                if isinstance(address, str) and active
            )
        )

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
        if self._context is not None:
            return
        self._reset_authentication()
        await self.async_login()

    async def _execute_apex(
        self, method: str, params: Mapping[str, Any]
    ) -> Any:
        action_params = {
            "namespace": "",
            "classname": "PaytAppController",
            "method": method,
            "params": dict(params),
            "cacheable": False,
            "isContinuation": False,
        }
        try:
            return await self._aura_action(
                descriptor="aura://ApexActionController/ACTION$execute",
                calling_descriptor="UNKNOWN",
                params=action_params,
            )
        except PayAsUGOAuthError:
            self._reset_authentication()
            await self.async_login()
            return await self._aura_action(
                descriptor="aura://ApexActionController/ACTION$execute",
                calling_descriptor="UNKNOWN",
                params=action_params,
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
            (
                f"{self._AURA_ENDPOINT}?r={self._action_id - 1}"
                f"&{_aura_route(descriptor)}=1"
            ),
            headers={
                "Accept": "*/*",
                "Accept-Language": "en-NZ,en;q=0.9",
                "Origin": self._base_url,
                "Referer": urljoin(f"{self._base_url}/", self._page_uri),
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
                ),
                "x-sfdc-page-scope-id": self._page_scope_id,
            },
            data={
                "message": json.dumps(message, separators=(",", ":")),
                "aura.context": json.dumps(
                    self._context, separators=(",", ":")
                ),
                "aura.pageURI": self._page_uri,
                "aura.token": self._token,
            },
        )
        raw_response = await response.read()
        if response.url.path.rstrip("/") == self._LOGIN_PAGE.rstrip("/"):
            self._context = None
            raise PayAsUGOAuthError("PayAsUGO session expired")
        try:
            payload = _decode_aura_response(raw_response)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as err:
            history = ",".join(str(item.status) for item in response.history) or "none"
            prefix_hex = raw_response[:32].hex()
            suffix_hex = raw_response[-32:].hex()
            raise PayAsUGOProtocolError(
                "PayAsUGO returned invalid JSON "
                f"(status={response.status}, content_type={response.content_type}, "
                f"path={response.url.path}, redirects={history}, "
                f"bytes={len(raw_response)}, open_frames={raw_response.count(b'*/')}, "
                f"close_frames={raw_response.count(b'/*')}, "
                f"prefix_hex={prefix_hex}, suffix_hex={suffix_hex})"
            ) from err

        actions = payload.get("actions", [])
        if not actions:
            exception_message = _aura_exception_message(payload)
            if exception_message:
                if _is_auth_error(exception_message):
                    self._context = None
                    raise PayAsUGOAuthError("PayAsUGO session expired")
                raise PayAsUGOProtocolError(
                    _redact_error_detail(
                        exception_message,
                        self._username,
                        self._password,
                    )
                )
            raise PayAsUGOProtocolError("PayAsUGO returned no Aura action")
        response_context = payload.get("context")
        if isinstance(response_context, dict):
            self._context = _compact_aura_context(response_context)
        action = actions[0]
        state = action.get("state")
        if state != "SUCCESS":
            errors = action.get("error") or []
            message_text = _error_message(errors)
            if _is_auth_error(message_text):
                self._context = None
                raise PayAsUGOAuthError(message_text)
            raise PayAsUGOProtocolError(message_text or f"Aura action failed: {state}")
        if descriptor == "apex://LightningLoginFormController/ACTION$login":
            redirect = _login_event_url(payload)
            if redirect is not None:
                return redirect
        return action.get("returnValue")

    async def _get(self, path_or_url: str) -> ClientResponse:
        url = urljoin(f"{self._base_url}/", path_or_url)
        try:
            response = await self._session.get(url, allow_redirects=True)
            self._remember_response_cookies(response)
            response.raise_for_status()
            return response
        except PayAsUGOError:
            raise
        except Exception as err:
            raise PayAsUGOConnectionError(
                f"Unable to reach PayAsUGO ({type(err).__name__}: {err})"
            ) from err

    async def _post(self, path: str, **kwargs: Any) -> ClientResponse:
        url = urljoin(f"{self._base_url}/", path)
        try:
            response = await self._session.post(url, **kwargs)
            self._remember_response_cookies(response)
            if response.status >= 400:
                detail = _redact_error_detail(
                    await response.text(),
                    self._username,
                    self._password,
                )
                raise PayAsUGOProtocolError(
                    f"PayAsUGO returned HTTP {response.status}"
                    f"{f': {detail}' if detail else ''}"
                )
            response.raise_for_status()
            return response
        except PayAsUGOError:
            raise
        except Exception as err:
            raise PayAsUGOConnectionError(
                f"Unable to reach PayAsUGO ({type(err).__name__}: {err})"
            ) from err

    def _remember_response_cookies(self, response: ClientResponse) -> None:
        """Remember response cookies that aiohttp may omit from its cookie jar."""
        for item in (*response.history, response):
            self._response_cookies.update(
                (name, morsel.value) for name, morsel in item.cookies.items()
            )

    def _reset_authentication(self) -> None:
        """Discard stale Salesforce state before creating a fresh session."""
        self._session.cookie_jar.clear()
        self._context = None
        self._token = "null"
        self._response_cookies.clear()
        self._page_uri = self._APP_PAGE
        self._action_id = 1
        self._page_scope_id = str(uuid4())


def _redact_error_detail(content: str, username: str, password: str) -> str:
    """Return a bounded server error with authentication data removed."""
    detail = re.sub(r"\s+", " ", content).strip()
    for secret in (username, password):
        if secret:
            detail = detail.replace(secret, "[redacted]")
    detail = re.sub(
        r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
        "[redacted-email]",
        detail,
    )
    return detail[:500]


def _is_auth_error(message: str) -> bool:
    """Return whether Salesforce is reporting an expired login session."""
    detail = message.casefold()
    return any(
        marker in detail
        for marker in (
            "authentication",
            "client is out of sync",
            "credential",
            "guest user",
            "invalid session",
            "login",
            "not authenticated",
            "session expired",
        )
    )


def _decode_aura_response(content: bytes) -> dict[str, Any]:
    """Decode Salesforce Aura JSON after its optional anti-XSSI prefix."""
    value = content.lstrip()
    if value.startswith(b"while(1);"):
        value = value[len(b"while(1);") :].lstrip()

    error_marker = value.find(b"/*ERROR*/")
    if error_marker != -1:
        frame = value[:error_marker]
        if frame.startswith(b"*/"):
            frame = frame[2:]
        payload = json.loads(frame)
        if not isinstance(payload, dict):
            raise ValueError("Aura error response is not an object")
        return payload

    if value.startswith(b"*/"):
        frames: list[dict[str, Any]] = []
        for frame in value.split(b"/*"):
            frame = frame.strip()
            if frame.startswith(b"*/"):
                frame = frame[2:].lstrip()
            if not frame:
                continue
            payload = json.loads(frame)
            if isinstance(payload, dict):
                frames.append(payload)
        for payload in frames:
            if "actions" in payload:
                return payload
        if frames:
            return frames[-1]
        raise ValueError("Aura response has no JSON frames")

    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("Aura response is not an object")
    return payload


def _aura_exception_message(payload: Mapping[str, Any]) -> str:
    """Return a message from a framed Salesforce Aura exception event."""
    message = payload.get("exceptionMessage")
    if isinstance(message, str) and message:
        return message
    event = payload.get("event")
    if not isinstance(event, dict):
        return ""
    attributes = event.get("attributes")
    if not isinstance(attributes, dict):
        return ""
    values = attributes.get("values")
    if not isinstance(values, dict):
        return ""
    message = values.get("message")
    return message if isinstance(message, str) else ""


def _compact_aura_context(context: Mapping[str, Any]) -> dict[str, Any]:
    """Return the request context produced by Salesforce's browser runtime."""
    required = ("mode", "fwuid", "app", "loaded")
    if any(key not in context for key in required):
        raise PayAsUGOProtocolError("Aura context is missing required fields")
    return {
        "mode": context["mode"],
        "fwuid": context["fwuid"],
        "app": context["app"],
        "loaded": context["loaded"],
        "dn": [],
        "globals": {"srcdoc": True},
        "uad": True,
    }


def _login_redirect(result: Any) -> str:
    """Validate that Salesforce returned a login redirect, not an error message."""
    if not isinstance(result, str) or not result:
        raise PayAsUGOAuthError("PayAsUGO rejected the supplied credentials")
    if not result.startswith(("/", "http://", "https://")):
        raise PayAsUGOAuthError("PayAsUGO rejected the supplied credentials")
    return result


def _login_event_url(payload: Mapping[str, Any]) -> str | None:
    """Return the redirect URL emitted after a successful Salesforce login."""
    events = payload.get("events")
    if not isinstance(events, list):
        return None
    for event in events:
        if not isinstance(event, dict):
            continue
        attributes = event.get("attributes")
        if not isinstance(attributes, dict):
            continue
        values = attributes.get("values")
        if not isinstance(values, dict):
            continue
        url = values.get("url")
        if isinstance(url, str) and url:
            return url
    return None


def _aura_route(descriptor: str) -> str:
    """Return Salesforce's request-routing key for an Aura descriptor."""
    routes = {
        (
            "serviceComponent://ui.communities.components.aura.components."
            "forceCommunity.navigationMenu.NavigationMenuDataProviderController/"
            "ACTION$getNavigationMenu"
        ): (
            "ui-communities-components-aura-components-forceCommunity-navigationMenu."
            "NavigationMenuDataProvider.getNavigationMenu"
        ),
        (
            "serviceComponent://ui.self.service.components.profileMenu."
            "ProfileMenuController/ACTION$getProfileMenuResponse"
        ): "ui-self-service-components-profileMenu.ProfileMenu.getProfileMenuResponse",
        (
            "serviceComponent://ui.force.components.controllers.hostConfig."
            "HostConfigController/ACTION$getConfigData"
        ): "ui-force-components-controllers-hostConfig.HostConfig.getConfigData",
        "apex://LightningLoginFormController/ACTION$isGuestUser": (
            "other.LightningLoginForm.isGuestUser"
        ),
        "apex://LightningLoginFormController/ACTION$getForgotPasswordUrl": (
            "other.LightningLoginForm.getForgotPasswordUrl"
        ),
        "apex://LightningLoginFormController/ACTION$login": (
            "other.LightningLoginForm.login"
        ),
        "apex://PaytAppController/ACTION$getUserDetails": (
            "other.PaytApp.getUserDetails"
        ),
        "aura://ApexActionController/ACTION$execute": "aura.ApexAction.execute",
    }
    try:
        return routes[descriptor]
    except KeyError as err:
        raise PayAsUGOProtocolError(
            f"Unsupported Aura action: {descriptor}"
        ) from err


def _extract_aura_bootstrap(
    content: str,
) -> tuple[dict[str, Any], str, str | None]:
    """Extract Aura context and CSRF token from a Salesforce bootstrap page."""
    markers = (
        "auraConfig",
        "Aura.bootstrap",
        "auraInitConfig",
    )
    candidates: list[dict[str, Any]] = []
    for marker in markers:
        start = 0
        while (position := content.find(marker, start)) != -1:
            brace = content.find("{", position)
            if brace == -1:
                break
            try:
                candidate = _decode_balanced_json(content, brace)
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
            cookie_name = candidate.get("eikoocnekot")
            return (
                context,
                str(token),
                cookie_name if isinstance(cookie_name, str) else None,
            )

    context_match = re.search(r'"context"\s*:', content)
    if context_match:
        brace = content.find("{", context_match.end())
        if brace != -1:
            context = _decode_balanced_json(content, brace)
            if isinstance(context, dict) and "fwuid" in context:
                token_match = re.search(
                    r'"(?:token|csrfToken)"\s*:\s*"([^"]+)"', content
                )
                cookie_match = re.search(
                    r'"eikoocnekot"\s*:\s*"([^"]+)"', content
                )
                return (
                    context,
                    token_match.group(1) if token_match else "null",
                    cookie_match.group(1) if cookie_match else None,
                )

    raise PayAsUGOProtocolError("Could not find Salesforce Aura bootstrap data")


def _extract_bootstrap_script_url(html: str) -> str:
    """Return the Aura bootstrap script URL from a Salesforce page."""
    matches = re.findall(
        r'<script[^>]+src=["\']([^"\']*bootstrap\.js[^"\']*)["\']',
        html,
        flags=re.IGNORECASE,
    )
    if not matches:
        raise PayAsUGOProtocolError("Could not find Salesforce bootstrap script")
    return matches[-1].replace("&amp;", "&")


def _decode_balanced_json(text: str, start: int) -> Any:
    decoder = json.JSONDecoder()
    value, _ = decoder.raw_decode(text[start:])
    return value


def _unwrap_return_value(value: Any) -> dict[str, Any]:
    while True:
        if isinstance(value, dict) and "returnValue" in value:
            value = value["returnValue"]
            continue
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                break
            continue
        break
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
