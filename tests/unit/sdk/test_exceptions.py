"""The shape of the hierarchy, and what each `except` clause catches once it is a tree."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx
import pytest

from infrahub_sdk import exceptions
from infrahub_sdk.exceptions import (
    ApiError,
    AuthenticationError,
    BranchNotFoundError,
    Error,
    GraphQLError,
    NodeInvalidError,
    NodeNotFoundError,
    SchemaNotFoundError,
    authentication_error_from_response,
    graphql_error_from_response,
)
from tests.helpers.fixtures import read_fixture

FIXTURE_SUBDIR = "error_catalogue"


def load_envelope(name: str) -> dict[str, Any]:
    return json.loads(read_fixture(file_name=name, fixture_subdir=FIXTURE_SUBDIR))


def auth_response(envelope: dict[str, Any], status_code: int = 401) -> httpx.Response:
    """The httpx response the SDK would have observed for a rejected request."""
    request = httpx.Request("POST", "http://mock/graphql/main")
    return httpx.Response(status_code=status_code, json=envelope, request=request)


@dataclass
class NodeNotFoundData:
    """Stands in for the generated payload model, which the SDK does not carry yet."""

    node_kind: str
    identifier: str


@dataclass
class BranchNotFoundData:
    branch_name: str


@dataclass
class SchemaNotFoundData:
    kind: str


def exported_classes() -> list[type[BaseException]]:
    return [
        value
        for name, value in vars(exceptions).items()
        if not name.startswith("_") and isinstance(value, type) and issubclass(value, BaseException)
    ]


class TestHierarchyIsATree:
    def test_no_class_has_more_than_one_parent(self) -> None:
        """Single inheritance is what keeps `except` ordering predictable for every consumer."""
        multiply_inherited = sorted(cls.__name__ for cls in exported_classes() if len(cls.__bases__) > 1)

        assert multiply_inherited == []

    def test_graphql_and_authentication_are_siblings_under_api_error(self) -> None:
        assert GraphQLError.__bases__ == (ApiError,)
        assert AuthenticationError.__bases__ == (ApiError,)
        assert not issubclass(GraphQLError, AuthenticationError)
        assert not issubclass(AuthenticationError, GraphQLError)

    def test_api_error_is_an_infrahub_error(self) -> None:
        assert issubclass(ApiError, Error)

    def test_node_invalid_error_inherits_the_re_rooting(self) -> None:
        """`NodeInvalidError` is re-rooted through its parent rather than by its own declaration."""
        exc = NodeInvalidError(identifier={"name": ["john"]}, node_type="TestPerson")

        assert isinstance(exc, GraphQLError)
        assert isinstance(exc, NodeNotFoundError)

    @pytest.mark.parametrize("exception_class", [NodeNotFoundError, BranchNotFoundError, SchemaNotFoundError])
    def test_the_unified_classes_sit_under_graphql_error(self, exception_class: type[GraphQLError]) -> None:
        assert exception_class.__bases__ == (GraphQLError,)

    def test_one_clause_catches_both_transports(self) -> None:
        """`except ApiError` is the clause that spans a failure however the server reported it."""
        envelope = load_envelope("graphql_uniqueness_violation.json")
        graphql_failure = graphql_error_from_response(errors=envelope["errors"])
        auth_failure = authentication_error_from_response(
            response=auth_response(envelope=load_envelope("auth_token_expired.json"))
        )

        assert isinstance(graphql_failure, ApiError)
        assert isinstance(auth_failure, ApiError)


class TestCatchingAcrossTransports:
    def test_a_real_401_is_caught_as_an_authentication_error(self) -> None:
        response = auth_response(envelope=load_envelope("auth_token_expired.json"))
        exc = authentication_error_from_response(response=response)

        with pytest.raises(AuthenticationError, match="TOKEN_EXPIRED") as exc_info:
            raise exc

        assert exc_info.value.code == "TOKEN_EXPIRED"

    def test_the_same_code_inside_a_200_body_is_caught_as_a_graphql_error(self) -> None:
        """A resolver-raised auth failure arrives on the GraphQL path and keeps that class."""
        envelope = load_envelope("graphql_permission_denied.json")
        exc = graphql_error_from_response(errors=envelope["errors"], query="mutation { x }")

        with pytest.raises(GraphQLError, match="PERMISSION_DENIED") as exc_info:
            raise exc

        assert exc_info.value.code == "PERMISSION_DENIED"
        assert not isinstance(exc_info.value, AuthenticationError), (
            "the transport the SDK observed decides the class, never the code's declared status"
        )


class TestTheEnvelopeIsReadableOnAClientSideRaise:
    def test_envelope_attributes_exist_on_a_client_side_node_not_found(self) -> None:
        """Re-rooting is only safe if `except GraphQLError` can read the envelope unconditionally."""
        exc = NodeNotFoundError(identifier={"name": ["john"]}, node_type="TestPerson")

        assert exc.errors == []
        assert exc.query is None
        assert exc.variables is None
        assert exc.code is None, "no server reported this, so there is no catalogue code"

    def test_errors_is_a_list_rather_than_the_base_default(self) -> None:
        """The base's tuple is a can't-crash floor; a `GraphQLError` documents `errors` as a list."""
        exc = NodeNotFoundError(identifier="missing-file.py")

        assert isinstance(exc.errors, list)

    @pytest.mark.parametrize(
        "exc",
        [
            NodeNotFoundError(identifier={"name": ["john"]}),
            BranchNotFoundError(identifier="does-not-exist"),
            SchemaNotFoundError(identifier="TestPerson"),
        ],
        ids=["node", "branch", "schema"],
    )
    def test_every_unified_class_sets_its_envelope_through_the_constructor(self, exc: GraphQLError) -> None:
        assert exc.errors == []
        assert isinstance(exc.errors, list)


class TestTheBroadening:
    def test_except_graphql_error_now_catches_a_client_side_lookup_miss(self) -> None:
        # An accepted behaviour change, asserted rather than worked around so that reverting the
        # re-rooting fails here rather than silently narrowing what the clause catches.
        with pytest.raises(GraphQLError, match="Unable to find the node in the database"):
            raise NodeNotFoundError(identifier={"name": ["john"]}, node_type="TestPerson")

    def test_the_existing_clauses_still_catch_what_they_caught(self) -> None:
        with pytest.raises(NodeNotFoundError, match="Unable to find the node in the database"):
            raise NodeNotFoundError(identifier={"name": ["john"]})
        with pytest.raises(BranchNotFoundError, match="Unable to find the branch"):
            raise BranchNotFoundError(identifier="does-not-exist")
        with pytest.raises(SchemaNotFoundError, match="Unable to find the schema"):
            raise SchemaNotFoundError(identifier="TestPerson")


class TestAdoptionMarkers:
    """The adoption markers the generator reads.

    Infrahub derives its bindings by parsing `base.py`, so these strings are load-bearing outside
    this repository and have no reader inside it. Only a test keeps them honest.
    """

    @pytest.mark.parametrize(
        ("exception_class", "code"),
        [
            (NodeNotFoundError, "NODE_NOT_FOUND"),
            (BranchNotFoundError, "BRANCH_NOT_FOUND"),
            (SchemaNotFoundError, "SCHEMA_NOT_FOUND"),
        ],
        ids=["node", "branch", "schema"],
    )
    def test_the_adopted_code_is_declared(self, exception_class: type[GraphQLError], code: str) -> None:
        assert code == exception_class.CODE  # type: ignore[attr-defined]

    def test_declaring_a_code_does_not_make_it_a_raised_code(self) -> None:
        """`CODE` says which code the class represents; `code` says which one the server reported."""
        assert NodeNotFoundError(identifier="anything").code is None


class TestPromotingAServerPayload:
    def test_node_not_found_maps_node_kind_onto_node_type(self) -> None:
        exc = NodeNotFoundError.from_payload(payload=NodeNotFoundData(node_kind="TestPerson", identifier="john"))

        assert exc.node_type == "TestPerson"
        assert exc.identifier == "john"

    def test_branch_not_found_maps_branch_name_onto_identifier(self) -> None:
        exc = BranchNotFoundError.from_payload(payload=BranchNotFoundData(branch_name="does-not-exist"))

        assert exc.identifier == "does-not-exist"

    def test_schema_not_found_maps_kind_onto_identifier(self) -> None:
        exc = SchemaNotFoundError.from_payload(payload=SchemaNotFoundData(kind="TestPerson"))

        assert exc.identifier == "TestPerson"


@pytest.mark.message
class TestMessages:
    def test_a_catalogued_failure_names_the_code_and_the_server_message(self) -> None:
        envelope = load_envelope("graphql_uniqueness_violation.json")

        exc = graphql_error_from_response(errors=envelope["errors"], query="mutation { TestPersonCreate }")

        assert exc.message == "UNIQUENESS_VIOLATION: Node of kind TestPerson already has name 'John'"

    def test_a_catalogued_failure_carries_no_query_text(self) -> None:
        query = "mutation { TestPersonCreate(data: {name: {value: 'John'}}) { ok }}"
        envelope = load_envelope("graphql_uniqueness_violation.json")

        exc = graphql_error_from_response(errors=envelope["errors"], query=query)

        assert query not in str(exc)
        assert "An error occurred while executing the GraphQL Query" not in str(exc)

    def test_an_uncatalogued_failure_keeps_todays_message_byte_for_byte(self) -> None:
        errors = [{"message": "Source node not found: a"}]
        query = "query { InfrahubPathTraversal }"

        exc = graphql_error_from_response(errors=errors, query=query)

        assert exc.message == f"An error occurred while executing the GraphQL Query {query}, {errors}"

    def test_a_catalogued_authentication_failure_names_its_code(self) -> None:
        response = auth_response(envelope=load_envelope("auth_two_messages.json"))

        exc = authentication_error_from_response(response=response)

        assert exc.message == "AUTHENTICATION_REQUIRED: first problem | second problem"

    def test_an_uncatalogued_authentication_failure_keeps_the_joined_messages(self) -> None:
        response = auth_response(envelope={"errors": [{"message": "first problem"}, {"message": "second problem"}]})

        exc = authentication_error_from_response(response=response)

        assert exc.message == "first problem | second problem"

    @pytest.mark.parametrize(
        ("exc", "expected"),
        [
            (NodeNotFoundError(identifier={"name": ["john"]}), "Unable to find the node in the database."),
            (BranchNotFoundError(identifier="dev"), "Unable to find the branch 'dev' in the Database."),
            (SchemaNotFoundError(identifier="TestPerson"), "Unable to find the schema 'TestPerson'."),
        ],
        ids=["node", "branch", "schema"],
    )
    def test_a_unified_class_raised_with_no_code_behind_it_keeps_todays_message(
        self, exc: GraphQLError, expected: str
    ) -> None:
        """Re-rooting must not put the GraphQL default message on a client-side lookup miss."""
        assert exc.message == expected

    def test_only_the_governing_error_message_is_named_beside_the_code(self) -> None:
        """Joining the whole list would file every later error under a code that is not theirs."""
        envelope = load_envelope("graphql_multiple_errors.json")

        exc = graphql_error_from_response(errors=envelope["errors"])

        assert exc.message == "SCHEMA_NOT_FOUND: first failure"
        assert "second failure" not in str(exc)
        assert [error["message"] for error in exc.errors] == ["first failure", "second failure", "third failure"], (
            "naming one message must not discard the rest, which stay on the exception"
        )

    def test_the_query_and_variables_survive_a_catalogued_failure(self) -> None:
        """The query leaves the message but stays readable, which is the whole trade."""
        envelope = load_envelope("graphql_uniqueness_violation.json")
        query = "mutation { TestPersonCreate }"

        exc = graphql_error_from_response(errors=envelope["errors"], query=query, variables={"name": "John"})

        assert exc.query == query
        assert exc.variables == {"name": "John"}
