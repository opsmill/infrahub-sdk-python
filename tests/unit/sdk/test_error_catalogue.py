"""The raise-time factories, exercised directly against captured response envelopes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from io import BytesIO
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from infrahub_sdk import Config, InfrahubClient, InfrahubClientSync
from infrahub_sdk.exceptions import (
    AttributeConstraintViolationError,
    AttributeInvalidTypeError,
    AttributeRequiredError,
    AuthenticationError,
    BranchAlreadyMergedError,
    BranchNeedsRebaseError,
    BranchNotFoundError,
    GraphQLError,
    MergeInProgressError,
    MergeRecoveryRequiredError,
    NodeNotFoundError,
    SchemaNotFoundError,
    UndefinedError,
    UniquenessViolationError,
    authentication_error_from_response,
    graphql_error_from_response,
)
from infrahub_sdk.exceptions.catalogue import CODE_TO_DATA_MODEL
from tests.helpers.fixtures import read_fixture

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from tests.unit.sdk.conftest import BothClients

FIXTURE_SUBDIR = "error_catalogue"
CODES_FIXTURE_SUBDIR = f"{FIXTURE_SUBDIR}/codes"

# The three codes that reach the SDK on either transport, so neither transport's class can be theirs.
CODES_WITHOUT_A_CLASS = {"AUTHENTICATION_REQUIRED", "PERMISSION_DENIED", "TOKEN_EXPIRED"}


def load_envelope(name: str) -> dict[str, Any]:
    return json.loads(read_fixture(file_name=name, fixture_subdir=FIXTURE_SUBDIR))


def load_code_envelope(code: str) -> dict[str, Any]:
    """The captured response for one catalogue code.

    Addressed by code rather than by listing the directory, so a code whose fixture is missing fails
    here instead of quietly dropping out of the parametrisation that is supposed to be exhaustive.
    """
    return json.loads(read_fixture(file_name=f"{code.lower()}.json", fixture_subdir=CODES_FIXTURE_SUBDIR))


def auth_response(envelope: dict[str, Any] | str, status_code: int = 401) -> httpx.Response:
    """Build the httpx response the SDK would have observed for a rejected request.

    The request is attached because `decode_json` reports the URL it failed on, and would raise
    looking for it rather than producing the JsonDecodeError the factory is meant to absorb.
    """
    request = httpx.Request("POST", "http://mock/graphql/main")
    if isinstance(envelope, str):
        return httpx.Response(status_code=status_code, text=envelope, request=request)
    return httpx.Response(status_code=status_code, json=envelope, request=request)


class TestGraphQLFactory:
    def test_reads_code_and_status_off_the_first_error(self) -> None:
        envelope = load_envelope("graphql_uniqueness_violation.json")

        exc = graphql_error_from_response(errors=envelope["errors"], query="query { x }", variables={"a": 1})

        assert isinstance(exc, GraphQLError)
        assert exc.code == "UNIQUENESS_VIOLATION"
        assert exc.http_status == 422
        assert exc.extensions is not None
        assert exc.extensions["data"] == {"node_kind": "TestPerson", "fields": ["name"]}

    def test_retains_the_complete_error_list_unreordered(self) -> None:
        envelope = load_envelope("graphql_multiple_errors.json")

        exc = graphql_error_from_response(errors=envelope["errors"])

        assert [error["message"] for error in exc.errors] == ["first failure", "second failure", "third failure"]
        assert exc.code == "SCHEMA_NOT_FOUND", "the first error governs, not the most specific one"

    def test_errors_is_a_sequence_of_dicts(self) -> None:
        envelope = load_envelope("graphql_uniqueness_violation.json")

        exc = graphql_error_from_response(errors=envelope["errors"])

        assert isinstance(exc.errors, list)
        assert all(isinstance(error, dict) for error in exc.errors)

    def test_query_and_variables_are_retained(self) -> None:
        envelope = load_envelope("graphql_uniqueness_violation.json")

        exc = graphql_error_from_response(errors=envelope["errors"], query="query { x }", variables={"a": 1})

        assert exc.query == "query { x }"
        assert exc.variables == {"a": 1}


@dataclass
class CodeCase:
    name: str
    expected_class: type[GraphQLError]
    expected_http_status: int
    expected_attributes: dict[str, Any]


CODE_CASES = [
    CodeCase(
        name="ATTRIBUTE_CONSTRAINT_VIOLATION",
        expected_class=AttributeConstraintViolationError,
        expected_http_status=422,
        expected_attributes={
            "node_kind": "TestPerson",
            "field_name": "name",
            "constraint": "regex",
            "detail": "^[A-Z]",
        },
    ),
    CodeCase(
        name="ATTRIBUTE_INVALID_TYPE",
        expected_class=AttributeInvalidTypeError,
        expected_http_status=422,
        expected_attributes={
            "node_kind": "TestPerson",
            "field_name": "height",
            "expected_type": "Integer",
            "received_type": "String",
        },
    ),
    CodeCase(
        name="ATTRIBUTE_REQUIRED",
        expected_class=AttributeRequiredError,
        expected_http_status=422,
        expected_attributes={"node_kind": "TestPerson", "field_name": "name"},
    ),
    CodeCase(
        name="AUTHENTICATION_REQUIRED",
        expected_class=GraphQLError,
        expected_http_status=401,
        expected_attributes={},
    ),
    CodeCase(
        name="BRANCH_ALREADY_MERGED",
        expected_class=BranchAlreadyMergedError,
        expected_http_status=400,
        expected_attributes={"branch_name": "feature-a"},
    ),
    CodeCase(
        name="BRANCH_NEEDS_REBASE",
        expected_class=BranchNeedsRebaseError,
        expected_http_status=400,
        expected_attributes={"branch_name": "feature-a"},
    ),
    CodeCase(
        name="BRANCH_NOT_FOUND",
        expected_class=BranchNotFoundError,
        expected_http_status=400,
        expected_attributes={"identifier": "does-not-exist"},
    ),
    CodeCase(
        name="MERGE_IN_PROGRESS",
        expected_class=MergeInProgressError,
        expected_http_status=423,
        expected_attributes={"branch_name": "main", "merging_branch": "feature-a"},
    ),
    CodeCase(
        name="MERGE_RECOVERY_REQUIRED",
        expected_class=MergeRecoveryRequiredError,
        expected_http_status=423,
        expected_attributes={"branch_name": "main", "merging_branch": "feature-a"},
    ),
    CodeCase(
        name="NODE_NOT_FOUND",
        expected_class=NodeNotFoundError,
        expected_http_status=404,
        expected_attributes={"node_type": "TestPerson", "identifier": "john"},
    ),
    CodeCase(
        name="PERMISSION_DENIED",
        expected_class=GraphQLError,
        expected_http_status=403,
        expected_attributes={},
    ),
    CodeCase(
        name="SCHEMA_NOT_FOUND",
        expected_class=SchemaNotFoundError,
        expected_http_status=422,
        expected_attributes={"identifier": "TestWidget"},
    ),
    CodeCase(
        name="TOKEN_EXPIRED",
        expected_class=GraphQLError,
        expected_http_status=401,
        expected_attributes={},
    ),
    CodeCase(
        name="UNDEFINED_ERROR",
        expected_class=UndefinedError,
        expected_http_status=500,
        expected_attributes={},
    ),
    CodeCase(
        name="UNIQUENESS_VIOLATION",
        expected_class=UniquenessViolationError,
        expected_http_status=422,
        expected_attributes={"node_kind": "TestPerson", "fields": ["name"]},
    ),
]


class TestEveryCatalogueCode:
    """One case per code, reading the raised class and its attributes and never a message."""

    def test_the_cases_cover_every_code_the_bindings_carry(self) -> None:
        """Exhaustive only if it is checked against the bindings rather than maintained by hand."""
        assert {case.name for case in CODE_CASES} == set(CODE_TO_DATA_MODEL)

    def test_the_codes_with_no_class_of_their_own_are_the_authentication_ones(self) -> None:
        """The one asymmetry in the hierarchy, and the reason the fallback follows the transport."""
        assert {case.name for case in CODE_CASES if case.expected_class is GraphQLError} == CODES_WITHOUT_A_CLASS

    @pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in CODE_CASES])
    def test_the_code_raises_its_class_with_its_payload_promoted(self, case: CodeCase) -> None:
        envelope = load_code_envelope(case.name)

        exc = graphql_error_from_response(errors=envelope["errors"], query="query { x }")

        assert type(exc) is case.expected_class
        assert exc.code == case.name
        assert exc.http_status == case.expected_http_status
        for attribute, value in case.expected_attributes.items():
            assert getattr(exc, attribute) == value

    @pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in CODE_CASES])
    def test_the_code_is_identifiable_without_reading_a_message(self, case: CodeCase) -> None:
        """A class of its own, or a code on the generic class: either way, no words are parsed."""
        envelope = load_code_envelope(case.name)

        exc = graphql_error_from_response(errors=envelope["errors"])

        assert isinstance(exc, GraphQLError)
        assert exc.code == case.name

    @pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in CODE_CASES])
    def test_the_raw_payload_stays_available_for_forwarding(self, case: CodeCase) -> None:
        envelope = load_code_envelope(case.name)

        exc = graphql_error_from_response(errors=envelope["errors"])

        assert exc.extensions is not None
        assert exc.extensions["data"] == envelope["errors"][0]["extensions"]["data"]


class TestTheAdoptedClasses:
    """The three classes that predate the catalogue, now reachable from a server-reported failure.

    They are the only catalogued classes that are also raised with no code behind them, so `code` is
    what tells the two apart - and their attributes keep the names they have always had.
    """

    def test_a_server_reported_node_not_found_populates_the_node_attributes(self) -> None:
        envelope = load_code_envelope("NODE_NOT_FOUND")

        exc = graphql_error_from_response(errors=envelope["errors"])

        assert isinstance(exc, NodeNotFoundError)
        assert exc.node_type == "TestPerson"
        assert exc.identifier == "john"
        assert exc.code == "NODE_NOT_FOUND"

    def test_a_server_reported_branch_not_found_populates_the_identifier(self) -> None:
        envelope = load_code_envelope("BRANCH_NOT_FOUND")

        exc = graphql_error_from_response(errors=envelope["errors"])

        assert isinstance(exc, BranchNotFoundError)
        assert exc.identifier == "does-not-exist"
        assert exc.code == "BRANCH_NOT_FOUND"

    def test_a_server_reported_schema_not_found_populates_the_identifier(self) -> None:
        envelope = load_code_envelope("SCHEMA_NOT_FOUND")

        exc = graphql_error_from_response(errors=envelope["errors"])

        assert isinstance(exc, SchemaNotFoundError)
        assert exc.identifier == "TestWidget"
        assert exc.code == "SCHEMA_NOT_FOUND"

    def test_a_client_side_raise_of_the_same_class_carries_no_code(self) -> None:
        """`exc.code is not None` is the test for which of the two a caller is holding."""
        assert NodeNotFoundError(identifier="john", node_type="TestPerson").code is None
        assert BranchNotFoundError(identifier="does-not-exist").code is None
        assert SchemaNotFoundError(identifier="TestWidget").code is None


class TestTheFirstErrorGoverns:
    def test_a_silent_first_error_governs_over_a_later_coded_one(self) -> None:
        """Otherwise a response's class would depend on which error the SDK happens to recognise."""
        errors = [
            {"message": "the failure that came first"},
            {
                "message": "and one the catalogue describes",
                "extensions": {
                    "code": "UNIQUENESS_VIOLATION",
                    "http_status": 422,
                    "data": {"node_kind": "TestPerson", "fields": ["name"]},
                },
            },
        ]

        exc = graphql_error_from_response(errors=errors, query="mutation { TestPersonCreate }")

        assert type(exc) is GraphQLError
        assert exc.code is None
        assert exc.http_status is None

    def test_the_complete_list_is_retained_unreordered(self) -> None:
        errors = [
            {"message": "the failure that came first"},
            {
                "message": "and one the catalogue describes",
                "extensions": {
                    "code": "UNIQUENESS_VIOLATION",
                    "http_status": 422,
                    "data": {"node_kind": "TestPerson", "fields": ["name"]},
                },
            },
        ]

        exc = graphql_error_from_response(errors=errors)

        assert [error["message"] for error in exc.errors] == [
            "the failure that came first",
            "and one the catalogue describes",
        ]


