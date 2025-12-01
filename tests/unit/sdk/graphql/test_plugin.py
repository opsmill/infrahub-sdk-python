import ast

import pytest
from ariadne_codegen.schema import (
    get_graphql_schema_from_path,
)
from ariadne_codegen.utils import ast_to_str
from graphql import GraphQLSchema

from infrahub_sdk.graphql.plugin import FutureAnnotationPlugin
from infrahub_sdk.utils import get_fixtures_dir


@pytest.fixture
def graphql_schema() -> GraphQLSchema:
    gql_schema = get_fixtures_dir() / "unit" / "test_graphql_plugin" / "schema.graphql"
    return get_graphql_schema_from_path(str(gql_schema))


@pytest.fixture
def python01_file() -> str:
    python01_file = get_fixtures_dir() / "unit" / "test_graphql_plugin" / "python01.py"
    return python01_file.read_text(encoding="UTF-8")


@pytest.fixture
def python02_file() -> str:
    python02_file = get_fixtures_dir() / "unit" / "test_graphql_plugin" / "python02.py"
    return python02_file.read_text(encoding="UTF-8")


@pytest.fixture
def python02_after_annotation_file() -> str:
    python02_file = get_fixtures_dir() / "unit" / "test_graphql_plugin" / "python02_after_annotation.py"
    return python02_file.read_text(encoding="UTF-8")


def test_future_annotation_plugin_already_present(graphql_schema: GraphQLSchema, python01_file: str) -> None:
    python01 = ast.parse(python01_file)
    python01_expected = ast.parse(python01_file)
    python01_expected_str = ast_to_str(python01_expected)

    plugin = FutureAnnotationPlugin(schema=graphql_schema, config_dict={})
    python01_after = plugin.generate_result_types_module(module=python01, operation_definition=None)

    python01_after_str = ast_to_str(python01_after)

    assert python01_after_str == python01_expected_str


def test_future_annotation_plugin_not_present(
    graphql_schema: GraphQLSchema, python02_file: str, python02_after_annotation_file: str
) -> None:
    python02 = ast.parse(python02_file)
    python02_expected = ast.parse(python02_after_annotation_file)
    python02_expected_str = ast_to_str(python02_expected)

    plugin = FutureAnnotationPlugin(schema=graphql_schema, config_dict={})
    python02_after = plugin.generate_result_types_module(module=python02, operation_definition=None)
    python02_after_str = ast_to_str(python02_after)

    assert python02_after_str == python02_expected_str
