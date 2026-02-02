"""Unit tests for MultipartBuilder class."""

from __future__ import annotations

from io import BytesIO

import ujson

from infrahub_sdk.graphql import MultipartBuilder


def test_build_operations_simple() -> None:
    """Test building operations with simple query and variables."""
    query = "mutation($file: Upload!) { upload(file: $file) { id } }"
    variables = {"other": "value"}

    result = MultipartBuilder.build_operations(query=query, variables=variables)

    parsed = ujson.loads(result)
    assert parsed["query"] == query
    assert parsed["variables"] == variables


def test_build_operations_empty_variables() -> None:
    """Test building operations with empty variables."""
    query = "mutation { doSomething { id } }"
    variables: dict[str, str] = {}

    result = MultipartBuilder.build_operations(query=query, variables=variables)

    parsed = ujson.loads(result)
    assert parsed["query"] == query
    assert parsed["variables"] == {}


def test_build_operations_complex_variables() -> None:
    """Test building operations with nested variables."""
    query = "mutation($input: CreateInput!) { create(input: $input) { id } }"
    variables = {"input": {"name": "test", "nested": {"value": 123}, "list": [1, 2, 3]}}

    result = MultipartBuilder.build_operations(query=query, variables=variables)

    parsed = ujson.loads(result)
    assert parsed["variables"]["input"]["name"] == "test"
    assert parsed["variables"]["input"]["nested"]["value"] == 123
    assert parsed["variables"]["input"]["list"] == [1, 2, 3]


def test_build_file_map_defaults() -> None:
    """Test building file map with default values."""
    result = MultipartBuilder.build_file_map()

    parsed = ujson.loads(result)
    assert parsed == {"0": ["variables.file"]}


def test_build_file_map_custom_key() -> None:
    """Test building file map with custom file key."""
    result = MultipartBuilder.build_file_map(file_key="1")

    parsed = ujson.loads(result)
    assert parsed == {"1": ["variables.file"]}


def test_build_file_map_custom_path() -> None:
    """Test building file map with custom variable path."""
    result = MultipartBuilder.build_file_map(variable_path="variables.input.document")

    parsed = ujson.loads(result)
    assert parsed == {"0": ["variables.input.document"]}


def test_build_file_map_both_custom() -> None:
    """Test building file map with both custom values."""
    result = MultipartBuilder.build_file_map(file_key="attachment", variable_path="variables.attachment")

    parsed = ujson.loads(result)
    assert parsed == {"attachment": ["variables.attachment"]}


def test_build_payload_with_file() -> None:
    """Test building complete payload with file content."""
    query = "mutation($file: Upload!) { upload(file: $file) { id } }"
    variables = {"other": "value"}
    file_content = BytesIO(b"test file content")
    file_name = "document.pdf"

    result = MultipartBuilder.build_payload(
        query=query, variables=variables, file_content=file_content, file_name=file_name
    )

    # Check operations
    assert "operations" in result
    assert result["operations"][0] is None  # No filename for operations
    operations_json = ujson.loads(result["operations"][1])
    assert operations_json["query"] == query
    assert operations_json["variables"]["other"] == "value"
    assert operations_json["variables"]["file"] is None  # File var should be null

    # Check map
    assert "map" in result
    assert result["map"][0] is None
    map_json = ujson.loads(result["map"][1])
    assert map_json == {"0": ["variables.file"]}

    # Check file
    assert "0" in result
    assert result["0"][0] == file_name
    assert result["0"][1] is file_content


def test_build_payload_without_file() -> None:
    """Test building payload without file content."""
    query = "mutation($file: Upload!) { upload(file: $file) { id } }"
    variables = {"other": "value"}

    result = MultipartBuilder.build_payload(query=query, variables=variables, file_content=None, file_name="unused.txt")

    # Should have operations and map
    assert "operations" in result
    assert "map" in result

    # Should NOT have file key
    assert "0" not in result


def test_build_payload_sets_file_var_to_null() -> None:
    """Test that build_payload sets file variable to null per spec."""
    query = "mutation($file: Upload!) { upload(file: $file) { id } }"
    variables = {"file": "should_be_overwritten", "other": "value"}
    file_content = BytesIO(b"content")

    result = MultipartBuilder.build_payload(
        query=query, variables=variables, file_content=file_content, file_name="test.txt"
    )

    operations_json = ujson.loads(result["operations"][1])
    assert operations_json["variables"]["file"] is None
    assert operations_json["variables"]["other"] == "value"


def test_build_payload_default_filename() -> None:
    """Test that default filename is used when not specified."""
    query = "mutation($file: Upload!) { upload(file: $file) { id } }"
    file_content = BytesIO(b"content")

    result = MultipartBuilder.build_payload(
        query=query,
        variables={},
        file_content=file_content,
    )

    assert result["0"][0] == "upload"


def test_build_payload_preserves_existing_variables() -> None:
    """Test that existing variables are preserved in the payload."""
    query = "mutation($file: Upload!, $nodeId: ID!) { upload(file: $file, node: $nodeId) { id } }"
    variables = {
        "nodeId": "node-123",
        "description": "A test file",
        "nested": {"key": "value"},
    }
    file_content = BytesIO(b"content")

    result = MultipartBuilder.build_payload(
        query=query,
        variables=variables,
        file_content=file_content,
        file_name="test.txt",
    )

    operations_json = ujson.loads(result["operations"][1])
    assert operations_json["variables"]["nodeId"] == "node-123"
    assert operations_json["variables"]["description"] == "A test file"
    assert operations_json["variables"]["nested"] == {"key": "value"}
    assert operations_json["variables"]["file"] is None  # file is null per spec