class TestTheFallbackFollowsTheObservedTransport:
    """Which generic class a code falls back to is decided by how the SDK saw it arrive.

    Following the status the catalogue declares instead would send the three authentication codes to
    `AuthenticationError` whenever a resolver raised them inside an HTTP 200, out of reach of the
    `except GraphQLError` clause that catches them today - and send a 401 carrying a data code to a
    class no caller of that path expects.
    """

    @pytest.mark.parametrize("code", sorted(CODES_WITHOUT_A_CLASS))
    def test_an_authentication_code_inside_a_graphql_response_raises_the_graphql_class(self, code: str) -> None:
        envelope = load_code_envelope(code)

        exc = graphql_error_from_response(errors=envelope["errors"])

        assert type(exc) is GraphQLError, "the declared 401 or 403 is metadata, not the transport"
        assert not isinstance(exc, AuthenticationError)
        assert exc.code == code

    def test_a_data_code_on_a_real_401_raises_the_authentication_class(self) -> None:
        response = auth_response(envelope=load_code_envelope("NODE_NOT_FOUND"))

        exc = authentication_error_from_response(response=response)

        assert type(exc) is AuthenticationError, "a class the caller of this path cannot expect is worse than none"
        assert exc.code == "NODE_NOT_FOUND"
        assert exc.http_status == 404, "the declared status is still readable, it just governs nothing"


