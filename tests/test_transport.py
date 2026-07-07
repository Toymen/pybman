from __future__ import annotations

import pytest

from pybman import (
    AuthenticationError,
    AuthorizationError,
    BadRequestError,
    NotFoundError,
    ServerError,
)
from pybman._http import Transport
from pybman.exceptions import PubManHTTPError

from .conftest import BASE, REST


@pytest.fixture
def transport() -> Transport:
    return Transport(BASE, retries=0)


def test_urls_derived_from_base():
    t = Transport("https://qa.pure.mpdl.mpg.de/")
    assert t.base_url == "https://qa.pure.mpdl.mpg.de"
    assert t.rest_url == "https://qa.pure.mpdl.mpg.de/rest"
    assert t.cone_url == "https://qa.pure.mpdl.mpg.de/cone"


def test_login_posts_plaintext_credentials_and_stores_token(responses, transport):
    responses.post(f"{REST}/login", json={}, headers={"Token": "tok-1"})
    transport.login("alice", "secret")
    assert transport.token == "tok-1"
    assert transport.is_authenticated
    request = responses.calls[0].request
    assert request.body == b"alice:secret"
    assert request.headers["Content-Type"] == "text/plain"


def test_login_failure_raises_authentication_error(responses, transport):
    responses.post(f"{REST}/login", status=401)
    with pytest.raises(AuthenticationError):
        transport.login("alice", "wrong")
    assert transport.token is None


def test_login_without_credentials_raises(transport):
    with pytest.raises(AuthenticationError):
        transport.login()


def test_authenticated_request_logs_in_lazily(responses):
    transport = Transport(BASE, credentials=("alice", "secret"), retries=0)
    responses.post(f"{REST}/login", json={}, headers={"Token": "tok-lazy"})
    responses.get(f"{REST}/protected", json={"ok": True})
    payload = transport.request_json("GET", "/protected", authenticated=True)
    assert payload == {"ok": True}
    assert responses.calls[1].request.headers["Authorization"] == "tok-lazy"


def test_authenticated_request_without_credentials_raises(transport):
    with pytest.raises(AuthenticationError):
        transport.request("GET", "/protected", authenticated=True)


def test_expired_token_triggers_one_relogin(responses):
    transport = Transport(BASE, credentials=("alice", "secret"), token="stale", retries=0)
    responses.get(f"{REST}/thing", status=401)
    responses.post(f"{REST}/login", json={}, headers={"Token": "fresh"})
    responses.get(f"{REST}/thing", json={"fine": 1})
    assert transport.request_json("GET", "/thing", authenticated=True) == {"fine": 1}
    assert transport.token == "fresh"


def test_token_sent_on_anonymous_endpoints_when_present(responses):
    transport = Transport(BASE, token="tok-x", retries=0)
    responses.get(f"{REST}/items/item_1", json={})
    transport.request("GET", "/items/item_1")
    assert responses.calls[0].request.headers["Authorization"] == "tok-x"


def test_logout_clears_token_and_never_raises(responses):
    transport = Transport(BASE, token="tok-x", retries=0)
    responses.get(f"{REST}/logout", status=500)
    transport.logout()
    assert transport.token is None
    transport.logout()  # no token: no request, no error


def test_whoami_parses_grants(responses):
    transport = Transport(BASE, token="tok-x", retries=0)
    responses.get(
        f"{REST}/login/who",
        json={
            "objectId": "user_1",
            "loginname": "alice",
            "grantList": [
                {"role": "MODERATOR", "objectRef": "ctx_1"},
                {"role": "MODERATOR", "objectRef": "ctx_2"},
                {"role": "DEPOSITOR"},
            ],
        },
    )
    account = transport.whoami()
    assert account.login_name == "alice"
    assert account.grants["MODERATOR"] == ["ctx_1", "ctx_2"]
    assert account.roles == ["DEPOSITOR", "MODERATOR"]


@pytest.mark.parametrize(
    ("status", "exc"),
    [
        (400, BadRequestError),
        (401, AuthenticationError),
        (403, AuthorizationError),
        (404, NotFoundError),
        (500, ServerError),
        (418, PubManHTTPError),
    ],
)
def test_http_errors_are_mapped(responses, transport, status, exc):
    responses.get(f"{REST}/broken", status=status, json={"message": "nope"})
    with pytest.raises(exc) as excinfo:
        transport.request("GET", "/broken")
    assert excinfo.value.status_code == status
    assert "nope" in str(excinfo.value)


def test_none_params_are_dropped(responses, transport):
    responses.get(f"{REST}/items/search/scroll", json={"numberOfRecords": 0})
    transport.request("GET", "/items/search/scroll", params={"scrollId": "s", "format": None})
    assert responses.calls[0].request.url == f"{REST}/items/search/scroll?scrollId=s"


def test_request_json_handles_empty_body(responses, transport):
    responses.get(f"{REST}/empty", body=b"", status=200)
    assert transport.request_json("GET", "/empty") is None
