"""Unit tests for the ``infrahub schema`` end-user CLI subcommand group."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from infrahub_sdk.ctl.cli_commands import app
from infrahub_sdk.schema import NodeSchemaAPI

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