class TestAuthenticationFactory:
    def test_reads_code_and_status_off_a_real_401(self) -> None:
        response = auth_response(envelope=load_envelope("auth_token_expired.json"))

        exc = authentication_error_from_response(response=response)

        assert isinstance(exc, AuthenticationError)
        assert exc.code == "TOKEN_EXPIRED"
        assert exc.http_status == 401

    def test_errors_is_a_sequence_of_dicts(self) -> None:
        response = auth_response(envelope=load_envelope("auth_token_expired.json"))

        exc = authentication_error_from_response(response=response)

        assert isinstance(exc.errors, list)
        assert all(isinstance(error, dict) for error in exc.errors)

    def test_only_the_governing_message_is_named_beside_the_code(self) -> None:
        response = auth_response(envelope=load_envelope("auth_two_messages.json"))

        exc = authentication_error_from_response(response=response)

        assert exc.message == "AUTHENTICATION_REQUIRED: first problem", (
            "joining the rest would file them under a code that is not theirs, the same rule the GraphQL path follows"
        )
        assert [error["message"] for error in exc.errors] == ["first problem", "second problem"], (
            "naming one message must not discard the rest, which stay on the exception"
        )

    def test_an_undescribed_code_keeps_the_joined_messages(self) -> None:
        """`UNDEFINED_ERROR` names nothing, so it must not displace the reasons the server gave."""
        response = auth_response(
            envelope={
                "errors": [
                    {"message": "first problem", "extensions": {"code": "UNDEFINED_ERROR"}},
                    {"message": "second problem"},
                ]
            }
        )

        exc = authentication_error_from_response(response=response)

        assert exc.message == "first problem | second problem"
        assert exc.code == "UNDEFINED_ERROR", "the code is still readable, it is just not the headline"

    def test_rest_integer_code_is_never_a_catalogue_code(self) -> None:
        response = auth_response(envelope=load_envelope("rest_legacy_401.json"))

        exc = authentication_error_from_response(response=response)

        assert exc.code is None
        assert exc.extensions == {"code": 401}

    def test_empty_error_list_falls_back_to_the_status(self) -> None:
        response = auth_response(envelope={"errors": []})

        exc = authentication_error_from_response(response=response)

        assert exc.message == "HTTP 401", "an empty join must not discard the status"

    def test_a_rest_detail_string_is_used_when_there_is_no_error_array(self) -> None:
        """The REST API rejects an unauthenticated request with a bare `detail` and no envelope."""
        response = auth_response(envelope={"detail": "Not authenticated"})

        exc = authentication_error_from_response(response=response)

        assert exc.message == "Not authenticated"
        assert exc.errors == []

    def test_a_server_message_wins_over_a_detail_string(self) -> None:
        response = auth_response(envelope={"detail": "Not authenticated", "errors": [{"message": "real reason"}]})

        exc = authentication_error_from_response(response=response)

        assert exc.message == "real reason"

    def test_an_object_body_carrying_nothing_readable_falls_back_to_the_status(self) -> None:
        response = auth_response(envelope={"unexpected": "shape"}, status_code=403)

        exc = authentication_error_from_response(response=response)

        assert exc.message == "HTTP 403"

    def test_a_403_is_parsed_the_same_way_as_a_401(self) -> None:
        response = auth_response(envelope=load_envelope("auth_two_messages.json"), status_code=403)

        exc = authentication_error_from_response(response=response)

        assert exc.message == "AUTHENTICATION_REQUIRED: first problem"

    def test_a_non_auth_status_falls_back_to_that_status(self) -> None:
        """A failed token refresh reaches this factory on whatever status the server sent."""
        response = auth_response(envelope="<html>502 Bad Gateway</html>", status_code=502)

        exc = authentication_error_from_response(response=response)

        assert exc.message == "HTTP 502"


