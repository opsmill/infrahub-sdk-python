from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk.schema import (
    GenericSchemaAPI,
    InfrahubSchemaBase,
    NodeSchemaAPI,
    ProfileSchemaAPI,
    SchemaExport,
    TemplateSchemaAPI,
)
from infrahub_sdk.schema.export import schema_to_export_dict

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from tests.unit.sdk.conftest import BothClients

client_types = ["standard", "sync"]

# ---------------------------------------------------------------------------
# Minimal schema API response builders (reused from ctl tests)
# ---------------------------------------------------------------------------

_BASE_NODE: dict[str, Any] = {
    "id": None,
    "state": "present",
    "hash": None,
    "hierarchy": None,
    "label": None,
    "description": None,
    "include_in_menu": None,
    "menu_placement": None,
    "display_label": None,
    "display_labels": None,
    "human_friendly_id": None,
    "icon": None,
    "uniqueness_constraints": None,
    "documentation": None,
    "order_by": None,
    "inherit_from": [],
    "branch": "aware",
    "default_filter": None,
    "generate_profile": True,
    "generate_template": False,
    "parent": None,
    "children": None,
    "attributes": [],
    "relationships": [],
}

_BASE_GENERIC: dict[str, Any] = {
    "id": None,
    "state": "present",
    "hash": None,
    "used_by": [],
    "label": None,
    "description": None,
    "include_in_menu": None,
    "menu_placement": None,
    "display_label": None,
    "display_labels": None,
    "human_friendly_id": None,
    "icon": None,
    "uniqueness_constraints": None,
    "documentation": None,
    "order_by": None,
    "attributes": [],
    "relationships": [],
}


def _make_node_schema(namespace: str, name: str) -> NodeSchemaAPI:
    return NodeSchemaAPI(**{**_BASE_NODE, "namespace": namespace, "name": name})


def _make_generic_schema(namespace: str, name: str) -> GenericSchemaAPI:
    return GenericSchemaAPI(**{**_BASE_GENERIC, "namespace": namespace, "name": name})


def _make_profile_schema(namespace: str, name: str) -> ProfileSchemaAPI:
    return ProfileSchemaAPI(
        **{
            **_BASE_NODE,
            "namespace": namespace,
            "name": name,
        }
    )


def _make_template_schema(namespace: str, name: str) -> TemplateSchemaAPI:
    return TemplateSchemaAPI(
        **{
            **_BASE_NODE,
            "namespace": namespace,
            "name": name,
        }
    )


# ---------------------------------------------------------------------------
# _build_export_schemas tests
# ---------------------------------------------------------------------------


class TestBuildExportSchemas:
    def test_separates_nodes_and_generics(self) -> None:
        schema_nodes = {
            "InfraDevice": _make_node_schema("Infra", "Device"),
            "InfraInterface": _make_generic_schema("Infra", "Interface"),
        }
        result = InfrahubSchemaBase._build_export_schemas(schema_nodes)
        assert isinstance(result, SchemaExport)
        assert "Infra" in result.namespaces
        assert len(result.namespaces["Infra"].nodes) == 1
        assert len(result.namespaces["Infra"].generics) == 1
        assert result.namespaces["Infra"].nodes[0]["name"] == "Device"
        assert result.namespaces["Infra"].generics[0]["name"] == "Interface"

    def test_groups_by_namespace(self) -> None:
        schema_nodes = {
            "InfraDevice": _make_node_schema("Infra", "Device"),
            "DcimRack": _make_node_schema("Dcim", "Rack"),
        }
        result = InfrahubSchemaBase._build_export_schemas(schema_nodes)
        assert set(result.namespaces.keys()) == {"Infra", "Dcim"}

    def test_filters_profiles_and_templates(self) -> None:
        schema_nodes = {
            "InfraDevice": _make_node_schema("Infra", "Device"),
            "ProfileInfraDevice": _make_profile_schema("Profile", "InfraDevice"),
            "TemplateInfraDevice": _make_template_schema("Template", "InfraDevice"),
        }
        result = InfrahubSchemaBase._build_export_schemas(schema_nodes)
        assert "Infra" in result.namespaces
        assert "Profile" not in result.namespaces
        assert "Template" not in result.namespaces

    def test_filters_restricted_namespaces(self) -> None:
        schema_nodes = {
            "CoreRepository": _make_node_schema("Core", "Repository"),
            "BuiltinTag": _make_node_schema("Builtin", "Tag"),
            "InfraDevice": _make_node_schema("Infra", "Device"),
        }
        result = InfrahubSchemaBase._build_export_schemas(schema_nodes)
        assert "Core" not in result.namespaces
        assert "Builtin" not in result.namespaces
        assert "Infra" in result.namespaces

    def test_namespace_filter(self) -> None:
        schema_nodes = {
            "InfraDevice": _make_node_schema("Infra", "Device"),
            "DcimRack": _make_node_schema("Dcim", "Rack"),
        }
        result = InfrahubSchemaBase._build_export_schemas(schema_nodes, namespaces=["Infra"])
        assert "Infra" in result.namespaces
        assert "Dcim" not in result.namespaces

    def test_empty_when_no_user_schemas(self) -> None:
        schema_nodes = {
            "CoreRepository": _make_node_schema("Core", "Repository"),
        }
        result = InfrahubSchemaBase._build_export_schemas(schema_nodes)
        assert result.namespaces == {}

    def test_warns_on_restricted_namespaces(self) -> None:
        schema_nodes = {
            "InfraDevice": _make_node_schema("Infra", "Device"),
        }
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = InfrahubSchemaBase._build_export_schemas(schema_nodes, namespaces=["Infra", "Core"])
        assert len(w) == 1
        assert "Core" in str(w[0].message)
        assert "Infra" in result.namespaces

    def test_to_dict(self) -> None:
        schema_nodes = {
            "InfraDevice": _make_node_schema("Infra", "Device"),
            "InfraInterface": _make_generic_schema("Infra", "Interface"),
        }
        result = InfrahubSchemaBase._build_export_schemas(schema_nodes)
        as_dict = result.to_dict()
        assert isinstance(as_dict, dict)
        assert "Infra" in as_dict
        assert isinstance(as_dict["Infra"], dict)
        assert len(as_dict["Infra"]["nodes"]) == 1
        assert len(as_dict["Infra"]["generics"]) == 1


