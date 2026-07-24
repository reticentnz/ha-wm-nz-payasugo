"""Tests for the PayAsUGO API parsing helpers."""

from datetime import date
from http.cookies import SimpleCookie
from types import SimpleNamespace

from custom_components.payasugo.api import (
    PayAsUGOClient,
    _add_months,
    _aura_route,
    _aura_exception_message,
    _compact_aura_context,
    _decode_aura_response,
    _extract_aura_bootstrap,
    _extract_bootstrap_script_url,
    _login_event_url,
    _login_redirect,
    _parse_collection,
    _redact_error_detail,
    _unwrap_return_value,
)


def test_remember_response_cookies_including_redirects() -> None:
    redirect_cookies = SimpleCookie()
    redirect_cookies.load("redirect-token=first")
    response_cookies = SimpleCookie()
    response_cookies.load("authenticated-token=second")
    response = SimpleNamespace(
        history=(SimpleNamespace(cookies=redirect_cookies),),
        cookies=response_cookies,
    )
    client = object.__new__(PayAsUGOClient)
    client._response_cookies = {}

    client._remember_response_cookies(response)

    assert client._response_cookies == {
        "redirect-token": "first",
        "authenticated-token": "second",
    }


def test_aura_exception_message() -> None:
    payload = _decode_aura_response(
        b'*/{"exceptionMessage":"Client is out of sync",'
        b'"exceptionEvent":true}/*ERROR*/'
    )
    assert _aura_exception_message(payload) == "Client is out of sync"


def test_decode_aura_response_with_prefix() -> None:
    assert _decode_aura_response(b'*/{\"actions\":[]}') == {"actions": []}
    assert _decode_aura_response(b'*/{\"actions\":[]}/*') == {"actions": []}
    assert _decode_aura_response(
        b'*/{\"event\":{\"descriptor\":\"markup://aura:doneWaiting\"}}'
        b'/**/{\"actions\":[{\"state\":\"SUCCESS\"}]}/*'
    ) == {"actions": [{"state": "SUCCESS"}]}
    assert _decode_aura_response(b'while(1); {\"actions\":[]}') == {"actions": []}


def test_login_event_url() -> None:
    assert _login_event_url(
        {
            "events": [
                {
                    "attributes": {
                        "values": {
                            "url": "/s/",
                        }
                    }
                }
            ]
        }
    ) == "/s/"


def test_login_event_url_missing() -> None:
    assert _login_event_url({"events": []}) is None


def test_login_redirect_rejects_error_message() -> None:
    try:
        _login_redirect("Your login was unsuccessful.")
    except Exception as err:
        assert type(err).__name__ == "PayAsUGOAuthError"
    else:
        raise AssertionError("Expected the login error message to be rejected")


def test_login_redirect_accepts_path() -> None:
    assert _login_redirect("/s/") == "/s/"


def test_compact_aura_context() -> None:
    assert _compact_aura_context(
        {
            "mode": "PROD",
            "fwuid": "example",
            "app": "siteforce:loginApp2",
            "loaded": {"APPLICATION@markup://siteforce:loginApp2": "value"},
            "componentDefs": {"unsafe": "100%"},
        }
    ) == {
        "mode": "PROD",
        "fwuid": "example",
        "app": "siteforce:loginApp2",
        "loaded": {"APPLICATION@markup://siteforce:loginApp2": "value"},
        "dn": [],
        "globals": {"srcdoc": True},
        "uad": True,
    }


def test_redact_error_detail() -> None:
    detail = _redact_error_detail(
        " Login failed for user@example.com using secret-password ",
        "user@example.com",
        "secret-password",
    )
    assert detail == "Login failed for [redacted] using [redacted]"


def test_aura_routes() -> None:
    assert _aura_route(
        "apex://LightningLoginFormController/ACTION$isGuestUser"
    ) == "other.LightningLoginForm.isGuestUser"
    assert _aura_route(
        "apex://LightningLoginFormController/ACTION$getForgotPasswordUrl"
    ) == "other.LightningLoginForm.getForgotPasswordUrl"
    assert (
        _aura_route("apex://LightningLoginFormController/ACTION$login")
        == "other.LightningLoginForm.login"
    )
    assert (
        _aura_route("apex://PaytAppController/ACTION$getUserDetails")
        == "other.PaytApp.getUserDetails"
    )
    assert (
        _aura_route("aura://ApexActionController/ACTION$execute")
        == "aura.ApexAction.execute"
    )


def test_extract_aura_bootstrap() -> None:
    html = """
    <script>
    window.auraConfig = {
      "context": {"mode": "PROD", "fwuid": "example", "app": "siteforce:loginApp2"},
      "token": "example-token"
    };
    </script>
    """
    context, token, cookie_name = _extract_aura_bootstrap(html)
    assert context["fwuid"] == "example"
    assert token == "example-token"
    assert cookie_name is None


def test_extract_aura_cookie_name() -> None:
    html = """
    <script>
    var auraConfig = {
      "context": {"mode": "PROD", "fwuid": "example"},
      "token": null,
      "eikoocnekot": "__Host-example"
    };
    </script>
    """
    context, token, cookie_name = _extract_aura_bootstrap(html)
    assert context["fwuid"] == "example"
    assert token == "null"
    assert cookie_name == "__Host-example"


def test_extract_external_bootstrap_url() -> None:
    html = """
    <script src="/s/other.js"></script>
    <script src="/s/bootstrap.js?aura.attributes=x&amp;mode=prod"></script>
    """
    assert _extract_bootstrap_script_url(html) == (
        "/s/bootstrap.js?aura.attributes=x&mode=prod"
    )


def test_parse_collection() -> None:
    collection = _parse_collection(
        {
            "Id": "event-1",
            "EventDate__c": "2026-08-11",
            "Status__c": "Paused",
            "Product_Family__c": "General waste",
            "Within_Long_Pause_Period__c": False,
        }
    )
    assert collection.collection_date == date(2026, 8, 11)
    assert collection.enabled is False
    assert collection.product_family == "General waste"


def test_unwrap_return_value() -> None:
    assert _unwrap_return_value(
        {"returnValue": {"returnValue": {"currentEvents": []}, "cacheable": False}}
    ) == {"currentEvents": []}


def test_add_months_across_year() -> None:
    assert _add_months(date(2026, 12, 1), 2) == date(2027, 2, 1)