class TestErrorsAlwaysASequenceOfDicts:
    """`ApiError.errors` is declared `Sequence[dict[str, Any]]`, so nothing else may reach it."""

    @pytest.mark.malformed
    def test_graphql_non_list_errors_becomes_an_empty_list(self) -> None:
        exc = graphql_error_from_response(errors="a bare string where an array belongs")

        assert exc.errors == []

    @pytest.mark.malformed
    def test_auth_non_list_errors_becomes_an_empty_list(self) -> None:
        response = auth_response(envelope={"errors": "a bare string where an array belongs"})

        exc = authentication_error_from_response(response=response)

        assert exc.errors == []

    @pytest.mark.malformed
    def test_auth_errors_as_an_object_becomes_an_empty_list(self) -> None:
        response = auth_response(envelope={"errors": {"message": "an object where an array belongs"}})

        exc = authentication_error_from_response(response=response)

        assert exc.errors == []

    @pytest.mark.malformed
    def test_non_dict_entries_are_dropped(self) -> None:
        exc = graphql_error_from_response(errors=[{"message": "real"}, "stray", None, 7])

        assert exc.errors == [{"message": "real"}]


class TestGuardsAgainstShapesThatLookRight:
    @pytest.mark.malformed
    def test_a_boolean_is_not_an_http_status(self) -> None:
        """`bool` is an `int` subclass, so a JSON `true` would otherwise pass the status check."""
        exc = graphql_error_from_response(errors=[{"extensions": {"code": "X", "http_status": True}}])

        assert exc.http_status is None

    @pytest.mark.malformed
    def test_extensions_that_are_not_an_object_yield_no_extensions(self) -> None:
        envelope = load_envelope("malformed_extensions_as_list.json")

        exc = graphql_error_from_response(errors=envelope["errors"])

        assert exc.extensions is None, "a list of extensions is not an extensions object"
        assert exc.code is None

    @pytest.mark.malformed
    def test_a_non_string_message_is_left_out_of_the_join(self) -> None:
        response = auth_response(envelope={"errors": [{"message": "real"}, {"message": None}, {"message": 7}]})

        exc = authentication_error_from_response(response=response)

        assert exc.message == "real"

    @pytest.mark.malformed
    def test_a_leading_non_dict_error_does_not_govern(self) -> None:
        exc = graphql_error_from_response(errors=["stray", {"extensions": {"code": "UNIQUENESS_VIOLATION"}}])

        assert exc.code is None, "the first entry governs even when it carries nothing readable"


