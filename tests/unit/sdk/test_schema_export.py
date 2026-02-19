from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk import Config, InfrahubClient, InfrahubClientSync

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock
from infrahub_sdk.schema import (
    GenericSchemaAPI,
    InfrahubSchemaBase,
    NodeSchemaAPI,
    ProfileSchemaAPI,
    TemplateSchemaAPI,
)

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
    "generate_profile": None,
    "generate_template": None,
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
        assert "Infra" in result
        assert len(result["Infra"]["nodes"]) == 1
        assert len(result["Infra"]["generics"]) == 1
        assert result["Infra"]["nodes"][0]["name"] == "Device"
        assert result["Infra"]["generics"][0]["name"] == "Interface"

    def test_groups_by_namespace(self) -> None:
        schema_nodes = {
            "InfraDevice": _make_node_schema("Infra", "Device"),
            "DcimRack": _make_node_schema("Dcim", "Rack"),
        }
        result = InfrahubSchemaBase._build_export_schemas(schema_nodes)
        assert set(result.keys()) == {"Infra", "Dcim"}

    def test_filters_profiles_and_templates(self) -> None:
        schema_nodes = {
            "InfraDevice": _make_node_schema("Infra", "Device"),
            "ProfileInfraDevice": _make_profile_schema("Profile", "InfraDevice"),
            "TemplateInfraDevice": _make_template_schema("Template", "InfraDevice"),
        }
        result = InfrahubSchemaBase._build_export_schemas(schema_nodes)
        assert "Infra" in result
        assert "Profile" not in result
        assert "Template" not in result

    def test_filters_restricted_namespaces(self) -> None:
        schema_nodes = {
            "CoreRepository": _make_node_schema("Core", "Repository"),
            "BuiltinTag": _make_node_schema("Builtin", "Tag"),
            "InfraDevice": _make_node_schema("Infra", "Device"),
        }
        result = InfrahubSchemaBase._build_export_schemas(schema_nodes)
        assert "Core" not in result
        assert "Builtin" not in result
        assert "Infra" in result

    def test_namespace_filter(self) -> None:
        schema_nodes = {
            "InfraDevice": _make_node_schema("Infra", "Device"),
            "DcimRack": _make_node_schema("Dcim", "Rack"),
        }
        result = InfrahubSchemaBase._build_export_schemas(schema_nodes, namespaces=["Infra"])
        assert "Infra" in result
        assert "Dcim" not in result

    def test_empty_when_no_user_schemas(self) -> None:
        schema_nodes = {
            "CoreRepository": _make_node_schema("Core", "Repository"),
        }
        result = InfrahubSchemaBase._build_export_schemas(schema_nodes)
        assert result == {}


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


@pytest.mark.parametrize("client_type", ["async", "sync"])
async def test_export_returns_user_schemas(httpx_mock: HTTPXMock, client_type: str) -> None:
    response = _schema_response(
        nodes=[_make_node_dict("Infra", "Device"), _make_node_dict("Dcim", "Rack")],
        generics=[_make_generic_dict("Infra", "GenericInterface")],
    )
    httpx_mock.add_response(method="GET", url="http://mock/api/schema?branch=main", json=response)

    if client_type == "async":
        client = InfrahubClient(config=Config(address="http://mock", insert_tracker=True))
        result = await client.schema.export(branch="main")
    else:
        client = InfrahubClientSync(config=Config(address="http://mock", insert_tracker=True))
        result = client.schema.export(branch="main")

    assert "Infra" in result
    assert "Dcim" in result
    assert len(result["Infra"]["nodes"]) == 1
    assert len(result["Infra"]["generics"]) == 1
    assert len(result["Dcim"]["nodes"]) == 1


@pytest.mark.parametrize("client_type", ["async", "sync"])
async def test_export_with_namespace_filter(httpx_mock: HTTPXMock, client_type: str) -> None:
    response = _schema_response(
        nodes=[_make_node_dict("Infra", "Device"), _make_node_dict("Dcim", "Rack")],
    )
    httpx_mock.add_response(method="GET", url="http://mock/api/schema?branch=main", json=response)

    if client_type == "async":
        client = InfrahubClient(config=Config(address="http://mock", insert_tracker=True))
        result = await client.schema.export(branch="main", namespaces=["Infra"])
    else:
        client = InfrahubClientSync(config=Config(address="http://mock", insert_tracker=True))
        result = client.schema.export(branch="main", namespaces=["Infra"])

    assert "Infra" in result
    assert "Dcim" not in result


@pytest.mark.parametrize("client_type", ["async", "sync"])
async def test_export_empty_when_only_restricted(httpx_mock: HTTPXMock, client_type: str) -> None:
    response = _schema_response(nodes=[_make_node_dict("Core", "Repository")])
    httpx_mock.add_response(method="GET", url="http://mock/api/schema?branch=main", json=response)

    if client_type == "async":
        client = InfrahubClient(config=Config(address="http://mock", insert_tracker=True))
        result = await client.schema.export(branch="main")
    else:
        client = InfrahubClientSync(config=Config(address="http://mock", insert_tracker=True))
        result = client.schema.export(branch="main")

    assert result == {}