def test_export_preserves_non_default_ordered_flag() -> None:
    """`ordered: false` survives the fetch -> export round-trip; the default `true` is omitted."""
    node = NodeSchemaAPI(
        **{
            **_BASE_NODE,
            "namespace": "Infra",
            "name": "Device",
            "attributes": [
                {"name": "tags_unordered", "kind": "List", "ordered": False},
                {"name": "tags_ordered", "kind": "List"},
            ],
        }
    )
    exported = schema_to_export_dict(node)
    attrs = {attr["name"]: attr for attr in exported["attributes"]}
    assert attrs["tags_unordered"]["ordered"] is False
    assert "ordered" not in attrs["tags_ordered"]


# ---------------------------------------------------------------------------
# Integration tests for export() method on client.schema
# ---------------------------------------------------------------------------


def _schema_response(
    nodes: list[dict] | None = None,
    generics: list[dict] | None = None,
    profiles: list[dict] | None = None,
    templates: list[dict] | None = None,
) -> dict:
    return {
        "main": "aabbccdd",
        "nodes": nodes or [],
        "generics": generics or [],
        "profiles": profiles or [],
        "templates": templates or [],
    }


def _make_node_dict(namespace: str, name: str) -> dict[str, Any]:
    return {**_BASE_NODE, "namespace": namespace, "name": name}


def _make_generic_dict(namespace: str, name: str) -> dict[str, Any]:
    return {**_BASE_GENERIC, "namespace": namespace, "name": name}


@pytest.mark.parametrize("client_type", client_types)
async def test_export_returns_user_schemas(httpx_mock: HTTPXMock, clients: BothClients, client_type: str) -> None:
    response = _schema_response(
        nodes=[_make_node_dict("Infra", "Device"), _make_node_dict("Dcim", "Rack")],
        generics=[_make_generic_dict("Infra", "GenericInterface")],
    )
    httpx_mock.add_response(method="GET", url="http://mock/api/schema?branch=main", json=response)

    if client_type == "standard":
        result = await clients.standard.schema.export(branch="main")
    else:
        result = clients.sync.schema.export(branch="main")

    assert isinstance(result, SchemaExport)
    assert "Infra" in result.namespaces
    assert "Dcim" in result.namespaces
    assert len(result.namespaces["Infra"].nodes) == 1
    assert len(result.namespaces["Infra"].generics) == 1
    assert len(result.namespaces["Dcim"].nodes) == 1


@pytest.mark.parametrize("client_type", client_types)
async def test_export_with_namespace_filter(httpx_mock: HTTPXMock, clients: BothClients, client_type: str) -> None:
    response = _schema_response(
        nodes=[_make_node_dict("Infra", "Device")],
    )
    httpx_mock.add_response(method="GET", url="http://mock/api/schema?branch=main&namespaces=Infra", json=response)

    if client_type == "standard":
        result = await clients.standard.schema.export(branch="main", namespaces=["Infra"])
    else:
        result = clients.sync.schema.export(branch="main", namespaces=["Infra"])

    assert "Infra" in result.namespaces
    assert "Dcim" not in result.namespaces


@pytest.mark.parametrize("client_type", client_types)
async def test_export_empty_when_only_restricted(httpx_mock: HTTPXMock, clients: BothClients, client_type: str) -> None:
    response = _schema_response(nodes=[_make_node_dict("Core", "Repository")])
    httpx_mock.add_response(method="GET", url="http://mock/api/schema?branch=main", json=response)

    if client_type == "standard":
        result = await clients.standard.schema.export(branch="main")
    else:
        result = clients.sync.schema.export(branch="main")

    assert result.namespaces == {}