@dataclass
class CrossVersionCase:
    name: str
    fixture: str
    expected_code: str | None
    expected_http_status: int | None = None
    expected_class: type[GraphQLError] = GraphQLError


CROSS_VERSION_CASES = [
    CrossVersionCase(
        name="unknown-code-from-a-newer-server",
        fixture="graphql_unknown_code.json",
        expected_code="SOMETHING_WE_HAVE_NEVER_HEARD_OF",
        expected_http_status=418,
    ),
    CrossVersionCase(
        name="known-code-with-an-extra-payload-field",
        fixture="graphql_extra_payload_field.json",
        expected_code="UNIQUENESS_VIOLATION",
        expected_http_status=422,
        expected_class=UniquenessViolationError,
    ),
    CrossVersionCase(
        name="error-carrying-no-extensions",
        fixture="graphql_no_extensions.json",
        expected_code=None,
    ),
    CrossVersionCase(
        name="pre-catalogue-integer-code",
        fixture="graphql_integer_code.json",
        expected_code=None,
    ),
]


@pytest.mark.crossversion
@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in CROSS_VERSION_CASES])
def test_a_cross_version_envelope_parses_without_raising(case: CrossVersionCase) -> None:
    """Any SDK version talks to any server version, and parsing never raises.

    A code these bindings have a class for still reaches it here: gaining a field it has never heard
    of changes nothing, which is the forward compatibility the payload models are for.
    """
    envelope = load_envelope(case.fixture)

    exc = graphql_error_from_response(errors=envelope["errors"], query="query { x }")

    assert type(exc) is case.expected_class
    assert exc.code == case.expected_code
    assert exc.http_status == case.expected_http_status


