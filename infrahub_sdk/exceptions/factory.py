"""Raise-time construction of an exception from a server response envelope.

Every authentication and GraphQL raise site that has a server response behind it funnels through
here, so envelope parsing lives in one place rather than being repeated per call site. Both factories
are total: a shape the parser does not recognise degrades to the generic exception that call site
raises anyway, never to a decode error or a TypeError originating in the SDK.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .base import AuthenticationError, GraphQLError, as_error_list

if TYPE_CHECKING:
    import httpx

LOGGER = logging.getLogger("infrahub_sdk")

# The names the package façade re-exports. `token_expired_in` is deliberately absent: it is public to
# the SDK, which imports it from this module, but it is not part of the published exception surface.
__all__ = ["authentication_error_from_response", "graphql_error_from_response"]


def _extensions_of(error: Any) -> dict[str, Any] | None:
    if not isinstance(error, dict):
        return None
    extensions = error.get("extensions")
    return extensions if isinstance(extensions, dict) else None


def _first_extensions(errors: Any) -> dict[str, Any] | None:
    """Extensions of the governing error: the first one, whether or not it carries a code."""
    if not isinstance(errors, list) or not errors:
        return None
    return _extensions_of(errors[0])


def _catalogue_code(extensions: dict[str, Any] | None) -> str | None:
    """Only a string is a catalogue code.

    A pre-catalogue envelope puts an integer here mirroring the HTTP status, which must never be
    mistaken for one.
    """
    if extensions is None:
        return None
    code = extensions.get("code")
    return code if isinstance(code, str) else None


def _declared_http_status(extensions: dict[str, Any] | None) -> int | None:
    if extensions is None:
        return None
    status = extensions.get("http_status")
    # bool is an int subclass, and a JSON `true` here is not a status.
    return status if isinstance(status, int) and not isinstance(status, bool) else None


def _server_messages(errors: Any) -> list[str]:
    if not isinstance(errors, list):
        return []
    return [error["message"] for error in errors if isinstance(error, dict) and isinstance(error.get("message"), str)]


def _detail_message(body: dict[str, Any]) -> str | None:
    """The REST API rejects a request with a bare `detail` string rather than an `errors` array."""
    detail = body.get("detail")
    return detail if isinstance(detail, str) and detail else None


def _log_unresolved_code(extensions: dict[str, Any] | None, source: str) -> None:
    if extensions is not None and _catalogue_code(extensions) is None:
        LOGGER.debug("No catalogue code resolved from %s error extensions: %r", source, extensions.get("code"))


def token_expired_in(errors: Any) -> bool:
    """Whether a decoded `errors` array reports the caller's token as expired.

    Lives here so the client's silent-refresh decision reads the envelope through the same parser as
    everything else. Every error is scanned rather than only the first: a stale token is a fact about
    the request, not about which error happens to lead. The legacy message check is the fallback for
    servers that predate the catalogue, and is the only place in the SDK that string still appears.
    """
    if not isinstance(errors, list):
        return False
    if any(_catalogue_code(_extensions_of(error)) == "TOKEN_EXPIRED" for error in errors):
        return True
    return "Expired Signature" in _server_messages(errors)


def graphql_error_from_response(
    errors: Any,
    query: str | None = None,
    variables: dict | None = None,
) -> GraphQLError:
    """Build the exception for an `errors` array returned on the GraphQL path.

    `errors` is raw decoded JSON, so it is read defensively. The complete list is retained
    unreordered, and the message is the one this call site has always produced.
    """
    extensions = _first_extensions(errors)
    exc = GraphQLError(errors=errors, query=query, variables=variables)
    exc.code = _catalogue_code(extensions)
    exc.http_status = _declared_http_status(extensions)
    exc.extensions = extensions
    _log_unresolved_code(extensions=extensions, source="GraphQL")
    return exc


def authentication_error_from_response(response: httpx.Response) -> AuthenticationError:
    """Build the exception for a response the SDK rejected as an authentication failure.

    Most call sites reach here on a 401 or 403, but the two that handle a failed token refresh reach
    it on any other status, so the status itself is not assumed. The message joins the server's
    messages with `" | "`, as every call site this replaces did, falling back to the REST API's bare
    `detail` string and then to the plain status. A body the SDK cannot read as an envelope therefore
    still names the status rather than surfacing a decode error in place of the authentication failure.
    """
    errors: Any = []
    message = f"HTTP {response.status_code}"

    # Read raw rather than through utils.decode_json, which raises JsonDecodeError on a body that is
    # not JSON. Tolerating that body is the whole point here, so the wrapping would be built and then
    # discarded. The catch stays broad because this runs while the caller is already failing: whatever
    # a proxy answered with, the authentication failure is what has to reach them.
    try:
        body = response.json()
    except Exception:
        LOGGER.debug("Authentication response body could not be parsed; using the plain status", exc_info=True)
    else:
        if isinstance(body, dict):
            errors = body.get("errors", [])
            # Each fallback only applies when the one before it yielded nothing, so a body carrying
            # no readable reason keeps the status rather than losing it to an empty join.
            message = " | ".join(_server_messages(errors)) or _detail_message(body) or message
        else:
            LOGGER.debug("Authentication response body is not an envelope object; using the plain status: %r", body)

    extensions = _first_extensions(errors)

    exc = AuthenticationError(message)
    exc.code = _catalogue_code(extensions)
    exc.http_status = _declared_http_status(extensions)
    exc.extensions = extensions
    exc.errors = as_error_list(errors)
    _log_unresolved_code(extensions=extensions, source="authentication")
    return exc
