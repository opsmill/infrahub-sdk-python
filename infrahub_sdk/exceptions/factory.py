"""Raise-time construction of an exception from a server response envelope.

Every authentication and GraphQL raise site that has a server response behind it funnels through
here, so envelope parsing lives in one place rather than being repeated per call site. Both factories
are total: a shape the parser does not recognise degrades to the generic exception that call site
raises anyway, never to a decode error or a TypeError originating in the SDK.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .base import (
    AuthenticationError,
    BranchNotFoundError,
    Error,
    GraphQLError,
    NodeNotFoundError,
    SchemaNotFoundError,
    as_error_list,
    code_names_the_failure,
)

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
    """The message for a described failure: the code and the server's message, and no query text.

    A described failure is one the server's catalogue has an entry for, so its own words are what the
    reader needs; the query stays on the exception as an attribute.

    Callers apply this only when the governing error carried a message. A code with nothing beside it
    is a worse headline than whatever that transport would otherwise have produced, and it is no loss
    of information: the code is on `exc.code` either way.
    """
    return f"{code}: {message}"


def _replace_message(exc: Error, message: str) -> None:
    """Swap the message of an exception that is already built.

    `args` is reassigned alongside it because that, not `message`, is what `str()` reads on a class
    that does not override `__str__`.
    """
    exc.message = message
    exc.args = (message,)


@dataclass
class _NodeNotFoundData:
    """Stands in for the generated payload model, which the SDK does not carry yet.

    Plain rather than frozen, because the payload protocols declare settable attributes: the shape
    the generated pydantic models will have.
    """

    node_kind: str
    identifier: str


@dataclass
class _BranchNotFoundData:
    branch_name: str


@dataclass
class _SchemaNotFoundData:
    kind: str


def _payload_strings(data: Any, names: tuple[str, ...]) -> dict[str, str] | None:
    """The named payload fields, when every one of them is present as a string.

    A payload that violates the catalogue's own contract yields `None` so the caller falls back to
    the generic class, rather than a TypeError raised from inside the SDK while the caller is
    already failing.
    """
    if not isinstance(data, dict):
        return None
    values = {name: data.get(name) for name in names}
    if any(not isinstance(value, str) for value in values.values()):
        return None
    return {name: value for name, value in values.items() if isinstance(value, str)}


def _adopted_exception(code: str | None, extensions: dict[str, Any] | None) -> GraphQLError | None:
    """The class that adopted `code`, built from the payload the envelope carries.

    Only the three codes the SDK already ships a class for are resolved here, and each class maps the
    payload itself through its own `from_payload`. Every other code raises the generic class for the
    transport with the code readable on `exc.code`; turning the rest into classes of their own is
    what the generated bindings buy.

    `None` means no class was resolved, whether because the code has none or because its payload did
    not carry the fields the class needs.
    """
    if code is None:
        return None
    data = extensions.get("data") if extensions is not None else None

    if code == NodeNotFoundError.CODE:
        node = _payload_strings(data=data, names=("node_kind", "identifier"))
        if node is not None:
            payload = _NodeNotFoundData(node_kind=node["node_kind"], identifier=node["identifier"])
            return NodeNotFoundError.from_payload(payload=payload)
    elif code == BranchNotFoundError.CODE:
        branch = _payload_strings(data=data, names=("branch_name",))
        if branch is not None:
            return BranchNotFoundError.from_payload(payload=_BranchNotFoundData(branch_name=branch["branch_name"]))
    elif code == SchemaNotFoundError.CODE:
        schema = _payload_strings(data=data, names=("kind",))
        if schema is not None:
            return SchemaNotFoundError.from_payload(payload=_SchemaNotFoundData(kind=schema["kind"]))
    else:
        return None

    LOGGER.debug("Payload for %s does not carry the fields its class needs: %r", code, data)
    return None


def _log_unresolved_code(extensions: dict[str, Any] | None, source: str) -> None:
    if extensions is not None and _catalogue_code(extensions) is None:
        LOGGER.debug("No catalogue code resolved from %s error extensions: %r", source, extensions.get("code"))


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
    unreordered. A code the SDK has adopted a class for raises that class; every other failure raises
    `GraphQLError`, and one the server's catalogue could not describe keeps the message this call site
    has always produced, query text included.
    """
    extensions = _first_extensions(errors)
    code = _catalogue_code(extensions)
    governing = _governing_message(errors)
    message = _named_by_code(code, governing) if code_names_the_failure(code) and governing else None

    adopted = _adopted_exception(code=code, extensions=extensions)
    if adopted is not None:
        exc: GraphQLError = adopted
        # An adopted class builds itself from its payload alone, so the envelope it came out of is
        # attached here. A silent governing error leaves `message` None, and the class its own text.
        if message is not None:
            _replace_message(exc, message)
        exc.query = query
        exc.variables = variables
    else:
        exc = GraphQLError(errors=errors, query=query, variables=variables, message=message)

    exc.errors = as_error_list(errors)
    exc.code = code
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

    A described failure names its code and the governing error's message instead, on the same rule as
    the GraphQL path: only the error the code came from may be named beside it, and the complete list
    stays on `exc.errors`.
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
    _log_unresolved_code(extensions=extensions, source="authentication")
    return exc