@pytest.mark.crossversion
def test_an_unknown_payload_field_is_passed_through_untouched() -> None:
    """Forward compatibility is only real if the payload we cannot interpret still reaches the caller."""
    envelope = load_envelope("graphql_extra_payload_field.json")

    exc = graphql_error_from_response(errors=envelope["errors"])

    assert exc.extensions is not None
    assert exc.extensions["data"]["introduced_in_a_later_version"] == "ignored"


@dataclass
class MalformedCase:
    name: str
    fixture: str


MALFORMED_CASES = [
    MalformedCase(name="errors-as-a-bare-string", fixture="malformed_errors_as_string.json"),
    MalformedCase(name="extensions-as-a-list", fixture="malformed_extensions_as_list.json"),
    MalformedCase(name="code-as-a-nested-object", fixture="malformed_code_as_object.json"),
]


@pytest.mark.malformed
@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in MALFORMED_CASES])
def test_malformed_envelope_degrades_to_the_generic_exception(case: MalformedCase) -> None:
    """A shape the parser does not recognise must not become an SDK TypeError."""
    envelope = load_envelope(case.fixture)

    exc = graphql_error_from_response(errors=envelope["errors"], query="query { x }")

    assert type(exc) is GraphQLError
    assert exc.code is None


@pytest.mark.malformed
def test_malformed_envelope_keeps_the_payload_in_the_message() -> None:
    """The server's failure must survive verbatim, not be replaced by the SDK's own."""
    envelope = load_envelope("malformed_errors_as_string.json")

    exc = graphql_error_from_response(errors=envelope["errors"], query="query { x }")

    assert exc.message == f"An error occurred while executing the GraphQL Query query {{ x }}, {envelope['errors']}"


@dataclass
class NonJsonBodyCase:
    name: str
    text: str


NON_JSON_BODY_CASES = [
    NonJsonBodyCase(name="html-proxy-page", text="<html><body>502 Bad Gateway</body></html>"),
    NonJsonBodyCase(name="empty-body", text=""),
]


@pytest.mark.malformed
@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in NON_JSON_BODY_CASES])
def test_authentication_factory_tolerates_a_non_json_body(case: NonJsonBodyCase) -> None:
    response = auth_response(envelope=case.text)

    exc = authentication_error_from_response(response=response)

    assert isinstance(exc, AuthenticationError)
    assert exc.message == "HTTP 401"
    assert exc.code is None
    assert exc.errors == []


