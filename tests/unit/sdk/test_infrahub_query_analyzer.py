import pytest

from infrahub_sdk.query_analyzer import GraphQLQueryReport, InfrahubQueryAnalyzer
from infrahub_sdk.schema import BranchSchema, NodeSchema, NodeSchemaAPI


@pytest.fixture
def tag_schema_with_uniqueness() -> NodeSchemaAPI:
    """Tag schema with uniqueness constraints on name__value (matching GraphQL filter format)."""
    data = {
        "name": "Tag",
        "namespace": "Builtin",
        "default_filter": "name__value",
        # The uniqueness_constraints must match the GraphQL argument name format
        "uniqueness_constraints": [["name__value"]],
        "attributes": [
            {"name": "name", "kind": "Text", "unique": True},
            {"name": "description", "kind": "Text", "optional": True},
        ],
    }
    return NodeSchema(**data).convert_api()


@pytest.fixture
def branch_schema_with_tag(tag_schema_with_uniqueness: NodeSchemaAPI) -> BranchSchema:
    """A BranchSchema containing only the BuiltinTag schema."""
    return BranchSchema(hash="test", nodes={"BuiltinTag": tag_schema_with_uniqueness})


class TestGraphQLQueryReportOnlyHasUniqueTargets:
    """Tests for GraphQLQueryReport.only_has_unique_targets property."""

    def test_empty_queries_returns_false(self) -> None:
        """When there are no queries, only_has_unique_targets should return False."""
        report = GraphQLQueryReport(queries=[])
        assert report.only_has_unique_targets is False

    def test_query_without_filter_returns_false(self, branch_schema_with_tag: BranchSchema) -> None:
        """A query without any filter should return False (multi-target)."""
        query = """
        query BuiltinTag {
            BuiltinTag {
                edges { node { id } }
            }
        }
        """
        analyzer = InfrahubQueryAnalyzer(
            query=query,
            schema_branch=branch_schema_with_tag,
        )
        report = analyzer.query_report

        assert report.top_level_kinds == ["BuiltinTag"]
        assert report.only_has_unique_targets is False

    def test_query_with_required_unique_filter_returns_true(self, branch_schema_with_tag: BranchSchema) -> None:
        """A query with a required filter on a unique field should return True."""
        query = """
        query BuiltinTag($name: String!) {
            BuiltinTag(name__value: $name) {
                edges { node { id } }
            }
        }
        """
        analyzer = InfrahubQueryAnalyzer(
            query=query,
            schema_branch=branch_schema_with_tag,
        )
        report = analyzer.query_report

        assert report.top_level_kinds == ["BuiltinTag"]
        assert report.only_has_unique_targets is True

    def test_query_with_optional_unique_filter_returns_false(self, branch_schema_with_tag: BranchSchema) -> None:
        """A query with an optional filter should return False (variable might not be provided)."""
        query = """
        query BuiltinTag($name: String) {
            BuiltinTag(name__value: $name) {
                edges { node { id } }
            }
        }
        """
        analyzer = InfrahubQueryAnalyzer(
            query=query,
            schema_branch=branch_schema_with_tag,
        )
        report = analyzer.query_report

        assert report.top_level_kinds == ["BuiltinTag"]
        assert report.only_has_unique_targets is False

    def test_query_with_static_unique_filter_returns_true(self, branch_schema_with_tag: BranchSchema) -> None:
        """A query with a static (non-variable) filter on unique field should return True."""
        query = """
        query {
            BuiltinTag(name__value: "my-tag") {
                edges { node { id } }
            }
        }
        """
        analyzer = InfrahubQueryAnalyzer(
            query=query,
            schema_branch=branch_schema_with_tag,
        )
        report = analyzer.query_report

        assert report.top_level_kinds == ["BuiltinTag"]
        assert report.only_has_unique_targets is True

    def test_query_with_required_ids_filter_returns_true(self, branch_schema_with_tag: BranchSchema) -> None:
        """A query filtering by ids with a required variable should return True."""
        query = """
        query BuiltinTag($ids: [ID]!) {
            BuiltinTag(ids: $ids) {
                edges { node { id } }
            }
        }
        """
        analyzer = InfrahubQueryAnalyzer(
            query=query,
            schema_branch=branch_schema_with_tag,
        )
        report = analyzer.query_report

        assert report.top_level_kinds == ["BuiltinTag"]
        assert report.only_has_unique_targets is True


class TestGraphQLQueryReportTopLevelKinds:
    """Tests for GraphQLQueryReport.top_level_kinds property."""

    def test_empty_queries_returns_empty_list(self) -> None:
        """When there are no queries, top_level_kinds should return empty list."""
        report = GraphQLQueryReport(queries=[])
        assert report.top_level_kinds == []

    def test_single_query_returns_kind(self, branch_schema_with_tag: BranchSchema) -> None:
        """A single query should return its kind in top_level_kinds."""
        query = """
        query {
            BuiltinTag {
                edges { node { id } }
            }
        }
        """
        analyzer = InfrahubQueryAnalyzer(
            query=query,
            schema_branch=branch_schema_with_tag,
        )
        report = analyzer.query_report

        assert report.top_level_kinds == ["BuiltinTag"]

    def test_unknown_kind_not_in_top_level_kinds(self) -> None:
        """A query for an unknown kind should not appear in top_level_kinds."""
        query = """
        query {
            UnknownKind {
                edges { node { id } }
            }
        }
        """
        branch_schema = BranchSchema(hash="test", nodes={})
        analyzer = InfrahubQueryAnalyzer(
            query=query,
            schema_branch=branch_schema,
        )
        report = analyzer.query_report

        assert report.top_level_kinds == []
