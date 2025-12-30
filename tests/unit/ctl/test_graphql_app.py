from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from ariadne_codegen.schema import get_graphql_schema_from_path
from typer.testing import CliRunner

from infrahub_sdk.ctl.graphql import app, find_gql_files, get_graphql_query
from tests.helpers.cli import remove_ansi_color

runner = CliRunner()

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "unit" / "test_infrahubctl" / "graphql"


class TestFindGqlFiles:
    """Tests for find_gql_files helper function."""

    def test_find_gql_files_single_file(self, tmp_path: Path) -> None:
        """Test finding a single .gql file when path points to a file."""
        query_file = tmp_path / "query.gql"
        query_file.write_text("query Test { field }")

        result = find_gql_files(query_file)

        assert len(result) == 1
        assert result[0] == query_file

    def test_find_gql_files_directory(self, tmp_path: Path) -> None:
        """Test finding multiple .gql files in a directory."""
        (tmp_path / "query1.gql").write_text("query Test1 { field }")
        (tmp_path / "query2.gql").write_text("query Test2 { field }")
        (tmp_path / "not_a_query.txt").write_text("not a query")

        result = find_gql_files(tmp_path)

        assert len(result) == 2
        assert all(f.suffix == ".gql" for f in result)

    def test_find_gql_files_nested_directory(self, tmp_path: Path) -> None:
        """Test finding .gql files in nested directories."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (tmp_path / "query1.gql").write_text("query Test1 { field }")
        (subdir / "query2.gql").write_text("query Test2 { field }")

        result = find_gql_files(tmp_path)

        assert len(result) == 2

    def test_find_gql_files_nonexistent_path(self, tmp_path: Path) -> None:
        """Test that FileNotFoundError is raised for non-existent path."""
        nonexistent = tmp_path / "nonexistent"

        with pytest.raises(FileNotFoundError, match="File or directory not found"):
            find_gql_files(nonexistent)

    def test_find_gql_files_empty_directory(self, tmp_path: Path) -> None:
        """Test finding no .gql files in an empty directory."""
        result = find_gql_files(tmp_path)

        assert len(result) == 0


class TestGetGraphqlQuery:
    """Tests for get_graphql_query helper function."""

    def test_get_graphql_query_valid(self) -> None:
        """Test parsing a valid GraphQL query."""
        schema = get_graphql_schema_from_path(str(FIXTURES_DIR / "test_schema.graphql"))
        query_file = FIXTURES_DIR / "valid_query.gql"

        definitions = get_graphql_query(query_file, schema)

        assert len(definitions) == 1
        assert definitions[0].name.value == "GetTags"

    def test_get_graphql_query_invalid(self) -> None:
        """Test that invalid query raises ValueError."""
        schema = get_graphql_schema_from_path(str(FIXTURES_DIR / "test_schema.graphql"))
        query_file = FIXTURES_DIR / "invalid_query.gql"

        with pytest.raises(ValueError, match="Cannot query field"):
            get_graphql_query(query_file, schema)

    def test_get_graphql_query_nonexistent_file(self) -> None:
        """Test that FileNotFoundError is raised for non-existent file."""
        schema = get_graphql_schema_from_path(str(FIXTURES_DIR / "test_schema.graphql"))
        nonexistent = FIXTURES_DIR / "nonexistent.gql"

        with pytest.raises(FileNotFoundError, match="File not found"):
            get_graphql_query(nonexistent, schema)

    def test_get_graphql_query_directory_instead_of_file(self) -> None:
        """Test that ValueError is raised when path is a directory."""
        schema = get_graphql_schema_from_path(str(FIXTURES_DIR / "test_schema.graphql"))

        with pytest.raises(ValueError, match="is not a file"):
            get_graphql_query(FIXTURES_DIR, schema)


class TestGenerateReturnTypesCommand:
    """Tests for the generate-return-types CLI command."""

    def test_generate_return_types_success(self, tmp_path: Path) -> None:
        """Test successful generation of return types from a valid query."""
        # Copy fixtures to temp directory
        schema_file = tmp_path / "schema.graphql"
        query_file = tmp_path / "query.gql"

        shutil.copy(FIXTURES_DIR / "test_schema.graphql", schema_file)
        shutil.copy(FIXTURES_DIR / "valid_query.gql", query_file)

        # Run the command
        result = runner.invoke(
            app, ["generate-return-types", str(query_file), "--schema", str(schema_file)], catch_exceptions=False
        )

        assert result.exit_code == 0
        clean_output = remove_ansi_color(result.stdout)
        assert "Generated" in clean_output

        # Check that a file was generated
        generated_files = list(tmp_path.glob("*.py"))
        assert len(generated_files) >= 1

    def test_generate_return_types_directory(self, tmp_path: Path) -> None:
        """Test generation when providing a directory of queries."""
        # Copy fixtures to temp directory
        schema_file = tmp_path / "schema.graphql"
        query_dir = tmp_path / "queries"
        query_dir.mkdir()

        shutil.copy(FIXTURES_DIR / "test_schema.graphql", schema_file)
        shutil.copy(FIXTURES_DIR / "valid_query.gql", query_dir / "query.gql")

        # Run the command with directory
        result = runner.invoke(
            app, ["generate-return-types", str(query_dir), "--schema", str(schema_file)], catch_exceptions=False
        )

        assert result.exit_code == 0
        clean_output = remove_ansi_color(result.stdout)
        assert "Generated" in clean_output

    def test_generate_return_types_missing_schema(self, tmp_path: Path) -> None:
        """Test error when schema file is missing."""
        query_file = tmp_path / "query.gql"
        shutil.copy(FIXTURES_DIR / "valid_query.gql", query_file)

        result = runner.invoke(app, ["generate-return-types", str(query_file), "--schema", "nonexistent.graphql"])

        assert result.exit_code == 1
        clean_output = remove_ansi_color(result.stdout)
        assert "not found" in clean_output.lower()

    def test_generate_return_types_invalid_query(self, tmp_path: Path) -> None:
        """Test handling of invalid query (should print error and continue)."""
        schema_file = tmp_path / "schema.graphql"
        query_file = tmp_path / "query.gql"

        shutil.copy(FIXTURES_DIR / "test_schema.graphql", schema_file)
        shutil.copy(FIXTURES_DIR / "invalid_query.gql", query_file)

        result = runner.invoke(app, ["generate-return-types", str(query_file), "--schema", str(schema_file)])

        # Should exit successfully but print error message for invalid query
        assert result.exit_code == 0
        clean_output = remove_ansi_color(result.stdout)
        assert "Error" in clean_output

    def test_generate_return_types_with_typename(self, tmp_path: Path) -> None:
        """Test that __typename fields are properly stripped during generation."""
        schema_file = tmp_path / "schema.graphql"
        query_file = tmp_path / "query.gql"

        shutil.copy(FIXTURES_DIR / "test_schema.graphql", schema_file)
        shutil.copy(FIXTURES_DIR / "query_with_typename.gql", query_file)

        result = runner.invoke(
            app, ["generate-return-types", str(query_file), "--schema", str(schema_file)], catch_exceptions=False
        )

        assert result.exit_code == 0
        clean_output = remove_ansi_color(result.stdout)
        assert "Generated" in clean_output

    def test_generate_return_types_default_cwd(self, tmp_path: Path) -> None:
        """Test that command defaults to current directory when no query path provided."""
        # Copy fixtures to temp directory
        schema_file = tmp_path / "schema.graphql"
        query_file = tmp_path / "query.gql"

        shutil.copy(FIXTURES_DIR / "test_schema.graphql", schema_file)
        shutil.copy(FIXTURES_DIR / "valid_query.gql", query_file)

        # Change to temp directory and run without specifying query path
        original_dir = Path.cwd()
        try:
            os.chdir(tmp_path)
            result = runner.invoke(app, ["generate-return-types", "--schema", str(schema_file)], catch_exceptions=False)
        finally:
            os.chdir(original_dir)

        assert result.exit_code == 0
        clean_output = remove_ansi_color(result.stdout)
        assert "Generated" in clean_output

    def test_generate_return_types_no_gql_files(self, tmp_path: Path) -> None:
        """Test when directory has no .gql files."""
        schema_file = tmp_path / "schema.graphql"
        shutil.copy(FIXTURES_DIR / "test_schema.graphql", schema_file)

        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        result = runner.invoke(app, ["generate-return-types", str(empty_dir), "--schema", str(schema_file)])

        # Should exit successfully with no output
        assert result.exit_code == 0

    def test_generate_return_types_multiple_queries_same_dir(self, tmp_path: Path) -> None:
        """Test generation with multiple query files in the same directory."""
        schema_file = tmp_path / "schema.graphql"
        shutil.copy(FIXTURES_DIR / "test_schema.graphql", schema_file)

        # Create multiple valid queries
        query1 = tmp_path / "query1.gql"
        query2 = tmp_path / "query2.gql"

        query1.write_text("""
query GetAllTags {
  BuiltinTag {
    edges {
      node {
        id
        name { value }
      }
    }
  }
}
""")
        query2.write_text("""
query GetTagByName($name: String!) {
  BuiltinTag(name__value: $name) {
    edges {
      node {
        id
        description { value }
      }
    }
  }
}
""")

        result = runner.invoke(
            app, ["generate-return-types", str(tmp_path), "--schema", str(schema_file)], catch_exceptions=False
        )

        assert result.exit_code == 0
        clean_output = remove_ansi_color(result.stdout)
        # Should generate files for both queries
        assert clean_output.count("Generated") >= 2
