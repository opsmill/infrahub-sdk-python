from __future__ import annotations

from typing import Any

from infrahub_sdk.exceptions import GraphQLError, GraphQLErrorDetail


def test_graphql_error_parses_catalogue_extensions() -> None:
    error = GraphQLError(
        errors=[
            {
                "message": "Query is not valid: Cannot query field 'DemoMissingNode' on type 'Query'.",
                "path": ["CoreGraphQLQueryCreate"],
                "extensions": {"code": "GRAPHQL_QUERY_INVALID", "http_status": 422, "data": {}},
            }
        ],
        query="mutation { CoreGraphQLQueryCreate { ok } }",
        variables={"secret": "should-not-leak"},
    )

    assert error.details == [
        GraphQLErrorDetail(
            message="Query is not valid: Cannot query field 'DemoMissingNode' on type 'Query'.",
            code="GRAPHQL_QUERY_INVALID",
            http_status=422,
            data={},
            path=["CoreGraphQLQueryCreate"],
        )
    ]
    assert error.codes == ["GRAPHQL_QUERY_INVALID"]


def test_graphql_error_message_excludes_query_and_variables() -> None:
    error = GraphQLError(
        errors=[
            {"message": "first error"},
            {"message": "second error"},
        ],
        query="query Sensitive { secretField }",
        variables={"password": "should-not-leak"},
    )

    assert str(error) == "An error occurred while executing the GraphQL Query: first error; second error"
    assert "secretField" not in str(error)
    assert "should-not-leak" not in str(error)
    assert error.query == "query Sensitive { secretField }"
    assert error.variables == {"password": "should-not-leak"}


def test_graphql_error_without_extensions() -> None:
    error = GraphQLError(errors=[{"message": "plain error"}])

    assert error.details == [GraphQLErrorDetail(message="plain error")]
    assert error.codes == []
    assert str(error) == "An error occurred while executing the GraphQL Query: plain error"


def test_graphql_error_with_non_dict_entries() -> None:
    errors: list[Any] = ["a bare string error"]
    error = GraphQLError(errors=errors)

    assert error.details == [GraphQLErrorDetail(message="a bare string error")]
    assert str(error) == "An error occurred while executing the GraphQL Query: a bare string error"


def test_graphql_error_with_non_list_errors() -> None:
    error = GraphQLError(errors="a single scalar error")  # type: ignore[arg-type]

    assert error.details == [GraphQLErrorDetail(message="a single scalar error")]
    assert error.codes == []
    assert str(error) == "An error occurred while executing the GraphQL Query: a single scalar error"


def test_graphql_error_with_empty_errors() -> None:
    error = GraphQLError(errors=[])

    assert error.details == []
    assert error.codes == []
    assert str(error) == "An error occurred while executing the GraphQL Query"


def test_graphql_error_ignores_malformed_extensions() -> None:
    error = GraphQLError(
        errors=[
            {
                "message": "typed wrong",
                "extensions": {"code": 42, "http_status": "not-an-int", "data": ["not", "a", "dict"]},
            },
            {"message": "extensions not a dict", "extensions": "bogus"},
        ]
    )

    assert error.details == [
        GraphQLErrorDetail(message="typed wrong"),
        GraphQLErrorDetail(message="extensions not a dict"),
    ]
    assert error.codes == []
