from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from infrahub_sdk import Config, InfrahubClient, InfrahubClientSync

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
    """The relogin retry must carry the freshly-refreshed token, not the stale per-request snapshot.

    Regression: the X-Priority merge flip let the stale snapshot Authorization overwrite the
    token refreshed mid-flight by handle_relogin, so the retry was sent with the expired token.
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
        await client.execute_graphql(query=query, branch_name="main")
    else:
        client.execute_graphql(query=query, branch_name="main")

    graphql_requests = [r for r in httpx_mock.get_requests() if str(r.url) == "http://mock/graphql/main"]
    assert len(graphql_requests) == 2
    # The first attempt used the stale token; the retry must use the refreshed one.
    assert graphql_requests[0].headers["Authorization"] == "Bearer OLD"
    assert graphql_requests[1].headers["Authorization"] == "Bearer NEW"


@pytest.mark.parametrize("client_type", client_types)
def test_merge_request_headers_reasserts_live_auth(client_type: str) -> None:
    """Directly exercise the merge helper: per-request X-Priority wins, live auth is re-asserted."""
    client = _build_password_client(client_type)
    client.headers["X-Priority"] = "normal"

    # A stale per-request snapshot: old token + a per-request priority override.
    snapshot = dict(client.headers)
    snapshot["X-Priority"] = "high"

    # Simulate a mid-flight token refresh on the live client headers.
    client.headers["Authorization"] = "Bearer NEW"

    merged = client._merge_request_headers(snapshot)

    # Per-request override wins over the base default.
    assert merged["X-Priority"] == "high"
    # Live/refreshed auth header wins over the stale snapshot value.
    assert merged["Authorization"] == "Bearer NEW"
