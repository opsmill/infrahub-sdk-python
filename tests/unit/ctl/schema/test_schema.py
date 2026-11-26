"""Unit tests for the ``infrahub schema`` end-user CLI subcommand group."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from typer.testing import CliRunner

from infrahub_sdk.ctl.cli_commands import app
from infrahub_sdk.schema import SCHEMA_EXPORT_MIN_INFRAHUB_VERSION, NodeSchemaAPI
from tests.helpers.cli import remove_ansi_color

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_httpx import HTTPXMock

runner = CliRunner()


def _make_node_schema(kind: str, namespace: str, name: str, description: str = "") -> MagicMock:
    """Build a MagicMock that satisfies ``isinstance(obj, NodeSchemaAPI)`` checks.

    Args:
        kind: Full kind string, e.g. ``"InfraDevice"``.
        namespace: Namespace portion, e.g. ``"Infra"``.
        name: Name portion, e.g. ``"Device"``.
        description: Optional human-readable description.

    Returns:
        A MagicMock with spec=NodeSchemaAPI and the given property values.

    """
    schema = MagicMock(spec=NodeSchemaAPI)
    schema.kind = kind
    schema.namespace = namespace
    schema.name = name
    schema.description = description
    return schema


def _make_attr(
    name: str,
    kind: str = "Text",
    optional: bool = True,
    default_value: object = None,
    description: str = "",
) -> MagicMock:
    """Build a mock attribute object for use in schema_show tests.

    Args:
        name: Attribute name.
        kind: Attribute type/kind string.
        optional: Whether the attribute is optional.
        default_value: Default value for the attribute.
        description: Optional description.

    Returns:
        A plain MagicMock with the given property values.

    """
    attr = MagicMock()
    attr.name = name
    attr.kind = kind
    attr.optional = optional
    attr.default_value = default_value
    attr.description = description
    return attr


def _make_rel(name: str, peer: str, cardinality: str = "one", optional: bool = True) -> MagicMock:
    """Build a mock relationship object for use in schema_show tests.

    Args:
        name: Relationship name.
        peer: Peer kind string.
        cardinality: ``"one"`` or ``"many"``.
        optional: Whether the relationship is optional.

    Returns:
        A plain MagicMock with the given property values.

    """
    rel = MagicMock()
    rel.name = name
    rel.peer = peer
    rel.cardinality = cardinality
    rel.optional = optional
    return rel


# ---------------------------------------------------------------------------
# Help tests
# ---------------------------------------------------------------------------


def test_schema_list_help() -> None:
    """``schema list --help`` exits cleanly and includes usage text."""
    result = runner.invoke(app, ["schema", "list", "--help"])
    assert result.exit_code == 0
    assert "Usage" in result.stdout


def test_schema_show_help() -> None:
    """``schema show --help`` exits cleanly and includes usage text."""
    result = runner.invoke(app, ["schema", "show", "--help"])
    assert result.exit_code == 0
    assert "kind" in result.stdout.lower() or "Usage" in result.stdout


# ---------------------------------------------------------------------------
# schema list tests
# ---------------------------------------------------------------------------


def test_schema_list_returns_table() -> None:
    """``schema list`` renders a table containing the returned kind names."""
    device_schema = _make_node_schema("InfraDevice", "Infra", "Device", "A network device")
    interface_schema = _make_node_schema("InfraInterface", "Infra", "Interface", "A network interface")

    mock_client = MagicMock()
    mock_client.schema.all = AsyncMock(return_value={"InfraDevice": device_schema, "InfraInterface": interface_schema})

    with patch("infrahub_sdk.ctl.schema.initialize_client", return_value=mock_client):
        result = runner.invoke(app, ["schema", "list"])

    assert result.exit_code == 0, result.stdout
    assert "InfraDevice" in result.stdout
    assert "InfraInterface" in result.stdout
    mock_client.schema.all.assert_awaited_once_with(branch=None)


def test_schema_list_with_filter() -> None:
    """``schema list --filter`` restricts output to kinds matching the substring."""
    device_schema = _make_node_schema("InfraDevice", "Infra", "Device")
    prefix_schema = _make_node_schema("IpamPrefix", "Ipam", "Prefix")

    mock_client = MagicMock()
    mock_client.schema.all = AsyncMock(return_value={"InfraDevice": device_schema, "IpamPrefix": prefix_schema})

    with patch("infrahub_sdk.ctl.schema.initialize_client", return_value=mock_client):
        result = runner.invoke(app, ["schema", "list", "--filter", "infra"])

    assert result.exit_code == 0, result.stdout
    assert "InfraDevice" in result.stdout
    assert "IpamPrefix" not in result.stdout


def test_schema_list_empty() -> None:
    """``schema list`` exits cleanly when no schemas are returned."""
    mock_client = MagicMock()
    mock_client.schema.all = AsyncMock(return_value={})

    with patch("infrahub_sdk.ctl.schema.initialize_client", return_value=mock_client):
        result = runner.invoke(app, ["schema", "list"])

    assert result.exit_code == 0, result.stdout


def test_schema_list_with_branch() -> None:
    """``schema list --branch`` passes the branch name through to the client."""
    schema = _make_node_schema("CoreAccount", "Core", "Account")

    mock_client = MagicMock()
    mock_client.schema.all = AsyncMock(return_value={"CoreAccount": schema})

    with patch("infrahub_sdk.ctl.schema.initialize_client", return_value=mock_client):
        result = runner.invoke(app, ["schema", "list", "--branch", "feature-x"])

    assert result.exit_code == 0, result.stdout
    mock_client.schema.all.assert_awaited_once_with(branch="feature-x")


def test_schema_list_skips_non_node_schema_entries() -> None:
    """``schema list`` silently skips entries that are not NodeSchemaAPI instances."""
    node_schema = _make_node_schema("InfraDevice", "Infra", "Device")
    # A plain MagicMock without spec=NodeSchemaAPI will fail isinstance(x, NodeSchemaAPI)
    generic_schema = MagicMock()
    generic_schema.kind = "SomeGenericKind"

    mock_client = MagicMock()
    mock_client.schema.all = AsyncMock(return_value={"InfraDevice": node_schema, "SomeGenericKind": generic_schema})

    with patch("infrahub_sdk.ctl.schema.initialize_client", return_value=mock_client):
        result = runner.invoke(app, ["schema", "list"])

    assert result.exit_code == 0, result.stdout
    assert "InfraDevice" in result.stdout
    assert "SomeGenericKind" not in result.stdout


# ---------------------------------------------------------------------------
# schema show tests
# ---------------------------------------------------------------------------


def _make_full_schema(
    kind: str = "InfraDevice",
    namespace: str = "Infra",
    description: str = "A network device",
    display_labels: list[str] | None = None,
    human_friendly_id: list[str] | None = None,
    attributes: list[MagicMock] | None = None,
    relationships: list[MagicMock] | None = None,
) -> MagicMock:
    """Build a detailed schema mock suitable for schema_show.

    Args:
        kind: Full kind string.
        namespace: Namespace portion.
        description: Human-readable description.
        display_labels: List of display label expressions.
        human_friendly_id: List of human-friendly ID expressions.
        attributes: List of attribute mocks.
        relationships: List of relationship mocks.

    Returns:
        A MagicMock configured with all schema_show-required fields.

    """
    schema = MagicMock()
    schema.kind = kind
    schema.namespace = namespace
    schema.description = description
    schema.display_labels = display_labels
    schema.human_friendly_id = human_friendly_id
    schema.attributes = attributes or []
    schema.relationships = relationships or []
    return schema


def test_schema_show_displays_metadata() -> None:
    """``schema show`` prints kind, description and namespace."""
    schema = _make_full_schema()
    mock_client = MagicMock()
    mock_client.schema.get = AsyncMock(return_value=schema)

    with patch("infrahub_sdk.ctl.schema.initialize_client", return_value=mock_client):
        result = runner.invoke(app, ["schema", "show", "InfraDevice"])

    assert result.exit_code == 0, result.stdout
    assert "InfraDevice" in result.stdout
    assert "A network device" in result.stdout
    assert "Infra" in result.stdout
    mock_client.schema.get.assert_awaited_once_with(kind="InfraDevice", branch=None)


def test_schema_show_displays_attributes() -> None:
    """``schema show`` renders the Attributes table with all column values."""
    attrs = [
        _make_attr("hostname", kind="Text", optional=False, default_value=None, description="Device hostname"),
        _make_attr("role", kind="Text", optional=True, default_value="router", description="Device role"),
    ]
    schema = _make_full_schema(attributes=attrs)
    mock_client = MagicMock()
    mock_client.schema.get = AsyncMock(return_value=schema)

    with patch("infrahub_sdk.ctl.schema.initialize_client", return_value=mock_client):
        result = runner.invoke(app, ["schema", "show", "InfraDevice"])

    assert result.exit_code == 0, result.stdout
    assert "Attributes" in result.stdout
    assert "hostname" in result.stdout
    assert "role" in result.stdout
    # Required attribute should show "Yes", optional should show "No"
    assert "Yes" in result.stdout
    assert "No" in result.stdout
    assert "router" in result.stdout
    assert "Device hostname" in result.stdout


def test_schema_show_displays_relationships() -> None:
    """``schema show`` renders the Relationships table with peer and cardinality."""
    rels = [
        _make_rel("interfaces", peer="InfraInterface", cardinality="many", optional=True),
        _make_rel("site", peer="LocationSite", cardinality="one", optional=False),
    ]
    schema = _make_full_schema(relationships=rels)
    mock_client = MagicMock()
    mock_client.schema.get = AsyncMock(return_value=schema)

    with patch("infrahub_sdk.ctl.schema.initialize_client", return_value=mock_client):
        result = runner.invoke(app, ["schema", "show", "InfraDevice"])

    assert result.exit_code == 0, result.stdout
    assert "Relationships" in result.stdout
    assert "interfaces" in result.stdout
    assert "InfraInterface" in result.stdout
    assert "many" in result.stdout
    assert "site" in result.stdout
    assert "LocationSite" in result.stdout
    assert "one" in result.stdout


def test_schema_show_no_attributes_or_relationships() -> None:
    """``schema show`` exits cleanly for a schema with no attributes or relationships."""
    schema = _make_full_schema(attributes=[], relationships=[])
    mock_client = MagicMock()
    mock_client.schema.get = AsyncMock(return_value=schema)

    with patch("infrahub_sdk.ctl.schema.initialize_client", return_value=mock_client):
        result = runner.invoke(app, ["schema", "show", "InfraDevice"])

    assert result.exit_code == 0, result.stdout
    assert "Attributes" not in result.stdout
    assert "Relationships" not in result.stdout


def test_schema_show_with_branch() -> None:
    """``schema show --branch`` passes the branch name through to the client."""
    schema = _make_full_schema()
    mock_client = MagicMock()
    mock_client.schema.get = AsyncMock(return_value=schema)

    with patch("infrahub_sdk.ctl.schema.initialize_client", return_value=mock_client):
        result = runner.invoke(app, ["schema", "show", "InfraDevice", "--branch", "feature-x"])

    assert result.exit_code == 0, result.stdout
    mock_client.schema.get.assert_awaited_once_with(kind="InfraDevice", branch="feature-x")


def test_schema_show_attribute_with_default_value() -> None:
    """``schema show`` displays the default value when set on an attribute."""
    attrs = [_make_attr("speed", kind="Number", optional=True, default_value=1000)]
    schema = _make_full_schema(attributes=attrs)
    mock_client = MagicMock()
    mock_client.schema.get = AsyncMock(return_value=schema)

    with patch("infrahub_sdk.ctl.schema.initialize_client", return_value=mock_client):
        result = runner.invoke(app, ["schema", "show", "InfraDevice"])

    assert result.exit_code == 0, result.stdout
    assert "1000" in result.stdout


# ---------------------------------------------------------------------------
# schema export tests
# ---------------------------------------------------------------------------

EXPORT_URL = "http://mock/api/schema/export?branch=main&mode=BRIEF"

EXPORT_RESPONSE: dict[str, Any] = {
    "version": "1.0",
    "infrahub_version": "1.13.0",
    "generics": [
        {
            "name": "Interface",
            "namespace": "Network",
            "attributes": [{"name": "name", "kind": "Text"}],
        },
    ],
    "nodes": [
        {
            "name": "Device",
            "namespace": "Network",
            "inherit_from": [],
            "attributes": [{"name": "name", "kind": "Text", "unique": True}],
            "relationships": [{"name": "site", "peer": "LocationSite", "cardinality": "one", "optional": False}],
        },
        {"name": "Site", "namespace": "Location", "attributes": [{"name": "name", "kind": "Text"}]},
    ],
}


def _read_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_schema_export_writes_one_file_per_namespace(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(method="GET", url=EXPORT_URL, json=EXPORT_RESPONSE)

    result = runner.invoke(app, ["schema", "export", "--directory", str(tmp_path)])

    assert result.exit_code == 0, result.stdout
    assert sorted(path.name for path in tmp_path.iterdir()) == ["location.yml", "network.yml"]

    network = _read_yaml(tmp_path / "network.yml")
    assert list(network) == ["version", "infrahub_version", "generics", "nodes"]
    assert network == {
        "version": "1.0",
        "infrahub_version": "1.13.0",
        "generics": EXPORT_RESPONSE["generics"],
        "nodes": [EXPORT_RESPONSE["nodes"][0]],
    }
    assert _read_yaml(tmp_path / "location.yml") == {
        "version": "1.0",
        "infrahub_version": "1.13.0",
        "nodes": [EXPORT_RESPONSE["nodes"][1]],
    }


def test_schema_export_single_file_writes_the_endpoint_document(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(method="GET", url=EXPORT_URL, json=EXPORT_RESPONSE)

    result = runner.invoke(app, ["schema", "export", "--directory", str(tmp_path), "--single-file"])

    assert result.exit_code == 0, result.stdout
    assert [path.name for path in tmp_path.iterdir()] == ["schema.yml"]
    schema = _read_yaml(tmp_path / "schema.yml")
    assert list(schema) == ["version", "infrahub_version", "generics", "nodes"]
    assert schema == EXPORT_RESPONSE


def test_schema_export_writes_no_default_for_a_field_the_response_left_out(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    httpx_mock.add_response(method="GET", url=EXPORT_URL, json=EXPORT_RESPONSE)

    result = runner.invoke(app, ["schema", "export", "--directory", str(tmp_path), "--single-file"])

    assert result.exit_code == 0, result.stdout
    site = _read_yaml(tmp_path / "schema.yml")["nodes"][1]
    # These fields have defaults in the schema model, so they would appear if the CLI wrote every field.
    for field in ("label", "branch", "state", "generate_profile", "relationships", "inherit_from"):
        assert field not in site
    assert site["attributes"] == [{"name": "name", "kind": "Text"}]


def test_schema_export_sends_mode_and_namespaces(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(
        method="GET",
        url="http://mock/api/schema/export?branch=main&namespaces=Network&namespaces=Location&mode=FULL",
        json=EXPORT_RESPONSE,
    )

    result = runner.invoke(
        app,
        [
            "schema",
            "export",
            "--directory",
            str(tmp_path),
            "--mode",
            "FULL",
            "--namespaces",
            "Network",
            "--namespaces",
            "Location",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert len(httpx_mock.get_requests()) == 1


def test_schema_export_empty_document(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(
        method="GET",
        url=EXPORT_URL,
        json={"version": "1.0", "infrahub_version": "1.13.0", "generics": [], "nodes": []},
    )
    directory = tmp_path / "export"

    result = runner.invoke(app, ["schema", "export", "--directory", str(directory)])

    assert result.exit_code == 0, result.stdout
    assert "No user-defined schema found to export." in result.stdout
    assert not directory.exists()


@dataclass
class ExportErrorCase:
    name: str
    status_code: int
    message: str
    expected_output: str


EXPORT_ERROR_CASES = [
    ExportErrorCase(
        name="older-server",
        status_code=422,
        message="Unable to find the schema export in the database.",
        expected_output=f"Infrahub {SCHEMA_EXPORT_MIN_INFRAHUB_VERSION} or later",
    ),
    ExportErrorCase(
        name="422-other-message",
        status_code=422,
        message="Unable to find the schema NetworkDevice in the database.",
        expected_output="HTTP 422: Unable to find the schema NetworkDevice in the database.",
    ),
    ExportErrorCase(
        name="500",
        status_code=500,
        message="Internal server error",
        expected_output="HTTP 500: Internal server error",
    ),
]


@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in EXPORT_ERROR_CASES])
def test_schema_export_error_response(httpx_mock: HTTPXMock, tmp_path: Path, case: ExportErrorCase) -> None:
    httpx_mock.add_response(
        method="GET",
        url=EXPORT_URL,
        status_code=case.status_code,
        json={"data": None, "errors": [{"message": case.message, "extensions": {"code": case.status_code}}]},
    )
    directory = tmp_path / "export"

    result = runner.invoke(app, ["schema", "export", "--directory", str(directory)])

    assert result.exit_code == 1
    output = remove_ansi_color(result.stdout.replace("\n", ""))
    assert case.expected_output in output
    if case.name != "older-server":
        assert SCHEMA_EXPORT_MIN_INFRAHUB_VERSION not in output
    assert not directory.exists()