class TestRaisedThroughTheClient:
    """The factories are only worth having if the envelope survives all the way to the caller."""

    @pytest.mark.parametrize("client_type", ["standard", "sync"])
    async def test_graphql_error_carries_the_envelope(
        self, client_type: str, clients: BothClients, httpx_mock: HTTPXMock
    ) -> None:
        envelope = load_envelope("graphql_uniqueness_violation.json")
        httpx_mock.add_response(method="POST", status_code=200, json={"data": None, "errors": envelope["errors"]})
        client = getattr(clients, client_type)
        query = "query { TestPerson { edges { node { name { value }}}}}"

        with pytest.raises(GraphQLError, match="already has name") as exc_info:
            if client_type == "standard":
                await client.execute_graphql(query=query)
            else:
                client.execute_graphql(query=query)

        assert exc_info.value.code == "UNIQUENESS_VIOLATION"
        assert exc_info.value.http_status == 422
        assert exc_info.value.query == query

    @pytest.mark.parametrize("client_type", ["standard", "sync"])
    async def test_authentication_error_carries_the_envelope(
        self, client_type: str, clients: BothClients, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(method="POST", status_code=403, json=load_envelope("auth_two_messages.json"))
        client = getattr(clients, client_type)

        with pytest.raises(AuthenticationError, match="AUTHENTICATION_REQUIRED: first problem") as exc_info:
            if client_type == "standard":
                await client.execute_graphql(query="query { TestPerson { edges { node { id }}}}")
            else:
                client.execute_graphql(query="query { TestPerson { edges { node { id }}}}")

        assert exc_info.value.code == "AUTHENTICATION_REQUIRED"
        assert exc_info.value.http_status == 401, (
            "http_status is the status the envelope declares, not the one the transport observed"
        )

    @pytest.mark.parametrize("client_type", ["standard", "sync"])
    @pytest.mark.parametrize("status_code", [401, 403])
    async def test_a_rejected_file_upload_carries_the_envelope(
        self, client_type: str, status_code: int, clients: BothClients, httpx_mock: HTTPXMock
    ) -> None:
        """The multipart path observes 401 and 403 too, so it owes the same exception as every other."""
        httpx_mock.add_response(
            method="POST",
            status_code=status_code,
            json={"errors": [{"message": "no upload rights", "extensions": {"code": "PERMISSION_DENIED"}}]},
        )
        client = getattr(clients, client_type)
        query = "mutation ($file: Upload!) { CoreFileUpload(data: {file: $file}) { ok }}"

        with pytest.raises(AuthenticationError, match="no upload rights") as exc_info:
            if client_type == "standard":
                await client._execute_graphql_with_file(query=query, file_content=BytesIO(b"x"), file_name="f.txt")
            else:
                client._execute_graphql_with_file(query=query, file_content=BytesIO(b"x"), file_name="f.txt")

        assert exc_info.value.code == "PERMISSION_DENIED"

    @pytest.mark.parametrize("client_type", ["standard", "sync"])
    async def test_a_file_upload_rejected_for_another_reason_still_raises_the_status_error(
        self, client_type: str, clients: BothClients, httpx_mock: HTTPXMock
    ) -> None:
        """Only 401 and 403 are converted; every other status keeps reaching the caller as it did."""
        httpx_mock.add_response(method="POST", status_code=500, json={"errors": [{"message": "boom"}]})
        client = getattr(clients, client_type)
        query = "mutation ($file: Upload!) { CoreFileUpload(data: {file: $file}) { ok }}"

        with pytest.raises(httpx.HTTPStatusError):
            if client_type == "standard":
                await client._execute_graphql_with_file(query=query, file_content=BytesIO(b"x"), file_name="f.txt")
            else:
                client._execute_graphql_with_file(query=query, file_content=BytesIO(b"x"), file_name="f.txt")

    @pytest.mark.parametrize("client_type", ["standard", "sync"])
    async def test_a_failed_token_refresh_surfaces_as_an_authentication_error(
        self, client_type: str, httpx_mock: HTTPXMock
    ) -> None:
        """A refresh that fails on any status other than 401 still reaches the caller as an auth failure."""
        httpx_mock.add_response(
            method="POST",
            url="http://mock/api/auth/refresh",
            status_code=503,
            json={"errors": [{"message": "the auth backend is down"}]},
        )
        config = Config(address="http://mock", username="admin", password="password", insert_tracker=True)
        client: InfrahubClient | InfrahubClientSync = (
            InfrahubClient(config=config) if client_type == "standard" else InfrahubClientSync(config=config)
        )
        client.refresh_token = "refresh-token"

        with pytest.raises(AuthenticationError, match="the auth backend is down") as exc_info:
            if isinstance(client, InfrahubClient):
                await client.login(refresh=True)
            else:
                client.login(refresh=True)

        assert exc_info.value.http_status is None, "the server sent no catalogue status on this path"


@pytest.mark.crossversion
def test_cross_version_fallback_is_logged_at_debug_level(caplog: pytest.LogCaptureFixture) -> None:
    """A fallback must be diagnosable in the field, not only in a test."""
    envelope = load_envelope("graphql_integer_code.json")

    with caplog.at_level("DEBUG", logger="infrahub_sdk"):
        graphql_error_from_response(errors=envelope["errors"])

    assert any("No catalogue code resolved" in record.getMessage() for record in caplog.records)


@pytest.mark.malformed
def test_unparseable_authentication_body_is_logged_at_debug_level(caplog: pytest.LogCaptureFixture) -> None:
    response = auth_response(envelope="<html>502</html>")

    with caplog.at_level("DEBUG", logger="infrahub_sdk"):
        authentication_error_from_response(response=response)

    assert any("could not be parsed" in record.getMessage() for record in caplog.records)
