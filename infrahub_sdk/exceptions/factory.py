"""Raise-time construction of an exception from a server response envelope.

Every authentication and GraphQL raise site that has a server response behind it funnels through
here, so envelope parsing lives in one place rather than being repeated per call site. Both factories
are total: a shape the parser does not recognise degrades to the generic exception that call site
raises anyway, never to a decode error or a TypeError originating in the SDK.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError as PayloadValidationError

from .base import (
    AuthenticationError,
    Error,
    GraphQLError,
    as_error_list,
    code_names_the_failure,
    graphql_default_message,
)
from .catalogue import exception_from_payload

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


def _governing_message(errors: Any) -> str:
    """The message of the error the code came from, which is the first one.

    Only this error's message may be named beside the code. Joining the whole list would file every
    later error under a code that is not theirs; the complete list stays on `exc.errors`.
    """
    if not isinstance(errors, list) or not errors:
        return ""
    first = errors[0]
    message = first.get("message") if isinstance(first, dict) else None
    return message if isinstance(message, str) else ""


def _named_by_code(code: str, message: str) -> str:
    """The message for a described failure: the code and the server's own words, and no query text.

    Callers apply this only where the governing error carried a message, since a bare code is a
    worse headline than what the transport would otherwise produce. The query stays on `exc.query`.
    """
    return f"{code}: {message}"


def _replace_message(exc: Error, message: str) -> None:
    """Swap the message of an exception that is already built.

    `args` is reassigned alongside it because that, not `message`, is what `str()` reads on a class
    that does not override `__str__`.
    """
    exc.message = message
    exc.args = (message,)


def _payload_of(extensions: dict[str, Any] | None) -> Mapping[str, Any]:
    """The governing error's payload, or an empty one where the envelope carried none.

    An absent payload is not the same as a malformed one: a code whose fields are all optional still
    resolves to its class, while one with required fields fails the validation below and falls back.
    """
    data = extensions.get("data") if extensions is not None else None
    return data if isinstance(data, Mapping) else {}


def _catalogued_exception(code: str | None, extensions: dict[str, Any] | None) -> GraphQLError | None:
    """The class the catalogue binds `code` to, built from the payload the envelope carries.

    Resolution and validation both belong to the generated bindings: each code's payload is validated
    against its own model and handed to that class's `from_payload`, so the factory never assembles
    an attribute itself and never has to widen a payload type to reach a constructor.

    `None` means no class was resolved - the code has none, or its payload violates what the
    catalogue declares for it - and the caller then raises the generic class for the transport it
    observed, with the code still readable.
    """
    if code is None:
        return None
    try:
        exception = exception_from_payload(code=code, data=_payload_of(extensions))
    except PayloadValidationError:
        # The caller is already failing, so a validation error from inside the SDK would replace the
        # server's reason with one of the SDK's own.
        LOGGER.debug("Payload for %s does not match what the catalogue declares: %r", code, extensions, exc_info=True)
        return None
    if exception is None:
        LOGGER.debug("These bindings have no class for the catalogue code %s: %r", code, extensions)
    return exception


def _has_no_sentence_of_its_own(exc: GraphQLError) -> bool:
    """Whether the class supplied no message of its own when it built itself from its payload.

    A class that predates the catalogue writes its own sentence; one bound to a code takes the
    GraphQL default, which names the query and errors it was given - and `from_payload` gives it
    neither. Asking the instance rather than a fixed string keeps that true if a class ever starts
    passing them.
    """
    return exc.message == graphql_default_message(query=exc.query, errors=exc.errors)


def _log_unresolved_code(code: str | None, extensions: dict[str, Any] | None, source: str) -> None:
    """Record a response the SDK read no catalogue code from, whatever the reason.

    The whole `extensions` mapping is logged rather than its `code` alone, since the commonest shapes
    here carry no `code` at all and the rest of the mapping is what identifies the server.
    """
    if code is None:
        LOGGER.debug("No catalogue code resolved from %s error extensions: %r", source, extensions)


def token_expired_in(errors: Any) -> bool:
    """Whether a decoded `errors` array reports the caller's token as expired.

    Lives here so the client's silent-refresh decision reads the envelope through the same parser as
    everything else. Every error is scanned rather than only the first: a stale token is a fact about
    the request, not about which error happens to lead. The legacy message check is the fallback for
    servers that predate the catalogue; `query_groups` keeps the only other one, for the same reason.
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
    unreordered. A code the catalogue binds to a class raises that class; every other failure raises
    `GraphQLError`, and one the server's catalogue could not describe keeps the message this call site
    has always produced, query text included.

    This is the GraphQL branch, so its fallback is `GraphQLError` whatever status the code declares.
    A code that reaches an `errors` array was read off this transport, and a declared 401 does not
    make it an authentication failure the SDK observed.
    """
    extensions = _first_extensions(errors)
    code = _catalogue_code(extensions)
    governing = _governing_message(errors)
    message = _named_by_code(code, governing) if code_names_the_failure(code) and governing else None

    catalogued = _catalogued_exception(code=code, extensions=extensions)
    if catalogued is not None:
        exc: GraphQLError = catalogued
        # An undescribed failure leaves a class with its own sentence holding it, and one without
        # holding a placeholder that names neither the query nor the errors it was never given.
        if message is None and _has_no_sentence_of_its_own(exc):
            message = graphql_default_message(query=query, errors=errors)
        if message is not None:
            _replace_message(exc, message)
        exc.query = query
        exc.variables = variables
    else:
        exc = GraphQLError(errors=errors, query=query, variables=variables, message=message)

    exc.errors = as_error_list(errors)
    exc.code = code
    declared_status = _declared_http_status(extensions)
    if declared_status is not None:
        # Conditional so a class that declares the catalogue's status keeps it where the envelope
        # omitted one.
        exc.http_status = declared_status
    exc.extensions = extensions
    _log_unresolved_code(code=code, extensions=extensions, source="GraphQL")
    return exc


def authentication_error_from_response(response: httpx.Response) -> AuthenticationError:
    """Build the exception for a response the SDK rejected as an authentication failure.

    Most call sites reach here on a 401 or 403, but the two that handle a failed token refresh reach
    it on any other status, so the status itself is not assumed. The message joins the server's
    messages with `" | "`, as every call site this replaces did, falling back to the REST API's bare
    `detail` string and then to the plain status. A body the SDK cannot read as an envelope therefore
    still names the status rather than surfacing a decode error in place of the authentication failure.

    A described failure names its code and the governing error's message instead, on the same rule as
    the GraphQL path: only the error the code came from may be named beside it, and the complete list
    stays on `exc.errors`.

    No code is resolved to a class here. Every catalogued class descends from `GraphQLError`, so
    raising one for a response the SDK observed as an authentication failure would put it out of
    reach of `except AuthenticationError`.
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
    code = _catalogue_code(extensions)
    governing = _governing_message(errors)
    if code_names_the_failure(code) and governing:
        message = _named_by_code(code, governing)

    exc = AuthenticationError(message)
    exc.code = code
    exc.http_status = _declared_http_status(extensions)
    exc.extensions = extensions
    exc.errors = as_error_list(errors)
    _log_unresolved_code(code=code, extensions=extensions, source="authentication")
    return exc
