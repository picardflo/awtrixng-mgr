"""Place search — what replaced asking people for their own latitude."""

import httpx
import pytest
import respx

from app.core.errors import AwtrixNgError
from app.services.places import ENDPOINT, search

RESPONSE = {
    "results": [
        {
            "name": "Lyon", "admin1": "Rhône-Alpes", "country": "France",
            "country_code": "FR", "latitude": 45.74906, "longitude": 4.84789,
            "timezone": "Europe/Paris", "population": 520774,
        },
        {
            "name": "Lyon", "admin1": "Mississippi", "country": "United States",
            "country_code": "US", "latitude": 34.21789, "longitude": -90.54204,
            "timezone": "America/Chicago", "population": 330,
        },
        {"name": "Broken", "latitude": "not a number", "longitude": 0},
    ]
}


@respx.mock
async def test_returns_places_in_the_order_the_api_gives():
    respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json=RESPONSE))
    found = await search("Lyon")
    assert [place.country_code for place in found] == ["FR", "US"]


@respx.mock
async def test_label_disambiguates_same_named_towns():
    respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json=RESPONSE))
    found = await search("Lyon")
    assert found[0].label == "Lyon, Rhône-Alpes, FR"
    assert found[1].label == "Lyon, Mississippi, US"


@respx.mock
async def test_malformed_entry_is_skipped_not_fatal():
    respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json=RESPONSE))
    assert len(await search("Lyon")) == 2


@respx.mock
async def test_language_is_passed_through():
    route = respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json={"results": []}))
    await search("Lyon", language="fr")
    assert route.calls.last.request.url.params["language"] == "fr"


@pytest.mark.parametrize("query", ["", " ", "a", " a "])
async def test_short_queries_do_not_hit_the_api(query):
    """Typing one letter must not fire a request per keystroke."""
    with respx.mock:
        route = respx.get(ENDPOINT)
        assert await search(query) == []
        assert route.call_count == 0


@respx.mock
async def test_no_result_is_an_empty_list_not_an_error():
    respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json={}))
    assert await search("zzzzzz") == []


@respx.mock
async def test_unreachable_api_is_explained():
    respx.get(ENDPOINT).mock(side_effect=httpx.ConnectTimeout(""))
    with pytest.raises(AwtrixNgError) as caught:
        await search("Lyon")
    assert caught.value.code == "places.unreachable"
    assert caught.value.params["reason"] == "ConnectTimeout"


@respx.mock
async def test_rejected_request_is_explained():
    respx.get(ENDPOINT).mock(return_value=httpx.Response(400))
    with pytest.raises(AwtrixNgError, match="refused"):
        await search("Lyon")
