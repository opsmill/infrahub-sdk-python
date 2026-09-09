from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from infrahub_sdk import Config, InfrahubClient, InfrahubClientSync
from infrahub_sdk.constants import Priority
from infrahub_sdk.exceptions import AuthenticationError

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

client_types = ["standard", "sync"]


def _build_password_client(client_type: str) -> InfrahubClient | InfrahubClientSync:
    """Build a password-authenticated client primed with a stale bearer token."""
    config = Config(address="http://mock", username="admin", password="password", insert_tracker=True)
    client: InfrahubClient | InfrahubClientSync = (
        InfrahubClient(config=config) if client_type == "standard" else InfrahubClientSync(config=config)
    )

    # Prime the client as if it had already logged in with a now-stale token.
    client.access_token = "OLD"
    client.refresh_token = "refresh-token"
    client.headers["Authorization"] = "Bearer OLD"
    return client


@pytest.mark.parametrize("client_type", client_types)
async def test_relogin_retry_uses_refreshed_auth_header(client_type: str, httpx_mock: HTTPXMock) -> None:
    """The relogin retry carries the freshly-refreshed token, while a per-request priority override rides both attempts.

    The transport helpers merge the per-request delta (here, the priority override) over the
    current base headers, so the retry picks up the token refreshed mid-flight instead of a
    stale snapshot, and the priority override is preserved across the retry.
    """
    # First GraphQL POST returns 401 with an expired-signature error.
    httpx_mock.add_response(
        method="POST",
        url="http://mock/graphql/main",
        status_code=401,
        json={"errors": [{"message": "Expired Signature"}]},
    )
    # The relogin refresh call issues a NEW access token.
    httpx_mock.add_response(
        method="POST",
        url="http://mock/api/auth/refresh",
        json={"access_token": "NEW"},
    )
    # The retried GraphQL POST succeeds; it must carry the refreshed token.
    httpx_mock.add_response(
        method="POST",
        url="http://mock/graphql/main",
        json={"data": {"InfrahubInfo": {"version": "1.0"}}},
    )

    client = _build_password_client(client_type)
    query = "query { InfrahubInfo { version }}"
    if isinstance(client, InfrahubClient):
        await client.execute_graphql(query=query, branch_name="main", priority=Priority.HIGH)
    else:
        client.execute_graphql(query=query, branch_name="main", priority=Priority.HIGH)

    graphql_requests = [r for r in httpx_mock.get_requests() if str(r.url) == "http://mock/graphql/main"]
    assert len(graphql_requests) == 2
    # The first attempt used the stale token; the retry must use the refreshed one.
    assert graphql_requests[0].headers["Authorization"] == "Bearer OLD"
    assert graphql_requests[1].headers["Authorization"] == "Bearer NEW"
    # The per-request priority override rides both the initial attempt and the retry.
    assert all(r.headers["x-priority"] == "high" for r in graphql_requests)


@dataclass
class RefreshCase:
    name: str
    body: dict | str
    expected_attempts: int
    expected_message: str


