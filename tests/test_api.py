"""Tests for the PayAsUGO API parsing helpers."""

from datetime import date

from custom_components.payasugo.api import (
    _add_months,
    _extract_aura_bootstrap,
    _parse_collection,
    _unwrap_return_value,
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
    context, token = _extract_aura_bootstrap(html)
    assert context["fwuid"] == "example"
    assert token == "example-token"


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