REFRESH_CASES = [
    RefreshCase(
        name="catalogued-token-expired-refreshes",
        body={"errors": [{"message": "Token has expired", "extensions": {"code": "TOKEN_EXPIRED"}}]},
        expected_attempts=2,
        expected_message="Token has expired",
    ),
    RefreshCase(
        name="legacy-expired-signature-refreshes",
        body={"errors": [{"message": "Expired Signature"}]},
        expected_attempts=2,
        expected_message="Expired Signature",
    ),
    RefreshCase(
        name="unrelated-401-does-not-refresh",
        body={"errors": [{"message": "Invalid credentials", "extensions": {"code": "AUTHENTICATION_REQUIRED"}}]},
        expected_attempts=1,
        expected_message="Invalid credentials",
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in REFRESH_CASES])
@pytest.mark.parametrize("client_type", client_types)
async def test_refresh_decision_reads_the_code_then_falls_back_to_the_message(
    client_type: str, case: RefreshCase, httpx_mock: HTTPXMock
) -> None:
    """The silent refresh is decided by the catalogue code, with the legacy string as the fallback."""
    httpx_mock.add_response(
        method="POST", url="http://mock/graphql/main", status_code=401, json=case.body, is_reusable=True
    )
    if case.expected_attempts > 1:
        httpx_mock.add_response(method="POST", url="http://mock/api/auth/refresh", json={"access_token": "NEW"})

    client = _build_password_client(client_type)
    query = "query { InfrahubInfo { version }}"

    with pytest.raises(AuthenticationError, match=case.expected_message):
        if isinstance(client, InfrahubClient):
            await client.execute_graphql(query=query, branch_name="main")
        else:
            client.execute_graphql(query=query, branch_name="main")

    graphql_requests = [r for r in httpx_mock.get_requests() if str(r.url) == "http://mock/graphql/main"]
    assert len(graphql_requests) == case.expected_attempts


@dataclass
class UnreadableBodyCase:
    name: str
    text: str


UNREADABLE_BODY_CASES = [
    UnreadableBodyCase(name="html-proxy-error-page", text="<html><body><h1>502 Bad Gateway</h1></body></html>"),
    UnreadableBodyCase(name="empty-body", text=""),
    # Valid JSON, but not the object the envelope is supposed to be. A gateway that answers in its
    # own format reaches the same code path, and reading `errors` off it must not throw.
    UnreadableBodyCase(name="json-array", text='[{"message": "denied"}]'),
    UnreadableBodyCase(name="json-null", text="null"),
    UnreadableBodyCase(name="json-string", text='"denied"'),
    UnreadableBodyCase(name="json-number", text="401"),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in UNREADABLE_BODY_CASES])
@pytest.mark.parametrize("client_type", client_types)
async def test_refresh_decision_tolerates_a_body_it_cannot_read(
    client_type: str, case: UnreadableBodyCase, httpx_mock: HTTPXMock
) -> None:
    """A 401 body the SDK cannot read must surface as an AuthenticationError, never as an SDK error."""
    httpx_mock.add_response(
        method="POST", url="http://mock/graphql/main", status_code=401, text=case.text, is_reusable=True
    )

    client = _build_password_client(client_type)
    query = "query { InfrahubInfo { version }}"

    with pytest.raises(AuthenticationError, match="HTTP 401"):
        if isinstance(client, InfrahubClient):
            await client.execute_graphql(query=query, branch_name="main")
        else:
            client.execute_graphql(query=query, branch_name="main")

    graphql_requests = [r for r in httpx_mock.get_requests() if str(r.url) == "http://mock/graphql/main"]
    assert len(graphql_requests) == 1, "a body carrying no refresh signal means no retry"


@pytest.mark.parametrize("client_type", client_types)
def test_merge_request_headers_layers_delta_over_live_base(client_type: str) -> None:
    """The merge helper layers the per-request delta over the current base headers.

    A delta with no auth key leaves the live base auth intact (so a refreshed token wins), while
    an explicit per-request override — of a normal header or of auth itself — takes precedence.
    """
    client = _build_password_client(client_type)
    client.headers["X-Priority"] = "medium"

    # A delta carrying only a per-request priority override (no auth).
    merged = client._merge_request_headers({"X-Priority": "high"})
    assert merged["X-Priority"] == "high"  # per-request override wins over the base default
    assert merged["Authorization"] == "Bearer OLD"  # base auth is preserved from the live headers

    # After a mid-flight token refresh, a delta with no auth picks up the fresh token.
    client.headers["Authorization"] = "Bearer NEW"
    assert client._merge_request_headers({"X-Priority": "high"})["Authorization"] == "Bearer NEW"

    # An explicit per-request auth override is respected (the caller owns relogin in that case).
    assert client._merge_request_headers({"Authorization": "Bearer CALLER"})["Authorization"] == "Bearer CALLER"
