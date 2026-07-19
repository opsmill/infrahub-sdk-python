from __future__ import annotations

import inspect
import ipaddress
import json
import tempfile
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from infrahub_sdk.exceptions import FeatureNotSupportedError, NodeNotFoundError
from infrahub_sdk.node import (
    InfrahubNode,
    InfrahubNodeBase,
    InfrahubNodeSync,
    RelatedNodeBase,
    RelationshipManager,
    RelationshipManagerBase,
    parse_human_friendly_id,
)
from infrahub_sdk.node.constants import SAFE_VALUE
from infrahub_sdk.node.metadata import NodeMetadata, RelationshipMetadata
from infrahub_sdk.node.property import NodeProperty
from infrahub_sdk.node.related_node import RelatedNode, RelatedNodeSync

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from inspect import Parameter
    from typing import Any

    from pytest_httpx import HTTPXMock

    from infrahub_sdk import InfrahubClient, InfrahubClientSync
    from infrahub_sdk.schema import GenericSchema, NodeSchemaAPI
    from tests.unit.sdk.conftest import BothClients


async_node_methods = [
    method for method in dir(InfrahubNode) if not method.startswith("_") and method not in {"hfid", "hfid_str"}
]
sync_node_methods = [
    method for method in dir(InfrahubNodeSync) if not method.startswith("_") and method not in {"hfid", "hfid_str"}
]

client_types = ["standard", "sync"]

WITH_PROPERTY = "with_property"
WITHOUT_PROPERTY = "without_property"
property_tests = [WITHOUT_PROPERTY, WITH_PROPERTY]


SAFE_GRAPHQL_VALUES = [
    pytest.param("", id="allow-empty"),
    pytest.param("user1", id="allow-normal"),
    pytest.param("User Lastname", id="allow-space"),
    pytest.param("020a1c39-6071-4bf8-9336-ffb7a001e665", id="allow-uuid"),
    pytest.param("user.lastname", id="allow-dots"),
    pytest.param("/opt/repos/backbone-links", id="allow-filepaths"),
    pytest.param("https://github.com/opsmill/infrahub-demo-edge", id="allow-urls"),
]

UNSAFE_GRAPHQL_VALUES = [
    pytest.param('No "quote"', id="disallow-quotes"),
    pytest.param("Line \n break", id="disallow-linebreaks"),
]


async def set_builtin_tag_schema_cache(client: InfrahubClient | InfrahubClientSync) -> None:
    # Set tag schema in cache to avoid needed to request the server.
    builtin_tag_schema = {
        "version": "1.0",
        "nodes": [
            {
                "name": "Tag",
                "namespace": "Builtin",
                "default_filter": "name__value",
                "display_label": "name__value",
                "branch": "aware",
            }
        ],
    }
    client.schema.set_cache(builtin_tag_schema)


async def test_method_sanity() -> None:
    """Validate that there is at least one public method and that both clients look the same."""
    assert async_node_methods
    assert async_node_methods == sync_node_methods


@pytest.mark.parametrize("value", SAFE_GRAPHQL_VALUES)
def test_validate_graphql_value(value: str) -> None:
    """All these values are safe and should not be converted."""
    assert SAFE_VALUE.match(value)


@pytest.mark.parametrize("value", UNSAFE_GRAPHQL_VALUES)
def test_identify_unsafe_graphql_value(value: str) -> None:
    """All these values are safe and should not be converted."""
    assert not SAFE_VALUE.match(value)


@pytest.mark.parametrize("method", async_node_methods)
async def test_validate_method_signature(
    method: str,
    replace_async_parameter_annotations: Callable[[Mapping[str, Parameter]], list[tuple[str, str]]],
    replace_sync_parameter_annotations: Callable[[Mapping[str, Parameter]], list[tuple[str, str]]],
    replace_async_return_annotation: Callable[[str], str],
    replace_sync_return_annotation: Callable[[str], str],
) -> None:
    exclude_parameters = ["client"]
    async_method = getattr(InfrahubNode, method)
    sync_method = getattr(InfrahubNodeSync, method)
    async_sig = inspect.signature(async_method)
    sync_sig = inspect.signature(sync_method)

    # Extract names of parameters and exclude some from the comparaison like client
    async_params_name = async_sig.parameters.keys()
    sync_params_name = sync_sig.parameters.keys()
    async_params = {key: value for key, value in async_sig.parameters.items() if key not in exclude_parameters}
    sync_params = {key: value for key, value in sync_sig.parameters.items() if key not in exclude_parameters}

    assert async_params_name == sync_params_name
    assert replace_sync_parameter_annotations(async_params) == replace_sync_parameter_annotations(sync_params)
    assert replace_async_parameter_annotations(async_params) == replace_async_parameter_annotations(sync_params)
    assert replace_sync_return_annotation(async_sig.return_annotation) == replace_sync_return_annotation(
        sync_sig.return_annotation
    )
    assert replace_async_return_annotation(async_sig.return_annotation) == replace_async_return_annotation(
        sync_sig.return_annotation
    )


@pytest.mark.parametrize(
    ("hfid", "expected_kind", "expected_hfid"), [("BuiltinLocation__JFK1", "BuiltinLocation", ["JFK1"])]
)
def test_parse_human_friendly_id(hfid: str, expected_kind: str, expected_hfid: list[str]) -> None:
    kind, hfid = parse_human_friendly_id(hfid)
    assert kind == expected_kind
    assert hfid == expected_hfid


@pytest.mark.parametrize("client_type", client_types)
async def test_init_node_no_data(client: InfrahubClient, location_schema: NodeSchemaAPI, client_type: str) -> None:
    if client_type == "standard":
        node = InfrahubNode(client=client, schema=location_schema)
    else:
        node = InfrahubNodeSync(client=client, schema=location_schema)
    assert sorted(node._attributes) == ["description", "name", "type"]

    assert hasattr(node, "name")
    assert hasattr(node, "description")
    assert hasattr(node, "type")


@pytest.mark.parametrize("client_type", client_types)
async def test_node_hfid(client: InfrahubClient, schema_with_hfid: dict[str, NodeSchemaAPI], client_type: str) -> None:
    location_data = {"name": {"value": "JFK1"}, "description": {"value": "JFK Airport"}, "type": {"value": "SITE"}}
    if client_type == "standard":
        location = InfrahubNode(client=client, schema=schema_with_hfid["location"], data=location_data)
    else:
        location = InfrahubNodeSync(client=client, schema=schema_with_hfid["location"], data=location_data)

    assert location.hfid == [location.name.value]
    assert location.get_human_friendly_id_as_string() == "JFK1"
    assert location.hfid_str == "BuiltinLocation__JFK1"

    rack_data = {"facility_id": {"value": "RACK1"}, "location": location}
    if client_type == "standard":
        rack = InfrahubNode(client=client, schema=schema_with_hfid["rack"], data=rack_data)
    else:
        rack = InfrahubNodeSync(client=client, schema=schema_with_hfid["rack"], data=rack_data)

    assert rack.hfid == [rack.facility_id.value, rack.location.get().name.value]
    assert rack.get_human_friendly_id_as_string() == "RACK1__JFK1"
    assert rack.hfid_str == "BuiltinRack__RACK1__JFK1"


@pytest.mark.parametrize("client_type", client_types)
async def test_node_create_upsert_excludes_hfid(
    httpx_mock: HTTPXMock,
    clients: BothClients,
    schema_with_hfid: dict[str, NodeSchemaAPI],
    client_type: str,
) -> None:
    """Upsert must never send the hfid in the mutation payload, for both async and sync clients.

    Sending the hfid on an upsert adds server-side performance overhead, so create(allow_upsert=True)
    excludes it. The async and sync clients must behave identically here.
    """
    httpx_mock.add_response(
        method="POST",
        json={"data": {"BuiltinLocationUpsert": {"ok": True, "object": {"id": "abcabc"}}}},
        match_headers={"X-Infrahub-Tracker": "mutation-builtinlocation-upsert"},
    )
    location_data = {"name": {"value": "JFK1"}, "description": {"value": "JFK Airport"}, "type": {"value": "SITE"}}

    if client_type == "standard":
        location = InfrahubNode(client=clients.standard, schema=schema_with_hfid["location"], data=location_data)
        await location.create(allow_upsert=True)
    else:
        location = InfrahubNodeSync(client=clients.sync, schema=schema_with_hfid["location"], data=location_data)
        location.create(allow_upsert=True)

    post_requests = [r for r in httpx_mock.get_requests() if r.method == "POST"]
    assert len(post_requests) == 1
    payload = json.loads(post_requests[0].content)
    assert "hfid" not in payload["query"]


@pytest.mark.parametrize("client_type", client_types)
async def test_init_node_data_user(client: InfrahubClient, location_schema: NodeSchemaAPI, client_type: str) -> None:
    data = {
        "name": {"value": "JFK1"},
        "description": {"value": "JFK Airport"},
        "type": {"value": "SITE"},
    }
    if client_type == "standard":
        node = InfrahubNode(client=client, schema=location_schema, data=data)
    else:
        node = InfrahubNodeSync(client=client, schema=location_schema, data=data)

    assert node.name.value == "JFK1"
    assert node.name.is_protected is None
    assert node.description.value == "JFK Airport"
    assert node.type.value == "SITE"


@pytest.mark.parametrize("client_type", client_types)
async def test_init_node_data_user_with_relationships(
    client: InfrahubClient, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    data = {
        "name": {"value": "JFK1"},
        "description": {"value": "JFK Airport"},
        "type": {"value": "SITE"},
        "primary_tag": "pppppppp",
        "tags": [{"id": "aaaaaa"}, {"id": "bbbb"}],
    }
    if client_type == "standard":
        node = InfrahubNode(client=client, schema=location_schema, data=data)
    else:
        node = InfrahubNodeSync(client=client, schema=location_schema, data=data)

    assert node.name.value == "JFK1"
    assert node.name.is_protected is None
    assert node.description.value == "JFK Airport"
    assert node.type.value == "SITE"

    assert isinstance(node.tags, RelationshipManagerBase)
    assert len(node.tags.peers) == 2
    assert isinstance(node.tags.peers[0], RelatedNodeBase)
    assert isinstance(node.primary_tag, RelatedNodeBase)
    assert node.primary_tag.id == "pppppppp"

    keys = dir(node)
    assert "name" in keys
    assert "type" in keys
    assert "tags" in keys
    assert "get_kind" in keys


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize(
    "rel_data",
    [
        {"id": "pppppppp", "__typename": "BuiltinTag"},
        {"hfid": ["pppp", "pppp"], "display_label": "mmmm", "kind": "BuiltinTag"},
    ],
)
async def test_init_node_data_user_with_relationships_using_related_node(
    client: InfrahubClient, location_schema: NodeSchemaAPI, client_type: str, rel_data: dict[str, Any]
) -> None:
    rel_schema = location_schema.get_relationship(name="primary_tag")
    if client_type == "standard":
        primary_tag = RelatedNode(name="primary_tag", branch="main", client=client, schema=rel_schema, data=rel_data)
    else:
        primary_tag = RelatedNodeSync(
            name="primary_tag", branch="main", client=client, schema=rel_schema, data=rel_data
        )

    data = {
        "name": {"value": "JFK1"},
        "description": {"value": "JFK Airport"},
        "type": {"value": "SITE"},
        "primary_tag": primary_tag,
        "tags": [{"id": "aaaaaa"}, {"id": "bbbb"}],
    }
    if client_type == "standard":
        node = InfrahubNode(client=client, schema=location_schema, data=data)
    else:
        node = InfrahubNodeSync(client=client, schema=location_schema, data=data)

    assert node.name.value == "JFK1"
    assert node.name.is_protected is None
    assert node.description.value == "JFK Airport"
    assert node.type.value == "SITE"

    assert isinstance(node.tags, RelationshipManagerBase)
    assert len(node.tags.peers) == 2
    assert isinstance(node.tags.peers[0], RelatedNodeBase)
    assert isinstance(node.primary_tag, RelatedNodeBase)
    assert node.primary_tag.id == rel_data.get("id")
    assert node.primary_tag.hfid == rel_data.get("hfid")
    assert node.primary_tag.typename == rel_data.get("__typename")
    assert node.primary_tag.kind == rel_data.get("kind")
    assert node.primary_tag.display_label == rel_data.get("display_label")

    keys = dir(node)
    assert "name" in keys
    assert "type" in keys
    assert "tags" in keys
    assert "get_kind" in keys


@pytest.mark.parametrize("property_test", property_tests)
@pytest.mark.parametrize("client_type", client_types)
async def test_init_node_data_graphql(
    client: InfrahubClient,
    location_schema: NodeSchemaAPI,
    location_data01: dict[str, Any],
    location_data01_property: dict[str, Any],
    client_type: str,
    property_test: str,
) -> None:
    location_data = location_data01 if property_test == WITHOUT_PROPERTY else location_data01_property

    if client_type == "standard":
        node = InfrahubNode(client=client, schema=location_schema, data=location_data)
    else:
        node = InfrahubNodeSync(client=client, schema=location_schema, data=location_data)

    assert node.name.value == "DFW"
    assert node.name.is_protected is True if property_test == WITH_PROPERTY else node.name.is_protected is None
    assert node.description.value is None
    assert node.type.value == "SITE"

    assert isinstance(node.tags, RelationshipManagerBase)
    assert len(node.tags.peers) == 1
    assert isinstance(node.tags.peers[0], RelatedNodeBase)
    assert isinstance(node.primary_tag, RelatedNodeBase)
    assert node.primary_tag.id == "rrrrrrrr-rrrr-rrrr-rrrr-rrrrrrrrrrrr"
    assert node.primary_tag.typename == "BuiltinTag"


@pytest.mark.parametrize("client_type", client_types)
async def test_cardinality_many_requires_list(
    client: InfrahubClient, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    data = {
        "name": {"value": "JFK1"},
        "tags": {"id": "pppppppp"},
    }
    with pytest.raises(ValueError, match=r"expects a list of nodes"):
        if client_type == "standard":
            InfrahubNode(client=client, schema=location_schema, data=data)
        else:
            InfrahubNodeSync(client=client, schema=location_schema, data=data)


@pytest.mark.parametrize("client_type", client_types)
async def test_cardinality_many_accepts_list(
    client: InfrahubClient, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    data = {
        "name": {"value": "JFK1"},
        "tags": [{"id": "aaaaaa"}, {"id": "bbbb"}],
    }
    if client_type == "standard":
        node = InfrahubNode(client=client, schema=location_schema, data=data)
    else:
        node = InfrahubNodeSync(client=client, schema=location_schema, data=data)
    assert len(node.tags.peers) == 2


@pytest.mark.parametrize("client_type", client_types)
async def test_query_data_no_filters_property(
    clients: BothClients, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=location_schema)
        data = await node.generate_query_data(property=True)
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=location_schema)
        data = node.generate_query_data(property=True)

    assert data == {
        "BuiltinLocation": {
            "@filters": {},
            "count": None,
            "edges": {
                "node": {
                    "__typename": None,
                    "id": None,
                    "hfid": None,
                    "display_label": None,
                    "name": {
                        "is_default": None,
                        "is_from_profile": None,
                        "is_protected": None,
                        "owner": {
                            "__typename": None,
                            "display_label": None,
                            "id": None,
                        },
                        "source": {
                            "__typename": None,
                            "display_label": None,
                            "id": None,
                        },
                        "updated_at": None,
                        "value": None,
                    },
                    "description": {
                        "is_default": None,
                        "is_from_profile": None,
                        "is_protected": None,
                        "owner": {
                            "__typename": None,
                            "display_label": None,
                            "id": None,
                        },
                        "source": {
                            "__typename": None,
                            "display_label": None,
                            "id": None,
                        },
                        "updated_at": None,
                        "value": None,
                    },
                    "type": {
                        "is_default": None,
                        "is_from_profile": None,
                        "is_protected": None,
                        "owner": {
                            "__typename": None,
                            "display_label": None,
                            "id": None,
                        },
                        "source": {
                            "__typename": None,
                            "display_label": None,
                            "id": None,
                        },
                        "updated_at": None,
                        "value": None,
                    },
                    "primary_tag": {
                        "properties": {
                            "is_protected": None,
                            "owner": {
                                "__typename": None,
                                "display_label": None,
                                "id": None,
                            },
                            "source": {
                                "__typename": None,
                                "display_label": None,
                                "id": None,
                            },
                            "updated_at": None,
                        },
                        "node": {
                            "id": None,
                            "hfid": None,
                            "display_label": None,
                            "__typename": None,
                        },
                    },
                },
            },
        },
    }


@pytest.mark.parametrize("client_type", client_types)
async def test_query_data_no_filters(clients: BothClients, location_schema: NodeSchemaAPI, client_type: str) -> None:
    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=location_schema)
        data = await node.generate_query_data()
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=location_schema)
        data = node.generate_query_data()

    assert data == {
        "BuiltinLocation": {
            "@filters": {},
            "count": None,
            "edges": {
                "node": {
                    "__typename": None,
                    "id": None,
                    "hfid": None,
                    "display_label": None,
                    "name": {
                        "value": None,
                    },
                    "description": {
                        "value": None,
                    },
                    "type": {
                        "value": None,
                    },
                    "primary_tag": {
                        "node": {
                            "id": None,
                            "hfid": None,
                            "display_label": None,
                            "__typename": None,
                        },
                    },
                },
            },
        },
    }


@pytest.mark.parametrize("client_type", client_types)
async def test_query_data_node_property(clients: BothClients, location_schema: NodeSchemaAPI, client_type: str) -> None:
    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=location_schema)
        data = await node.generate_query_data_node(property=True)
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=location_schema)
        data = node.generate_query_data_node(property=True)

    assert data == {
        "name": {
            "is_default": None,
            "is_from_profile": None,
            "is_protected": None,
            "owner": {"__typename": None, "display_label": None, "id": None},
            "source": {"__typename": None, "display_label": None, "id": None},
            "updated_at": None,
            "value": None,
        },
        "description": {
            "is_default": None,
            "is_from_profile": None,
            "is_protected": None,
            "owner": {"__typename": None, "display_label": None, "id": None},
            "source": {"__typename": None, "display_label": None, "id": None},
            "updated_at": None,
            "value": None,
        },
        "type": {
            "is_default": None,
            "is_from_profile": None,
            "is_protected": None,
            "owner": {"__typename": None, "display_label": None, "id": None},
            "source": {"__typename": None, "display_label": None, "id": None},
            "updated_at": None,
            "value": None,
        },
        "primary_tag": {
            "properties": {
                "is_protected": None,
                "owner": {
                    "__typename": None,
                    "display_label": None,
                    "id": None,
                },
                "source": {
                    "__typename": None,
                    "display_label": None,
                    "id": None,
                },
                "updated_at": None,
            },
            "node": {
                "id": None,
                "hfid": None,
                "display_label": None,
                "__typename": None,
            },
        },
    }


@pytest.mark.parametrize("client_type", client_types)
async def test_query_data_node(clients: BothClients, location_schema: NodeSchemaAPI, client_type: str) -> None:
    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=location_schema)
        data = await node.generate_query_data_node()
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=location_schema)
        data = node.generate_query_data_node()

    assert data == {
        "name": {
            "value": None,
        },
        "description": {
            "value": None,
        },
        "type": {
            "value": None,
        },
        "primary_tag": {
            "node": {
                "id": None,
                "hfid": None,
                "display_label": None,
                "__typename": None,
            },
        },
    }


@pytest.mark.parametrize("client_type", client_types)
async def test_query_data_with_prefetch_relationships_property(
    clients: BothClients, mock_schema_query_02: HTTPXMock, client_type: str
) -> None:
    if client_type == "standard":
        location_schema: GenericSchema = await clients.standard.schema.get(kind="BuiltinLocation")  # type: ignore[annotation-unchecked]
        node = InfrahubNode(client=clients.standard, schema=location_schema)
        data = await node.generate_query_data(prefetch_relationships=True, property=True)
    else:
        location_schema: GenericSchema = clients.sync.schema.get(kind="BuiltinLocation")  # type: ignore[annotation-unchecked]
        node = InfrahubNodeSync(client=clients.sync, schema=location_schema)
        data = node.generate_query_data(prefetch_relationships=True, property=True)

    assert data == {
        "BuiltinLocation": {
            "@filters": {},
            "count": None,
            "edges": {
                "node": {
                    "__typename": None,
                    "id": None,
                    "hfid": None,
                    "display_label": None,
                    "name": {
                        "is_default": None,
                        "is_from_profile": None,
                        "is_protected": None,
                        "owner": {
                            "__typename": None,
                            "display_label": None,
                            "id": None,
                        },
                        "source": {
                            "__typename": None,
                            "display_label": None,
                            "id": None,
                        },
                        "updated_at": None,
                        "value": None,
                    },
                    "description": {
                        "is_default": None,
                        "is_from_profile": None,
                        "is_protected": None,
                        "owner": {
                            "__typename": None,
                            "display_label": None,
                            "id": None,
                        },
                        "source": {
                            "__typename": None,
                            "display_label": None,
                            "id": None,
                        },
                        "updated_at": None,
                        "value": None,
                    },
                    "type": {
                        "is_default": None,
                        "is_from_profile": None,
                        "is_protected": None,
                        "owner": {
                            "__typename": None,
                            "display_label": None,
                            "id": None,
                        },
                        "source": {
                            "__typename": None,
                            "display_label": None,
                            "id": None,
                        },
                        "updated_at": None,
                        "value": None,
                    },
                    "primary_tag": {
                        "properties": {
                            "is_protected": None,
                            "owner": {
                                "__typename": None,
                                "display_label": None,
                                "id": None,
                            },
                            "source": {
                                "__typename": None,
                                "display_label": None,
                                "id": None,
                            },
                            "updated_at": None,
                        },
                        "node": {
                            "id": None,
                            "hfid": None,
                            "display_label": None,
                            "__typename": None,
                            "description": {
                                "is_default": None,
                                "is_from_profile": None,
                                "is_protected": None,
                                "owner": {
                                    "__typename": None,
                                    "display_label": None,
                                    "id": None,
                                },
                                "source": {
                                    "__typename": None,
                                    "display_label": None,
                                    "id": None,
                                },
                                "updated_at": None,
                                "value": None,
                            },
                            "name": {
                                "is_default": None,
                                "is_from_profile": None,
                                "is_protected": None,
                                "owner": {
                                    "__typename": None,
                                    "display_label": None,
                                    "id": None,
                                },
                                "source": {
                                    "__typename": None,
                                    "display_label": None,
                                    "id": None,
                                },
                                "updated_at": None,
                                "value": None,
                            },
                        },
                    },
                },
            },
        },
    }


@pytest.mark.parametrize("client_type", client_types)
async def test_query_data_with_prefetch_relationships(
    clients: BothClients, mock_schema_query_02: HTTPXMock, client_type: str
) -> None:
    if client_type == "standard":
        location_schema: GenericSchema = await clients.standard.schema.get(kind="BuiltinLocation")  # type: ignore[annotation-unchecked]
        node = InfrahubNode(client=clients.standard, schema=location_schema)
        data = await node.generate_query_data(prefetch_relationships=True)
    else:
        location_schema: GenericSchema = clients.sync.schema.get(kind="BuiltinLocation")  # type: ignore[annotation-unchecked]
        node = InfrahubNodeSync(client=clients.sync, schema=location_schema)
        data = node.generate_query_data(prefetch_relationships=True)

    assert data == {
        "BuiltinLocation": {
            "@filters": {},
            "count": None,
            "edges": {
                "node": {
                    "__typename": None,
                    "id": None,
                    "hfid": None,
                    "display_label": None,
                    "name": {
                        "value": None,
                    },
                    "description": {
                        "value": None,
                    },
                    "type": {
                        "value": None,
                    },
                    "primary_tag": {
                        "node": {
                            "id": None,
                            "hfid": None,
                            "display_label": None,
                            "__typename": None,
                            "description": {
                                "value": None,
                            },
                            "name": {
                                "value": None,
                            },
                        },
                    },
                },
            },
        },
    }


@pytest.mark.parametrize("client_type", client_types)
async def test_query_data_node_with_prefetch_relationships_property(
    clients: BothClients, mock_schema_query_02: HTTPXMock, client_type: str
) -> None:
    if client_type == "standard":
        location_schema: GenericSchema = await clients.standard.schema.get(kind="BuiltinLocation")  # type: ignore[assignment]
        node = InfrahubNode(client=clients.standard, schema=location_schema)
        data = await node.generate_query_data_node(prefetch_relationships=True, property=True)
    else:
        location_schema: GenericSchema = clients.sync.schema.get(kind="BuiltinLocation")  # type: ignore[assignment]
        node = InfrahubNodeSync(client=clients.sync, schema=location_schema)
        data = node.generate_query_data_node(prefetch_relationships=True, property=True)

    assert data == {
        "description": {
            "is_default": None,
            "is_from_profile": None,
            "is_protected": None,
            "owner": {"__typename": None, "display_label": None, "id": None},
            "source": {"__typename": None, "display_label": None, "id": None},
            "updated_at": None,
            "value": None,
        },
        "name": {
            "is_default": None,
            "is_from_profile": None,
            "is_protected": None,
            "owner": {"__typename": None, "display_label": None, "id": None},
            "source": {"__typename": None, "display_label": None, "id": None},
            "updated_at": None,
            "value": None,
        },
        "primary_tag": {
            "node": {
                "__typename": None,
                "description": {
                    "is_default": None,
                    "is_from_profile": None,
                    "is_protected": None,
                    "owner": {"__typename": None, "display_label": None, "id": None},
                    "source": {"__typename": None, "display_label": None, "id": None},
                    "updated_at": None,
                    "value": None,
                },
                "display_label": None,
                "id": None,
                "hfid": None,
                "name": {
                    "is_default": None,
                    "is_from_profile": None,
                    "is_protected": None,
                    "owner": {"__typename": None, "display_label": None, "id": None},
                    "source": {"__typename": None, "display_label": None, "id": None},
                    "updated_at": None,
                    "value": None,
                },
            },
            "properties": {
                "is_protected": None,
                "owner": {"__typename": None, "display_label": None, "id": None},
                "source": {"__typename": None, "display_label": None, "id": None},
                "updated_at": None,
            },
        },
        "type": {
            "is_default": None,
            "is_from_profile": None,
            "is_protected": None,
            "owner": {"__typename": None, "display_label": None, "id": None},
            "source": {"__typename": None, "display_label": None, "id": None},
            "updated_at": None,
            "value": None,
        },
    }


@pytest.mark.parametrize("client_type", client_types)
async def test_query_data_node_with_prefetch_relationships(
    clients: BothClients, mock_schema_query_02: HTTPXMock, client_type: str
) -> None:
    if client_type == "standard":
        location_schema: GenericSchema = await clients.standard.schema.get(kind="BuiltinLocation")  # type: ignore[assignment]
        node = InfrahubNode(client=clients.standard, schema=location_schema)
        data = await node.generate_query_data_node(prefetch_relationships=True)
    else:
        location_schema: GenericSchema = clients.sync.schema.get(kind="BuiltinLocation")  # type: ignore[assignment]
        node = InfrahubNodeSync(client=clients.sync, schema=location_schema)
        data = node.generate_query_data_node(prefetch_relationships=True)

    assert data == {
        "description": {
            "value": None,
        },
        "name": {
            "value": None,
        },
        "primary_tag": {
            "node": {
                "__typename": None,
                "description": {
                    "value": None,
                },
                "display_label": None,
                "id": None,
                "hfid": None,
                "name": {
                    "value": None,
                },
            },
        },
        "type": {
            "value": None,
        },
    }


@pytest.mark.parametrize("client_type", client_types)
async def test_query_data_generic_property(
    clients: BothClients, mock_schema_query_02: HTTPXMock, client_type: str
) -> None:
    if client_type == "standard":
        corenode_schema: GenericSchema = await clients.standard.schema.get(kind="CoreNode")  # type: ignore[assignment]
        node = InfrahubNode(client=clients.standard, schema=corenode_schema)
        data = await node.generate_query_data(fragment=False, property=True)
    else:
        corenode_schema: GenericSchema = clients.sync.schema.get(kind="CoreNode")  # type: ignore[assignment]
        node = InfrahubNodeSync(client=clients.sync, schema=corenode_schema)
        data = node.generate_query_data(fragment=False, property=True)

    assert data == {
        "CoreNode": {
            "@filters": {},
            "count": None,
            "edges": {
                "node": {
                    "__typename": None,
                    "id": None,
                    "hfid": None,
                    "display_label": None,
                },
            },
        },
    }


@pytest.mark.parametrize("client_type", client_types)
async def test_query_data_generic_fragment_property(
    clients: BothClients, mock_schema_query_02: HTTPXMock, client_type: str
) -> None:
    if client_type == "standard":
        corenode_schema: GenericSchema = await clients.standard.schema.get(kind="CoreNode")  # type: ignore[assignment]
        node = InfrahubNode(client=clients.standard, schema=corenode_schema)
        data = await node.generate_query_data(fragment=True, property=True)
    else:
        corenode_schema: GenericSchema = clients.sync.schema.get(kind="CoreNode")  # type: ignore[assignment]
        node = InfrahubNodeSync(client=clients.sync, schema=corenode_schema)
        data = node.generate_query_data(fragment=True, property=True)

    assert data == {
        "CoreNode": {
            "@filters": {},
            "count": None,
            "edges": {
                "node": {
                    "__typename": None,
                    "...on BuiltinLocation": {
                        "description": {
                            "@alias": "__alias__BuiltinLocation__description",
                            "is_default": None,
                            "is_from_profile": None,
                            "is_protected": None,
                            "owner": {
                                "__typename": None,
                                "display_label": None,
                                "id": None,
                            },
                            "source": {
                                "__typename": None,
                                "display_label": None,
                                "id": None,
                            },
                            "updated_at": None,
                            "value": None,
                        },
                        "name": {
                            "@alias": "__alias__BuiltinLocation__name",
                            "is_default": None,
                            "is_from_profile": None,
                            "is_protected": None,
                            "owner": {
                                "__typename": None,
                                "display_label": None,
                                "id": None,
                            },
                            "source": {
                                "__typename": None,
                                "display_label": None,
                                "id": None,
                            },
                            "updated_at": None,
                            "value": None,
                        },
                        "primary_tag": {
                            "@alias": "__alias__BuiltinLocation__primary_tag",
                            "node": {
                                "__typename": None,
                                "display_label": None,
                                "id": None,
                                "hfid": None,
                            },
                            "properties": {
                                "is_protected": None,
                                "owner": {
                                    "__typename": None,
                                    "display_label": None,
                                    "id": None,
                                },
                                "source": {
                                    "__typename": None,
                                    "display_label": None,
                                    "id": None,
                                },
                                "updated_at": None,
                            },
                        },
                        "type": {
                            "@alias": "__alias__BuiltinLocation__type",
                            "is_default": None,
                            "is_from_profile": None,
                            "is_protected": None,
                            "owner": {
                                "__typename": None,
                                "display_label": None,
                                "id": None,
                            },
                            "source": {
                                "__typename": None,
                                "display_label": None,
                                "id": None,
                            },
                            "updated_at": None,
                            "value": None,
                        },
                    },
                    "...on BuiltinTag": {
                        "description": {
                            "@alias": "__alias__BuiltinTag__description",
                            "is_default": None,
                            "is_from_profile": None,
                            "is_protected": None,
                            "owner": {
                                "__typename": None,
                                "display_label": None,
                                "id": None,
                            },
                            "source": {
                                "__typename": None,
                                "display_label": None,
                                "id": None,
                            },
                            "updated_at": None,
                            "value": None,
                        },
                        "name": {
                            "@alias": "__alias__BuiltinTag__name",
                            "is_default": None,
                            "is_from_profile": None,
                            "is_protected": None,
                            "owner": {
                                "__typename": None,
                                "display_label": None,
                                "id": None,
                            },
                            "source": {
                                "__typename": None,
                                "display_label": None,
                                "id": None,
                            },
                            "updated_at": None,
                            "value": None,
                        },
                    },
                    "display_label": None,
                    "id": None,
                    "hfid": None,
                },
            },
        },
    }


@pytest.mark.parametrize("client_type", client_types)
async def test_query_data_generic_fragment(
    clients: BothClients, mock_schema_query_02: HTTPXMock, client_type: str
) -> None:
    if client_type == "standard":
        corenode_schema: GenericSchema = await clients.standard.schema.get(kind="CoreNode")  # type: ignore[assignment]
        node = InfrahubNode(client=clients.standard, schema=corenode_schema)
        data = await node.generate_query_data(fragment=True)
    else:
        corenode_schema: GenericSchema = clients.sync.schema.get(kind="CoreNode")  # type: ignore[assignment]
        node = InfrahubNodeSync(client=clients.sync, schema=corenode_schema)
        data = node.generate_query_data(fragment=True)

    assert data == {
        "CoreNode": {
            "@filters": {},
            "count": None,
            "edges": {
                "node": {
                    "__typename": None,
                    "...on BuiltinLocation": {
                        "description": {
                            "@alias": "__alias__BuiltinLocation__description",
                            "value": None,
                        },
                        "name": {
                            "@alias": "__alias__BuiltinLocation__name",
                            "value": None,
                        },
                        "primary_tag": {
                            "@alias": "__alias__BuiltinLocation__primary_tag",
                            "node": {
                                "__typename": None,
                                "display_label": None,
                                "id": None,
                                "hfid": None,
                            },
                        },
                        "type": {
                            "@alias": "__alias__BuiltinLocation__type",
                            "value": None,
                        },
                    },
                    "...on BuiltinTag": {
                        "description": {
                            "@alias": "__alias__BuiltinTag__description",
                            "value": None,
                        },
                        "name": {
                            "@alias": "__alias__BuiltinTag__name",
                            "value": None,
                        },
                    },
                    "display_label": None,
                    "id": None,
                    "hfid": None,
                },
            },
        },
    }


@pytest.mark.parametrize("client_type", client_types)
async def test_query_data_include_property(
    client: InfrahubClient,
    client_sync: InfrahubClientSync,
    location_schema: NodeSchemaAPI,
    client_type: str,
) -> None:
    if client_type == "standard":
        await set_builtin_tag_schema_cache(client)
        node = InfrahubNode(client=client, schema=location_schema)
        data = await node.generate_query_data(include=["tags"], property=True)
    else:
        await set_builtin_tag_schema_cache(client_sync)
        node = InfrahubNodeSync(client=client_sync, schema=location_schema)
        data = node.generate_query_data(include=["tags"], property=True)

    assert data == {
        "BuiltinLocation": {
            "@filters": {},
            "count": None,
            "edges": {
                "node": {
                    "__typename": None,
                    "id": None,
                    "hfid": None,
                    "display_label": None,
                    "name": {
                        "is_default": None,
                        "is_from_profile": None,
                        "is_protected": None,
                        "owner": {
                            "__typename": None,
                            "display_label": None,
                            "id": None,
                        },
                        "source": {
                            "__typename": None,
                            "display_label": None,
                            "id": None,
                        },
                        "updated_at": None,
                        "value": None,
                    },
                    "description": {
                        "is_default": None,
                        "is_from_profile": None,
                        "is_protected": None,
                        "owner": {
                            "__typename": None,
                            "display_label": None,
                            "id": None,
                        },
                        "source": {
                            "__typename": None,
                            "display_label": None,
                            "id": None,
                        },
                        "updated_at": None,
                        "value": None,
                    },
                    "type": {
                        "is_default": None,
                        "is_from_profile": None,
                        "is_protected": None,
                        "owner": {
                            "__typename": None,
                            "display_label": None,
                            "id": None,
                        },
                        "source": {
                            "__typename": None,
                            "display_label": None,
                            "id": None,
                        },
                        "updated_at": None,
                        "value": None,
                    },
                    "primary_tag": {
                        "properties": {
                            "is_protected": None,
                            "owner": {
                                "__typename": None,
                                "display_label": None,
                                "id": None,
                            },
                            "source": {
                                "__typename": None,
                                "display_label": None,
                                "id": None,
                            },
                            "updated_at": None,
                        },
                        "node": {
                            "id": None,
                            "hfid": None,
                            "display_label": None,
                            "__typename": None,
                        },
                    },
                    "tags": {
                        "count": None,
                        "edges": {
                            "properties": {
                                "is_protected": None,
                                "owner": {
                                    "__typename": None,
                                    "display_label": None,
                                    "id": None,
                                },
                                "source": {
                                    "__typename": None,
                                    "display_label": None,
                                    "id": None,
                                },
                                "updated_at": None,
                            },
                            "node": {
                                "id": None,
                                "hfid": None,
                                "display_label": None,
                                "__typename": None,
                            },
                        },
                    },
                },
            },
        },
    }


@pytest.mark.parametrize("client_type", client_types)
async def test_query_data_include(
    client: InfrahubClient,
    client_sync: InfrahubClientSync,
    location_schema: NodeSchemaAPI,
    client_type: str,
) -> None:
    if client_type == "standard":
        await set_builtin_tag_schema_cache(client)
        node = InfrahubNode(client=client, schema=location_schema)
        data = await node.generate_query_data(include=["tags"])
    else:
        await set_builtin_tag_schema_cache(client_sync)
        node = InfrahubNodeSync(client=client_sync, schema=location_schema)
        data = node.generate_query_data(include=["tags"])

    assert data == {
        "BuiltinLocation": {
            "@filters": {},
            "count": None,
            "edges": {
                "node": {
                    "__typename": None,
                    "id": None,
                    "hfid": None,
                    "display_label": None,
                    "name": {
                        "value": None,
                    },
                    "description": {
                        "value": None,
                    },
                    "type": {
                        "value": None,
                    },
                    "primary_tag": {
                        "node": {
                            "id": None,
                            "hfid": None,
                            "display_label": None,
                            "__typename": None,
                        },
                    },
                    "tags": {
                        "count": None,
                        "edges": {
                            "node": {
                                "id": None,
                                "hfid": None,
                                "display_label": None,
                                "__typename": None,
                            },
                        },
                    },
                },
            },
        },
    }


@pytest.mark.parametrize("client_type", client_types)
async def test_query_data_exclude_property(
    client: InfrahubClient, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    if client_type == "standard":
        node = InfrahubNode(client=client, schema=location_schema)
        data = await node.generate_query_data(exclude=["description", "primary_tag"], property=True)
    else:
        node = InfrahubNodeSync(client=client, schema=location_schema)
        data = node.generate_query_data(exclude=["description", "primary_tag"], property=True)

    assert data == {
        "BuiltinLocation": {
            "@filters": {},
            "count": None,
            "edges": {
                "node": {
                    "__typename": None,
                    "id": None,
                    "hfid": None,
                    "display_label": None,
                    "name": {
                        "is_default": None,
                        "is_from_profile": None,
                        "is_protected": None,
                        "owner": {
                            "__typename": None,
                            "display_label": None,
                            "id": None,
                        },
                        "source": {
                            "__typename": None,
                            "display_label": None,
                            "id": None,
                        },
                        "updated_at": None,
                        "value": None,
                    },
                    "type": {
                        "is_default": None,
                        "is_from_profile": None,
                        "is_protected": None,
                        "owner": {
                            "__typename": None,
                            "display_label": None,
                            "id": None,
                        },
                        "source": {
                            "__typename": None,
                            "display_label": None,
                            "id": None,
                        },
                        "updated_at": None,
                        "value": None,
                    },
                },
            },
        },
    }


@pytest.mark.parametrize("client_type", client_types)
async def test_query_data_exclude(client: InfrahubClient, location_schema: NodeSchemaAPI, client_type: str) -> None:
    if client_type == "standard":
        node = InfrahubNode(client=client, schema=location_schema)
        data = await node.generate_query_data(exclude=["description", "primary_tag"])
    else:
        node = InfrahubNodeSync(client=client, schema=location_schema)
        data = node.generate_query_data(exclude=["description", "primary_tag"])

    assert data == {
        "BuiltinLocation": {
            "@filters": {},
            "count": None,
            "edges": {
                "node": {
                    "__typename": None,
                    "id": None,
                    "hfid": None,
                    "display_label": None,
                    "name": {
                        "value": None,
                    },
                    "type": {
                        "value": None,
                    },
                },
            },
        },
    }


@pytest.mark.parametrize("client_type", client_types)
async def test_create_input_data(client: InfrahubClient, location_schema: NodeSchemaAPI, client_type: str) -> None:
    data = {"name": {"value": "JFK1"}, "description": {"value": "JFK Airport"}, "type": {"value": "SITE"}}

    if client_type == "standard":
        node = InfrahubNode(client=client, schema=location_schema, data=data)
    else:
        node = InfrahubNodeSync(client=client, schema=location_schema, data=data)

    assert node._generate_input_data()["data"] == {
        "data": {
            "name": {"value": "JFK1"},
            "description": {"value": "JFK Airport"},
            "type": {"value": "SITE"},
        }
    }


@pytest.mark.parametrize("client_type", client_types)
async def test_create_input_data_with_dropdown(
    client: InfrahubClient, location_schema_with_dropdown: NodeSchemaAPI, client_type: str
) -> None:
    """Validate input data including dropdown field."""
    data = {
        "name": {"value": "JFK1"},
        "description": {"value": "JFK Airport"},
        "type": {"value": "SITE"},
        "status": {"value": "active"},
    }

    if client_type == "standard":
        node = InfrahubNode(client=client, schema=location_schema_with_dropdown, data=data)
    else:
        node = InfrahubNodeSync(client=client, schema=location_schema_with_dropdown, data=data)

    assert node.status.value == "active"
    node.status = None
    assert node._generate_input_data()["data"] == {
        "data": {
            "name": {"value": "JFK1"},
            "description": {"value": "JFK Airport"},
            "type": {"value": "SITE"},
            "status": {"value": None},
        }
    }


@pytest.mark.parametrize("client_type", client_types)
async def test_update_input_data_existing_node_with_optional_relationship(
    clients: BothClients, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    """An explicit `node.rel = None` on an existing node still clears the relationship."""
    data = {
        "id": "existing-node-id",
        "name": {"value": "JFK1"},
        "description": {"value": "JFK Airport"},
        "type": {"value": "SITE"},
    }

    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=location_schema, data=data)
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=location_schema, data=data)

    node.primary_tag = None

    assert node._generate_input_data()["data"] == {
        "data": {
            "id": "existing-node-id",
            "name": {"value": "JFK1"},
            "description": {"value": "JFK Airport"},
            "type": {"value": "SITE"},
            "primary_tag": None,
        }
    }


@pytest.mark.parametrize("client_type", client_types)
async def test_update_input_data_existing_node_preserves_untouched_optional_relationship(
    clients: BothClients, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    """A partial payload that omits an optional one-cardinality rel must NOT silently clear it on save."""
    data = {
        "id": "existing-node-id",
        "name": {"value": "JFK1"},
        "description": {"value": "JFK Airport"},
        "type": {"value": "SITE"},
    }

    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=location_schema, data=data)
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=location_schema, data=data)

    payload = node._generate_input_data()["data"]["data"]
    assert "primary_tag" not in payload


@pytest.mark.parametrize("client_type", client_types)
async def test_create_input_data__with_relationships_02(
    client: InfrahubClient, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    """Validate input data with variables that needs replacements."""
    data = {
        "name": {"value": "JFK1"},
        "description": {"value": "JFK\n Airport"},
        "type": {"value": "SITE"},
        "primary_tag": "pppppppp",
        "tags": [{"id": "aaaaaa"}, {"id": "bbbb"}],
    }

    if client_type == "standard":
        node = InfrahubNode(client=client, schema=location_schema, data=data)
    else:
        node = InfrahubNodeSync(client=client, schema=location_schema, data=data)

    input_data = node._generate_input_data()
    assert len(input_data["variables"].keys()) == 1
    key = next(iter(input_data["variables"].keys()))
    value = input_data["variables"][key]

    expected = {
        "data": {
            "name": {"value": "JFK1"},
            "description": {"value": f"${key}"},
            "type": {"value": "SITE"},
            "tags": [{"id": "aaaaaa"}, {"id": "bbbb"}],
            "primary_tag": {"id": "pppppppp"},
        }
    }
    assert input_data["data"] == expected
    assert value == "JFK\n Airport"


@pytest.mark.parametrize("client_type", client_types)
async def test_create_input_data__with_relationships_01(
    client: InfrahubClient, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    data = {
        "name": {"value": "JFK1"},
        "description": {"value": "JFK Airport"},
        "type": {"value": "SITE"},
        "primary_tag": "pppppppp",
        "tags": [{"id": "aaaaaa"}, {"id": "bbbb"}],
    }

    if client_type == "standard":
        node = InfrahubNode(client=client, schema=location_schema, data=data)
    else:
        node = InfrahubNodeSync(client=client, schema=location_schema, data=data)

    assert node._generate_input_data()["data"] == {
        "data": {
            "name": {"value": "JFK1"},
            "description": {"value": "JFK Airport"},
            "type": {"value": "SITE"},
            "tags": [{"id": "aaaaaa"}, {"id": "bbbb"}],
            "primary_tag": {"id": "pppppppp"},
        }
    }


@pytest.mark.parametrize("client_type", client_types)
async def test_create_input_data_with_relationships_02(
    clients: BothClients, rfile_schema: NodeSchemaAPI, client_type: str
) -> None:
    data = {
        "name": {"value": "rfile01", "is_protected": True, "source": "ffffffff", "owner": "ffffffff"},
        "template_path": {"value": "mytemplate.j2"},
        "query": {"id": "qqqqqqqq", "source": "ffffffff", "owner": "ffffffff"},
        "repository": {"id": "rrrrrrrr", "source": "ffffffff", "owner": "ffffffff"},
        "tags": [{"id": "t1t1t1t1"}, "t2t2t2t2"],
    }

    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=rfile_schema, data=data)
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=rfile_schema, data=data)

    assert node._generate_input_data()["data"] == {
        "data": {
            "name": {
                "is_protected": True,
                "owner": "ffffffff",
                "source": "ffffffff",
                "value": "rfile01",
            },
            "query": {
                "_relation__owner": "ffffffff",
                "_relation__source": "ffffffff",
                "id": "qqqqqqqq",
            },
            "tags": [{"id": "t1t1t1t1"}, {"id": "t2t2t2t2"}],
            "template_path": {"value": "mytemplate.j2"},
            "repository": {
                "_relation__owner": "ffffffff",
                "_relation__source": "ffffffff",
                "id": "rrrrrrrr",
            },
        }
    }


@pytest.mark.parametrize("client_type", client_types)
async def test_create_input_data_with_relationships_03(
    clients: BothClients, rfile_schema: NodeSchemaAPI, client_type: str
) -> None:
    data = {
        "name": {"value": "rfile01", "is_protected": True, "source": "ffffffff"},
        "template_path": {"value": "mytemplate.j2"},
        "query": {"id": "qqqqqqqq", "source": "ffffffff", "owner": "ffffffff", "is_protected": True},
        "repository": {"id": "rrrrrrrr", "source": "ffffffff", "owner": "ffffffff"},
        "tags": [{"id": "t1t1t1t1"}, "t2t2t2t2"],
    }

    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=rfile_schema, data=data)
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=rfile_schema, data=data)

    assert node._generate_input_data()["data"] == {
        "data": {
            "name": {"is_protected": True, "source": "ffffffff", "value": "rfile01"},
            "query": {
                "_relation__is_protected": True,
                "_relation__owner": "ffffffff",
                "_relation__source": "ffffffff",
                "id": "qqqqqqqq",
            },
            "tags": [{"id": "t1t1t1t1"}, {"id": "t2t2t2t2"}],
            "template_path": {"value": "mytemplate.j2"},
            "repository": {"_relation__owner": "ffffffff", "_relation__source": "ffffffff", "id": "rrrrrrrr"},
        }
    }


@pytest.mark.parametrize("property_test", property_tests)
@pytest.mark.parametrize("client_type", client_types)
async def test_create_input_data_with_relationships_03_for_update_include_unmodified(
    clients: BothClients,
    rfile_schema: NodeSchemaAPI,
    rfile_userdata01: dict[str, Any],
    rfile_userdata01_property: dict[str, Any],
    client_type: str,
    property_test: str,
) -> None:
    rfile_userdata = rfile_userdata01 if property_test == WITHOUT_PROPERTY else rfile_userdata01_property

    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=rfile_schema, data=rfile_userdata)
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=rfile_schema, data=rfile_userdata)

    node.template_path.value = "my-changed-template.j2"

    expected_result_with_property = {
        "data": {
            "name": {
                "is_protected": True,
                "source": "ffffffff",
                "value": "rfile01",
            },
            "query": {
                "id": "qqqqqqqq",
                "_relation__is_protected": True,
                "_relation__owner": "ffffffff",
                "_relation__source": "ffffffff",
            },
            "tags": [{"id": "t1t1t1t1"}, {"id": "t2t2t2t2"}],
            "template_path": {"value": "my-changed-template.j2"},
            "repository": {"id": "rrrrrrrr", "_relation__owner": "ffffffff", "_relation__source": "ffffffff"},
        }
    }

    expected_result_without_property = {
        "data": {
            "name": {
                "value": "rfile01",
            },
            "query": {
                "id": "qqqqqqqq",
            },
            "tags": [{"id": "t1t1t1t1"}, {"id": "t2t2t2t2"}],
            "template_path": {"value": "my-changed-template.j2"},
            "repository": {"id": "rrrrrrrr"},
        }
    }

    expected_result = (
        expected_result_without_property if property_test == WITHOUT_PROPERTY else expected_result_with_property
    )
    assert node._generate_input_data(exclude_unmodified=False)["data"] == expected_result


@pytest.mark.parametrize("property_test", property_tests)
@pytest.mark.parametrize("client_type", client_types)
async def test_create_input_data_with_relationships_03_for_update_exclude_unmodified(
    clients: BothClients,
    rfile_schema: NodeSchemaAPI,
    rfile_userdata01: dict[str, Any],
    rfile_userdata01_property: dict[str, Any],
    client_type: str,
    property_test: str,
) -> None:
    """NOTE: Need to fix this test, the issue is tracked in https://github.com/opsmill/infrahub-sdk-python/issues/214."""
    rfile_userdata = rfile_userdata01 if property_test == WITHOUT_PROPERTY else rfile_userdata01_property

    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=rfile_schema, data=rfile_userdata)
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=rfile_schema, data=rfile_userdata)

    node.template_path.value = "my-changed-template.j2"
    expected_result_with_property = {
        "data": {
            "query": {
                "id": "qqqqqqqq",
                "_relation__is_protected": True,
                "_relation__owner": "ffffffff",
                "_relation__source": "ffffffff",
            },
            "template_path": {"value": "my-changed-template.j2"},
            "repository": {"id": "rrrrrrrr", "_relation__owner": "ffffffff", "_relation__source": "ffffffff"},
        }
    }

    expected_result_without_property = {
        "data": {
            "template_path": {"value": "my-changed-template.j2"},
        }
    }

    expected_result = (
        expected_result_without_property if property_test == WITHOUT_PROPERTY else expected_result_with_property
    )

    assert node._generate_input_data(exclude_unmodified=True)["data"] == expected_result


@pytest.mark.parametrize("client_type", client_types)
async def test_create_input_data_with_IPHost_attribute(
    client: InfrahubClient, ipaddress_schema: NodeSchemaAPI, client_type: str
) -> None:
    data = {"address": {"value": ipaddress.ip_interface("1.1.1.1/24"), "is_protected": True}}

    if client_type == "standard":
        ip_address = InfrahubNode(client=client, schema=ipaddress_schema, data=data)
    else:
        ip_address = InfrahubNodeSync(client=client, schema=ipaddress_schema, data=data)

    assert ip_address._generate_input_data()["data"] == {
        "data": {"address": {"value": "1.1.1.1/24", "is_protected": True}}
    }


@pytest.mark.parametrize("client_type", client_types)
async def test_create_input_data_with_IPAddress_attribute(
    client: InfrahubClient, bare_ipaddress_schema: NodeSchemaAPI, client_type: str
) -> None:
    data = {"address": {"value": ipaddress.ip_address("1.1.1.1"), "is_protected": True}}

    if client_type == "standard":
        dns_record = InfrahubNode(client=client, schema=bare_ipaddress_schema, data=data)
    else:
        dns_record = InfrahubNodeSync(client=client, schema=bare_ipaddress_schema, data=data)

    # a bare address is serialized without any prefix
    assert dns_record._generate_input_data()["data"] == {
        "data": {"address": {"value": "1.1.1.1", "is_protected": True}}
    }


@pytest.mark.parametrize("client_type", client_types)
async def test_create_input_data_with_IPNetwork_attribute(
    client: InfrahubClient, ipnetwork_schema: NodeSchemaAPI, client_type: str
) -> None:
    data = {"network": {"value": ipaddress.ip_network("1.1.1.0/24"), "is_protected": True}}

    if client_type == "standard":
        ip_network = InfrahubNode(client=client, schema=ipnetwork_schema, data=data)
    else:
        ip_network = InfrahubNodeSync(client=client, schema=ipnetwork_schema, data=data)

    assert ip_network._generate_input_data()["data"] == {
        "data": {"network": {"value": "1.1.1.0/24", "is_protected": True}}
    }


@pytest.mark.parametrize("property_test", property_tests)
@pytest.mark.parametrize("client_type", client_types)
async def test_update_input_data__with_relationships_01(
    client: InfrahubClient,
    location_schema: NodeSchemaAPI,
    location_data01: dict[str, Any],
    location_data01_property: dict[str, Any],
    tag_schema: NodeSchemaAPI,
    tag_blue_data: dict[str, Any],
    tag_green_data: dict[str, Any],
    tag_red_data: dict[str, Any],
    client_type: str,
    property_test: str,
) -> None:
    location_data = location_data01 if property_test == WITHOUT_PROPERTY else location_data01_property

    if client_type == "standard":
        location = InfrahubNode(client=client, schema=location_schema, data=location_data)
        tag_green = InfrahubNode(client=client, schema=tag_schema, data=tag_green_data)
        tag_blue = InfrahubNode(client=client, schema=tag_schema, data=tag_blue_data)
        tag_red = InfrahubNode(client=client, schema=tag_schema, data=tag_red_data)
    else:
        location = InfrahubNodeSync(client=client, schema=location_schema, data=location_data)
        tag_green = InfrahubNodeSync(client=client, schema=tag_schema, data=tag_green_data)
        tag_blue = InfrahubNodeSync(client=client, schema=tag_schema, data=tag_blue_data)
        tag_red = InfrahubNodeSync(client=client, schema=tag_schema, data=tag_red_data)

    location.primary_tag = tag_green_data
    location.tags.extend([tag_green, tag_red])
    location.tags.remove(tag_blue)

    expected_result_without_property = {
        "data": {
            "id": "llllllll-llll-llll-llll-llllllllllll",
            "name": {"value": "DFW"},
            "primary_tag": {"id": "gggggggg-gggg-gggg-gggg-gggggggggggg"},
            "tags": [{"id": "gggggggg-gggg-gggg-gggg-gggggggggggg"}, {"id": "rrrrrrrr-rrrr-rrrr-rrrr-rrrrrrrrrrrr"}],
            "type": {"value": "SITE"},
        },
    }
    expected_result_with_property = {
        "data": {
            "id": "llllllll-llll-llll-llll-llllllllllll",
            "name": {
                "is_protected": True,
                "value": "DFW",
                "updated_at": "2024-01-15T10:30:00.000000Z",
            },
            "primary_tag": {"id": "gggggggg-gggg-gggg-gggg-gggggggggggg"},
            "tags": [{"id": "gggggggg-gggg-gggg-gggg-gggggggggggg"}, {"id": "rrrrrrrr-rrrr-rrrr-rrrr-rrrrrrrrrrrr"}],
            "type": {
                "is_protected": True,
                "value": "SITE",
                "updated_at": "2024-01-15T10:30:00.000000Z",
            },
        },
    }

    expected_data = (
        expected_result_without_property if property_test == WITHOUT_PROPERTY else expected_result_with_property
    )
    assert location._generate_input_data()["data"] == expected_data


@pytest.mark.parametrize("property_test", property_tests)
@pytest.mark.parametrize("client_type", client_types)
async def test_update_input_data_with_relationships_02(
    client: InfrahubClient,
    location_schema: NodeSchemaAPI,
    location_data02: dict[str, Any],
    location_data02_property: dict[str, Any],
    client_type: str,
    property_test: str,
) -> None:
    location_data = location_data02 if property_test == WITHOUT_PROPERTY else location_data02_property

    if client_type == "standard":
        location = InfrahubNode(client=client, schema=location_schema, data=location_data)
    else:
        location = InfrahubNodeSync(client=client, schema=location_schema, data=location_data)

    expected_result_without_property = {
        "data": {
            "id": "llllllll-llll-llll-llll-llllllllllll",
            "name": {
                "value": "dfw1",
            },
            "primary_tag": {
                "id": "rrrrrrrr-rrrr-rrrr-rrrr-rrrrrrrrrrrr",
            },
            "tags": [
                {
                    "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                },
            ],
            "type": {
                "value": "SITE",
            },
        },
    }

    expected_result_with_property = {
        "data": {
            "id": "llllllll-llll-llll-llll-llllllllllll",
            "name": {
                "is_protected": True,
                "source": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                "value": "dfw1",
                "updated_at": "2024-01-15T10:30:00.000000Z",
            },
            "primary_tag": {
                "_relation__updated_at": "2024-01-15T10:30:00.000000Z",
                "_relation__is_protected": True,
                "_relation__source": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                "id": "rrrrrrrr-rrrr-rrrr-rrrr-rrrrrrrrrrrr",
            },
            "tags": [
                {
                    "_relation__updated_at": "2024-01-15T10:30:00.000000Z",
                    "_relation__is_protected": True,
                    "_relation__source": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                    "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                },
            ],
            "type": {
                "is_protected": True,
                "source": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                "value": "SITE",
                "updated_at": "2024-01-15T10:30:00.000000Z",
            },
        },
    }

    expected_result = (
        expected_result_without_property if property_test == WITHOUT_PROPERTY else expected_result_with_property
    )

    assert location._generate_input_data()["data"] == expected_result


@pytest.mark.parametrize("property_test", property_tests)
@pytest.mark.parametrize("client_type", client_types)
async def test_update_input_data_with_relationships_02_exclude_unmodified(
    client: InfrahubClient,
    location_schema: NodeSchemaAPI,
    location_data02: dict[str, Any],
    location_data02_property: dict[str, Any],
    client_type: str,
    property_test: str,
) -> None:
    """NOTE Need to fix this test, issue is tracked in https://github.com/opsmill/infrahub-sdk-python/issues/214."""
    location_data = location_data02 if property_test == WITHOUT_PROPERTY else location_data02_property

    if client_type == "standard":
        location = InfrahubNode(client=client, schema=location_schema, data=location_data)
    else:
        location = InfrahubNodeSync(client=client, schema=location_schema, data=location_data)

    expected_result_without_property = {
        "data": {
            "id": "llllllll-llll-llll-llll-llllllllllll",
        },
    }

    expected_result_with_property = {
        "data": {
            "id": "llllllll-llll-llll-llll-llllllllllll",
            "primary_tag": {
                "_relation__is_protected": True,
                "_relation__source": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                "_relation__updated_at": "2024-01-15T10:30:00.000000Z",
                "id": "rrrrrrrr-rrrr-rrrr-rrrr-rrrrrrrrrrrr",
            },
        },
    }

    expected_result = (
        expected_result_without_property if property_test == WITHOUT_PROPERTY else expected_result_with_property
    )

    assert location._generate_input_data(exclude_unmodified=True)["data"] == expected_result


@pytest.mark.parametrize("property_test", property_tests)
@pytest.mark.parametrize("client_type", client_types)
async def test_update_input_data_empty_relationship(
    client: InfrahubClient,
    location_schema: NodeSchemaAPI,
    location_data01: dict[str, Any],
    location_data01_property: dict[str, Any],
    tag_schema: NodeSchemaAPI,
    tag_blue_data: dict[str, Any],
    client_type: str,
    property_test: str,
) -> None:
    """TODO: investigate why name and type are being returned since they haven't been modified."""
    location_data = location_data01 if property_test == WITHOUT_PROPERTY else location_data01_property

    if client_type == "standard":
        location = InfrahubNode(client=client, schema=location_schema, data=location_data)
        tag_blue = InfrahubNode(client=client, schema=tag_schema, data=tag_blue_data)
    else:
        location = InfrahubNodeSync(client=client, schema=location_schema, data=location_data)
        tag_blue = InfrahubNode(client=client, schema=tag_schema, data=tag_blue_data)

    location.tags.remove(tag_blue)
    location.primary_tag = None

    expected_result_without_property = {
        "data": {
            "id": "llllllll-llll-llll-llll-llllllllllll",
            "name": {"value": "DFW"},
            "primary_tag": None,
            "tags": [],
            "type": {"value": "SITE"},
        },
    }
    expected_result_with_property = {
        "data": {
            "id": "llllllll-llll-llll-llll-llllllllllll",
            "name": {
                "is_protected": True,
                "value": "DFW",
                "updated_at": "2024-01-15T10:30:00.000000Z",
            },
            "primary_tag": None,
            "tags": [],
            "type": {
                "is_protected": True,
                "value": "SITE",
                "updated_at": "2024-01-15T10:30:00.000000Z",
            },
        },
    }

    expected_data = (
        expected_result_without_property if property_test == WITHOUT_PROPERTY else expected_result_with_property
    )
    assert location._generate_input_data()["data"] == expected_data


@pytest.mark.parametrize("client_type", client_types)
async def test_node_get_relationship_from_store(
    client: InfrahubClient,
    location_schema: NodeSchemaAPI,
    location_data01: dict[str, Any],
    tag_schema: NodeSchemaAPI,
    tag_red_data: dict[str, Any],
    tag_blue_data: dict[str, Any],
    client_type: str,
) -> None:
    if client_type == "standard":
        node = InfrahubNode(client=client, schema=location_schema, data=location_data01)
        tag_red = InfrahubNode(client=client, schema=tag_schema, data=tag_red_data)
        tag_blue = InfrahubNode(client=client, schema=tag_schema, data=tag_blue_data)
    else:
        node = InfrahubNodeSync(client=client, schema=location_schema, data=location_data01)
        tag_red = InfrahubNodeSync(client=client, schema=tag_schema, data=tag_red_data)
        tag_blue = InfrahubNodeSync(client=client, schema=tag_schema, data=tag_blue_data)

    client.store.set(node=tag_red)
    client.store.set(node=tag_blue)

    assert node.primary_tag.peer == tag_red
    assert node.primary_tag.get() == tag_red

    assert node.tags[0].peer == tag_blue
    assert [tag.peer for tag in node.tags] == [tag_blue]


@pytest.mark.parametrize("client_type", client_types)
async def test_node_get_relationship_not_in_store(
    client: InfrahubClient, location_schema: NodeSchemaAPI, location_data01: dict[str, Any], client_type: str
) -> None:
    if client_type == "standard":
        node = InfrahubNode(client=client, schema=location_schema, data=location_data01)
    else:
        node = InfrahubNodeSync(client=client, schema=location_schema, data=location_data01)

    with pytest.raises(NodeNotFoundError):
        _ = node.primary_tag.peer

    with pytest.raises(NodeNotFoundError):
        _ = node.tags[0].peer


@pytest.mark.parametrize("client_type", client_types)
async def test_node_fetch_relationship(
    httpx_mock: HTTPXMock,
    mock_schema_query_01: HTTPXMock,
    clients: BothClients,
    location_schema: NodeSchemaAPI,
    location_data01: dict[str, Any],
    tag_schema: NodeSchemaAPI,
    tag_red_data: dict[str, Any],
    tag_blue_data: dict[str, Any],
    client_type: str,
) -> None:
    response1 = {
        "data": {
            "BuiltinTag": {
                "count": 1,
                "edges": [
                    tag_red_data,
                ],
            }
        }
    }

    httpx_mock.add_response(
        method="POST",
        json=response1,
        match_headers={"X-Infrahub-Tracker": "query-builtintag-page1"},
    )

    response2 = {
        "data": {
            "BuiltinTag": {
                "count": 1,
            }
        }
    }

    httpx_mock.add_response(
        method="POST",
        json=response2,
    )

    response3 = {
        "data": {
            "BuiltinTag": {
                "count": 1,
                "edges": [
                    tag_blue_data,
                ],
            }
        }
    }

    httpx_mock.add_response(
        method="POST",
        json=response3,
        match_headers={"X-Infrahub-Tracker": "query-builtintag-page1"},
    )

    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=location_schema, data=location_data01)
        await node.primary_tag.fetch()  # type: ignore[attr-defined]
        await node.tags.fetch()  # type: ignore[attr-defined]
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=location_schema, data=location_data01)  # type: ignore[assignment]
        node.primary_tag.fetch()  # type: ignore[attr-defined]
        node.tags.fetch()  # type: ignore[attr-defined]

    assert isinstance(node.primary_tag.peer, InfrahubNodeBase)  # type: ignore[attr-defined]
    assert isinstance(node.tags[0].peer, InfrahubNodeBase)  # type: ignore[attr-defined]


@pytest.mark.parametrize("client_type", client_types)
async def test_node_IPHost_deserialization(
    client: InfrahubClient, ipaddress_schema: NodeSchemaAPI, client_type: str
) -> None:
    data = {
        "id": "aaaaaaaaaaaaaa",
        "address": {
            "value": "1.1.1.1/24",
            "is_protected": True,
        },
    }
    if client_type == "standard":
        ip_address = InfrahubNode(client=client, schema=ipaddress_schema, data=data)
    else:
        ip_address = InfrahubNodeSync(client=client, schema=ipaddress_schema, data=data)

    assert ip_address.address.value == ipaddress.ip_interface("1.1.1.1/24")


@pytest.mark.parametrize("client_type", client_types)
async def test_node_IPAddress_deserialization(
    client: InfrahubClient, bare_ipaddress_schema: NodeSchemaAPI, client_type: str
) -> None:
    data = {
        "id": "aaaaaaaaaaaaaa",
        "address": {
            "value": "1.1.1.1",
            "is_protected": True,
        },
    }
    if client_type == "standard":
        dns_record = InfrahubNode(client=client, schema=bare_ipaddress_schema, data=data)
    else:
        dns_record = InfrahubNodeSync(client=client, schema=bare_ipaddress_schema, data=data)

    # a bare address deserializes to an ip_address object (no prefix)
    assert dns_record.address.value == ipaddress.ip_address("1.1.1.1")


@pytest.mark.parametrize("client_type", client_types)
async def test_node_IPNetwork_deserialization(
    client: InfrahubClient, ipnetwork_schema: NodeSchemaAPI, client_type: str
) -> None:
    data = {
        "id": "aaaaaaaaaaaaaa",
        "network": {
            "value": "1.1.1.0/24",
            "is_protected": True,
        },
    }
    if client_type == "standard":
        ip_network = InfrahubNode(client=client, schema=ipnetwork_schema, data=data)
    else:
        ip_network = InfrahubNodeSync(client=client, schema=ipnetwork_schema, data=data)

    assert ip_network.network.value == ipaddress.ip_network("1.1.1.0/24")


@pytest.mark.parametrize("client_type", client_types)
async def test_get_flat_value(
    httpx_mock: HTTPXMock,
    mock_schema_query_01: HTTPXMock,
    clients: BothClients,
    location_schema: NodeSchemaAPI,
    location_data01: dict[str, Any],
    client_type: str,
) -> None:
    httpx_mock.add_response(
        method="POST",
        json={"data": {"BuiltinTag": {"count": 1, "edges": [location_data01["node"]["primary_tag"]]}}},
        match_headers={"X-Infrahub-Tracker": "query-builtintag-page1"},
        is_reusable=True,
    )

    if client_type == "standard":
        tag = InfrahubNode(client=clients.standard, schema=location_schema, data=location_data01)
        assert await tag.get_flat_value(key="name__value") == "DFW"
        assert await tag.get_flat_value(key="primary_tag__display_label") == "red"
        assert await tag.get_flat_value(key="primary_tag.display_label", separator=".") == "red"

        with pytest.raises(ValueError, match="Can only look up flat value for relationships of cardinality one"):
            assert await tag.get_flat_value(key="tags__display_label") == "red"
    else:
        tag = InfrahubNodeSync(client=clients.sync, schema=location_schema, data=location_data01)
        assert tag.get_flat_value(key="name__value") == "DFW"
        assert tag.get_flat_value(key="primary_tag__display_label") == "red"
        assert tag.get_flat_value(key="primary_tag.display_label", separator=".") == "red"

        with pytest.raises(ValueError, match="Can only look up flat value for relationships of cardinality one"):
            assert tag.get_flat_value(key="tags__display_label") == "red"


@pytest.mark.parametrize("client_type", client_types)
async def test_node_extract(
    clients: BothClients, location_schema: NodeSchemaAPI, location_data01: dict[str, Any], client_type: str
) -> None:
    params = {"identifier": "id", "name": "name__value", "description": "description__value"}
    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=location_schema, data=location_data01)
        assert await node.extract(params=params) == {
            "description": None,
            "identifier": "llllllll-llll-llll-llll-llllllllllll",
            "name": "DFW",
        }

    else:
        node = InfrahubNodeSync(client=clients.sync, schema=location_schema, data=location_data01)
        assert node.extract(params=params) == {
            "description": None,
            "identifier": "llllllll-llll-llll-llll-llllllllllll",
            "name": "DFW",
        }


@pytest.mark.parametrize("client_type", client_types)
async def test_read_only_attr(
    client: InfrahubClient,
    address_schema: NodeSchemaAPI,
    address_data: dict[str, Any],
    client_type: str,
) -> None:
    if client_type == "standard":
        address = InfrahubNode(client=client, schema=address_schema, data=address_data)
    else:
        address = InfrahubNodeSync(client=client, schema=address_schema, data=address_data)

    assert address._generate_input_data()["data"] == {
        "data": {
            "id": "d5994b18-b25e-4261-9e63-17c2844a0b45",
            "street_number": {"is_protected": False, "value": "1234"},
            "street_name": {"is_protected": False, "value": "Fake Street"},
            "postal_code": {"is_protected": False, "value": "123ABC"},
        },
    }
    assert address.computed_address.value == "1234 Fake Street 123ABC"


@pytest.mark.parametrize("client_type", client_types)
async def test_relationships_excluded_input_data(
    client: InfrahubClient, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    data = {
        "name": {"value": "JFK1"},
        "description": {"value": "JFK Airport"},
        "type": {"value": "SITE"},
        "primary_tag": "pppppppp",
        "tags": [{"id": "aaaaaa"}, {"id": "bbbb"}],
    }
    if client_type == "standard":
        node = InfrahubNode(client=client, schema=location_schema, data=data)
    else:
        node = InfrahubNodeSync(client=client, schema=location_schema, data=data)

    assert node.tags.has_update is False


@pytest.mark.parametrize("client_type", client_types)
async def test_from_graphql(
    clients: BothClients, mock_schema_query_01: HTTPXMock, location_data01: dict[str, Any], client_type: str
) -> None:
    if client_type == "standard":
        schema = await clients.standard.schema.get(kind="BuiltinLocation", branch="main")
        node = await InfrahubNode.from_graphql(
            client=clients.standard, schema=schema, branch="main", data=location_data01
        )
    else:
        schema = clients.sync.schema.get(kind="BuiltinLocation", branch="main")
        node = InfrahubNodeSync.from_graphql(client=clients.sync, schema=schema, branch="main", data=location_data01)

    assert node.id == "llllllll-llll-llll-llll-llllllllllll"


@pytest.mark.parametrize("client_type", client_types)
async def test_process_relationships_recursive_deep_nesting(
    clients: BothClients,
    nested_device_with_interfaces_schema: NodeSchemaAPI,
    client_type: str,
) -> None:
    """Test that _process_relationships with recursive=True processes deeply nested relationships.

    This test validates 3-level deep nesting:
    Device -> Interfaces (many) -> IP Addresses (many)

    With recursive=False, only level 1 (interfaces) should be processed.
    With recursive=True, all 3 levels (device, interfaces, ip_addresses) should be processed.
    """
    nested_device_data = {
        "node": {
            "id": "device-1",
            "__typename": "InfraDevice",
            "display_label": "atl1-edge1",
            "name": {"value": "atl1-edge1"},
            "description": {"value": "Edge device in Atlanta"},
            "interfaces": {
                "edges": [
                    {
                        "node": {
                            "id": "interface-1",
                            "__typename": "InfraInterfaceL3",
                            "display_label": "Ethernet1",
                            "name": {"value": "Ethernet1"},
                            "description": {"value": "Primary interface"},
                            "ip_addresses": {
                                "edges": [
                                    {
                                        "node": {
                                            "id": "ip-1",
                                            "__typename": "InfraIPAddress",
                                            "display_label": "10.0.0.1/24",
                                            "address": {"value": "10.0.0.1/24"},
                                        }
                                    },
                                    {
                                        "node": {
                                            "id": "ip-2",
                                            "__typename": "InfraIPAddress",
                                            "display_label": "10.0.0.2/24",
                                            "address": {"value": "10.0.0.2/24"},
                                        }
                                    },
                                ]
                            },
                        }
                    },
                    {
                        "node": {
                            "id": "interface-2",
                            "__typename": "InfraInterfaceL3",
                            "display_label": "Ethernet2",
                            "name": {"value": "Ethernet2"},
                            "description": {"value": "Secondary interface"},
                            "ip_addresses": {
                                "edges": [
                                    {
                                        "node": {
                                            "id": "ip-3",
                                            "__typename": "InfraIPAddress",
                                            "display_label": "10.0.1.1/24",
                                            "address": {"value": "10.0.1.1/24"},
                                        }
                                    }
                                ]
                            },
                        }
                    },
                ]
            },
        }
    }
    schema_data = {
        "version": "1.0",
        "nodes": [
            # Convert the schema objects back to dictionaries
            {
                "name": "Device",
                "namespace": "Infra",
                "attributes": [{"name": "name", "kind": "Text"}],
                "relationships": [
                    {
                        "name": "interfaces",
                        "peer": "InfraInterfaceL3",
                        "cardinality": "many",
                        "optional": True,
                    }
                ],
            },
            {
                "name": "InterfaceL3",
                "namespace": "Infra",
                "attributes": [{"name": "name", "kind": "Text"}],
                "relationships": [
                    {
                        "name": "ip_addresses",
                        "peer": "InfraIPAddress",
                        "cardinality": "many",
                        "optional": True,
                    }
                ],
            },
            {
                "name": "IPAddress",
                "namespace": "Infra",
                "attributes": [{"name": "address", "kind": "IPHost"}],
                "relationships": [],
            },
        ],
    }

    # Set up schemas in the client cache to enable schema lookups
    if client_type == "standard":
        # Create a properly structured schema response with all three schemas

        clients.standard.schema.set_cache(schema_data, branch="main")

        # Test with recursive=False - should only process interfaces (level 1)
        device_node = await InfrahubNode.from_graphql(
            client=clients.standard,
            schema=nested_device_with_interfaces_schema,
            branch="main",
            data=nested_device_data,
        )
        related_nodes_non_recursive_async: list[InfrahubNode] = []
        await device_node._process_relationships(
            node_data=nested_device_data,
            branch="main",
            related_nodes=related_nodes_non_recursive_async,
            recursive=False,
        )
        related_nodes_non_recursive = related_nodes_non_recursive_async

        # Test with recursive=True - should process all levels
        device_node_recursive = await InfrahubNode.from_graphql(
            client=clients.standard,
            schema=nested_device_with_interfaces_schema,
            branch="main",
            data=nested_device_data,
        )
        related_nodes_recursive_async: list[InfrahubNode] = []
        await device_node_recursive._process_relationships(
            node_data=nested_device_data,
            branch="main",
            related_nodes=related_nodes_recursive_async,
            recursive=True,
        )
        related_nodes_recursive = related_nodes_recursive_async

    else:
        # Sync client test
        clients.sync.schema.set_cache(schema_data, branch="main")

        # Test with recursive=False
        device_node = InfrahubNodeSync.from_graphql(
            client=clients.sync,
            schema=nested_device_with_interfaces_schema,
            branch="main",
            data=nested_device_data,
        )
        related_nodes_non_recursive_sync: list[InfrahubNodeSync] = []
        device_node._process_relationships(
            node_data=nested_device_data,
            branch="main",
            related_nodes=related_nodes_non_recursive_sync,
            recursive=False,
        )
        related_nodes_non_recursive = related_nodes_non_recursive_sync

        # Test with recursive=True
        device_node_recursive = InfrahubNodeSync.from_graphql(
            client=clients.sync,
            schema=nested_device_with_interfaces_schema,
            branch="main",
            data=nested_device_data,
        )
        related_nodes_recursive_sync: list[InfrahubNodeSync] = []
        device_node_recursive._process_relationships(
            node_data=nested_device_data,
            branch="main",
            related_nodes=related_nodes_recursive_sync,
            recursive=True,
        )

        related_nodes_recursive = related_nodes_recursive_sync

    # With recursive=False, should only process the 2 interfaces (level 1)
    # IP addresses (level 2) should NOT be processed
    non_recursive_ids = {rn.id for rn in related_nodes_non_recursive}
    assert "interface-1" in non_recursive_ids
    assert "interface-2" in non_recursive_ids
    # IP addresses should NOT be in the list when recursive=False
    assert "ip-1" not in non_recursive_ids
    assert "ip-2" not in non_recursive_ids
    assert "ip-3" not in non_recursive_ids
    assert len(related_nodes_non_recursive) == 2  # Only 2 interfaces

    # With recursive=True, should process interfaces AND their IP addresses
    recursive_ids = {rn.id for rn in related_nodes_recursive}
    assert "interface-1" in recursive_ids
    assert "interface-2" in recursive_ids
    assert "ip-1" in recursive_ids  # From interface-1
    assert "ip-2" in recursive_ids  # From interface-1
    assert "ip-3" in recursive_ids  # From interface-2
    assert len(related_nodes_recursive) == 5  # 2 interfaces + 3 IP addresses


class TestRelatedNodeIsFromProfile:
    def test_is_from_profile_when_source_is_profile(self, location_schema: NodeSchemaAPI) -> None:
        data = {
            "node": {"id": "test-id", "display_label": "test-tag", "__typename": "BuiltinTag"},
            "properties": {
                "is_protected": False,
                "owner": None,
                "source": {"__typename": "ProfileInfraDevice", "display_label": "default-profile", "id": "profile-id"},
            },
        }
        related_node = RelatedNodeBase(branch="main", schema=location_schema.relationships[0], data=data)
        assert related_node.is_from_profile

    def test_is_from_profile_when_source_is_not_profile(self, location_schema: NodeSchemaAPI) -> None:
        data = {
            "node": {"id": "test-id", "display_label": "test-tag", "__typename": "BuiltinTag"},
            "properties": {
                "is_protected": False,
                "owner": None,
                "source": {"__typename": "CoreAccount", "display_label": "admin", "id": "account-id"},
            },
        }
        related_node = RelatedNodeBase(branch="main", schema=location_schema.relationships[0], data=data)
        assert not related_node.is_from_profile

    def test_is_from_profile_when_source_not_queried(self, location_schema: NodeSchemaAPI) -> None:
        data = {
            "node": {"id": "test-id", "display_label": "test-tag", "__typename": "BuiltinTag"},
            "properties": {"is_protected": False, "owner": None, "source": None},
        }
        related_node = RelatedNodeBase(branch="main", schema=location_schema.relationships[0], data=data)
        assert not related_node.is_from_profile

    def test_is_from_profile_when_no_properties(self, location_schema: NodeSchemaAPI) -> None:
        data = {"node": {"id": "test-id", "display_label": "test-tag", "__typename": "BuiltinTag"}}
        related_node = RelatedNodeBase(branch="main", schema=location_schema.relationships[0], data=data)
        assert not related_node.is_from_profile


class TestRelationshipManagerIsFromProfile:
    def test_is_from_profile_when_no_peers(self, location_schema: NodeSchemaAPI) -> None:
        manager = RelationshipManagerBase(name="tags", branch="main", schema=location_schema.relationships[0])
        assert not manager.is_from_profile

    def test_is_from_profile_when_all_peers_from_profile(
        self, client: InfrahubClient, location_schema: NodeSchemaAPI
    ) -> None:
        data = {
            "count": 2,
            "edges": [
                {
                    "node": {"id": "tag-1", "display_label": "tag1", "__typename": "BuiltinTag"},
                    "properties": {
                        "is_protected": False,
                        "owner": None,
                        "source": {"__typename": "ProfileInfraDevice", "display_label": "profile1", "id": "profile-1"},
                    },
                },
                {
                    "node": {"id": "tag-2", "display_label": "tag2", "__typename": "BuiltinTag"},
                    "properties": {
                        "is_protected": False,
                        "owner": None,
                        "source": {"__typename": "ProfileInfraDevice", "display_label": "profile1", "id": "profile-1"},
                    },
                },
            ],
        }
        manager = RelationshipManager(
            name="tags", client=client, node=None, branch="main", schema=location_schema.relationships[0], data=data
        )
        assert manager.is_from_profile

    def test_is_from_profile_when_any_peer_not_from_profile(
        self, client: InfrahubClient, location_schema: NodeSchemaAPI
    ) -> None:
        data = {
            "count": 2,
            "edges": [
                {
                    "node": {"id": "tag-1", "display_label": "tag1", "__typename": "BuiltinTag"},
                    "properties": {
                        "is_protected": False,
                        "owner": None,
                        "source": {"__typename": "ProfileInfraDevice", "display_label": "profile1", "id": "profile-1"},
                    },
                },
                {
                    "node": {"id": "tag-2", "display_label": "tag2", "__typename": "BuiltinTag"},
                    "properties": {
                        "is_protected": False,
                        "owner": None,
                        "source": {"__typename": "CoreAccount", "display_label": "admin", "id": "account-1"},
                    },
                },
            ],
        }
        manager = RelationshipManager(
            name="tags", client=client, node=None, branch="main", schema=location_schema.relationships[0], data=data
        )
        assert not manager.is_from_profile

    def test_is_from_profile_when_any_peer_has_unknown_source(
        self, client: InfrahubClient, location_schema: NodeSchemaAPI
    ) -> None:
        data = {
            "count": 2,
            "edges": [
                {
                    "node": {"id": "tag-1", "display_label": "tag1", "__typename": "BuiltinTag"},
                    "properties": {
                        "is_protected": False,
                        "owner": None,
                        "source": {"__typename": "ProfileInfraDevice", "display_label": "profile1", "id": "profile-1"},
                    },
                },
                {
                    "node": {"id": "tag-2", "display_label": "tag2", "__typename": "BuiltinTag"},
                    "properties": {"is_protected": False, "owner": None, "source": None},
                },
            ],
        }
        manager = RelationshipManager(
            name="tags", client=client, node=None, branch="main", schema=location_schema.relationships[0], data=data
        )
        assert not manager.is_from_profile


def test_node_property_repr_with_dict_data() -> None:
    data = {"id": "account-123", "display_label": "Admin User", "__typename": "CoreAccount"}
    prop = NodeProperty(data)
    result = repr(prop)
    assert result == "NodeProperty({'id': 'account-123', 'display_label': 'Admin User', '__typename': 'CoreAccount'})"


def test_node_metadata_repr_with_full_data() -> None:
    data = {
        "created_at": "2024-01-15T10:30:00Z",
        "created_by": {"id": "account-1", "display_label": "Admin", "__typename": "CoreAccount"},
        "updated_at": "2024-01-16T14:45:00Z",
        "updated_by": {"id": "account-2", "display_label": "Editor", "__typename": "CoreAccount"},
    }
    metadata = NodeMetadata(data)
    result = repr(metadata)
    assert "NodeMetadata(created_at='2024-01-15T10:30:00Z'" in result
    assert "created_by=NodeProperty({'id': 'account-1'" in result
    assert "updated_at='2024-01-16T14:45:00Z'" in result
    assert "updated_by=NodeProperty({'id': 'account-2'" in result


def test_relationship_metadata_repr_with_full_data() -> None:
    data = {
        "updated_at": "2024-01-16T14:45:00Z",
        "updated_by": {"id": "account-1", "display_label": "Admin", "__typename": "CoreAccount"},
    }
    metadata = RelationshipMetadata(data)
    result = repr(metadata)
    assert "RelationshipMetadata(updated_at='2024-01-16T14:45:00Z'" in result
    assert "updated_by=NodeProperty({'id': 'account-1'" in result


@pytest.mark.parametrize("client_type", client_types)
async def test_query_data_with_include_metadata(
    clients: BothClients, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    """Test that include_metadata=True adds node_metadata and attribute-level updated_by to the query."""
    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=location_schema)
        data = await node.generate_query_data(include_metadata=True)
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=location_schema)
        data = node.generate_query_data(include_metadata=True)

    edges = data["BuiltinLocation"]["edges"]

    # Verify node_metadata is present at the edge level
    assert "node_metadata" in edges
    assert edges["node_metadata"] == {
        "created_at": None,
        "created_by": {"id": None, "__typename": None, "display_label": None},
        "updated_at": None,
        "updated_by": {"id": None, "__typename": None, "display_label": None},
    }

    # Verify attribute-level metadata fields
    node_data = edges["node"]
    assert node_data["name"]["updated_at"] is None
    assert node_data["name"]["updated_by"] == {"id": None, "display_label": None, "__typename": None}
    assert node_data["description"]["updated_at"] is None
    assert node_data["description"]["updated_by"] == {"id": None, "display_label": None, "__typename": None}


@pytest.mark.parametrize("client_type", client_types)
async def test_query_data_with_include_metadata_and_property(
    clients: BothClients, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    """Test that include_metadata=True combined with property=True produces expected query structure."""
    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=location_schema)
        data = await node.generate_query_data(property=True, include_metadata=True)
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=location_schema)
        data = node.generate_query_data(property=True, include_metadata=True)

    edges = data["BuiltinLocation"]["edges"]

    # Verify node_metadata is present
    assert "node_metadata" in edges

    # Verify attribute has both property fields and metadata fields
    node_data = edges["node"]
    name_attr = node_data["name"]

    # Property fields
    assert "is_protected" in name_attr
    assert "source" in name_attr
    assert "owner" in name_attr
    assert "is_default" in name_attr
    assert "is_from_profile" in name_attr

    # Metadata fields
    assert "updated_at" in name_attr
    assert "updated_by" in name_attr
    assert name_attr["updated_by"] == {"id": None, "display_label": None, "__typename": None}

    # Verify relationship also has relationship_metadata
    primary_tag = node_data["primary_tag"]
    assert "relationship_metadata" in primary_tag
    assert primary_tag["relationship_metadata"] == {
        "updated_at": None,
        "updated_by": {"id": None, "__typename": None, "display_label": None},
    }


@pytest.mark.parametrize("client_type", client_types)
async def test_query_data_without_include_metadata(
    clients: BothClients, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    """Test that include_metadata=False (default) does not add metadata fields."""
    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=location_schema)
        data = await node.generate_query_data(include_metadata=False)
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=location_schema)
        data = node.generate_query_data(include_metadata=False)

    edges = data["BuiltinLocation"]["edges"]

    # Verify node_metadata is NOT present
    assert "node_metadata" not in edges

    # Verify attribute-level metadata fields are NOT present
    node_data = edges["node"]
    assert "updated_by" not in node_data["name"]


@pytest.mark.parametrize("client_type", client_types)
async def test_node_metadata_from_graphql_response(
    clients: BothClients, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    """Test that NodeMetadata is correctly parsed from GraphQL response data."""
    location_data = {
        "node": {
            "__typename": "BuiltinLocation",
            "id": "llllllll-llll-llll-llll-llllllllllll",
            "display_label": "dfw1",
            "name": {"value": "DFW"},
            "description": {"value": None},
            "type": {"value": "SITE"},
            "primary_tag": {
                "node": {
                    "id": "rrrrrrrr-rrrr-rrrr-rrrr-rrrrrrrrrrrr",
                    "display_label": "red",
                    "__typename": "BuiltinTag",
                },
            },
            "tags": {
                "count": 0,
                "edges": [],
            },
        },
        "node_metadata": {
            "created_at": "2024-01-15T10:30:00Z",
            "created_by": {"id": "account-1", "display_label": "Admin", "__typename": "CoreAccount"},
            "updated_at": "2024-01-16T14:45:00Z",
            "updated_by": {"id": "account-2", "display_label": "Editor", "__typename": "CoreAccount"},
        },
    }

    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=location_schema, data=location_data)
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=location_schema, data=location_data)

    metadata = node.get_node_metadata()

    assert metadata is not None
    assert metadata.created_at == "2024-01-15T10:30:00Z"
    assert metadata.created_by.id == "account-1"
    assert metadata.created_by.display_label == "Admin"
    assert metadata.updated_at == "2024-01-16T14:45:00Z"
    assert metadata.updated_by.id == "account-2"
    assert metadata.updated_by.display_label == "Editor"


@pytest.mark.parametrize("client_type", client_types)
async def test_relationship_metadata_from_graphql_response(
    clients: BothClients, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    """Test that RelationshipMetadata is correctly parsed from GraphQL response data."""
    location_data = {
        "node": {
            "__typename": "BuiltinLocation",
            "id": "llllllll-llll-llll-llll-llllllllllll",
            "display_label": "dfw1",
            "name": {"value": "DFW"},
            "description": {"value": None},
            "type": {"value": "SITE"},
            "primary_tag": {
                "node": {
                    "id": "rrrrrrrr-rrrr-rrrr-rrrr-rrrrrrrrrrrr",
                    "display_label": "red",
                    "__typename": "BuiltinTag",
                },
                "relationship_metadata": {
                    "updated_at": "2024-01-17T08:00:00Z",
                    "updated_by": {"id": "account-3", "display_label": "Updater", "__typename": "CoreAccount"},
                },
            },
            "tags": {
                "count": 0,
                "edges": [],
            },
        },
    }

    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=location_schema, data=location_data)
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=location_schema, data=location_data)

    rel_metadata = node.primary_tag.get_relationship_metadata()

    assert rel_metadata is not None
    assert rel_metadata.updated_at == "2024-01-17T08:00:00Z"
    assert rel_metadata.updated_by.id == "account-3"
    assert rel_metadata.updated_by.display_label == "Updater"


@pytest.mark.parametrize("client_type", client_types)
async def test_attribute_metadata_from_graphql_response(
    clients: BothClients, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    """Test that attribute-level metadata (updated_at, updated_by) is correctly parsed."""
    location_data = {
        "node": {
            "__typename": "BuiltinLocation",
            "id": "llllllll-llll-llll-llll-llllllllllll",
            "display_label": "dfw1",
            "name": {
                "value": "DFW",
                "updated_at": "2024-01-18T09:00:00Z",
                "updated_by": {"id": "account-4", "display_label": "NameUpdater", "__typename": "CoreAccount"},
            },
            "description": {
                "value": None,
                "updated_at": "2024-01-19T10:00:00Z",
                "updated_by": None,
            },
            "type": {"value": "SITE"},
            "primary_tag": {
                "node": {
                    "id": "rrrrrrrr-rrrr-rrrr-rrrr-rrrrrrrrrrrr",
                    "display_label": "red",
                    "__typename": "BuiltinTag",
                },
            },
            "tags": {
                "count": 0,
                "edges": [],
            },
        },
    }

    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=location_schema, data=location_data)
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=location_schema, data=location_data)

    assert node.name.updated_at == "2024-01-18T09:00:00Z"
    assert node.name.updated_by is not None
    assert node.name.updated_by.id == "account-4"
    assert node.name.updated_by.display_label == "NameUpdater"

    assert node.description.updated_at == "2024-01-19T10:00:00Z"
    assert node.description.updated_by is None


def test_node_metadata_with_no_data() -> None:
    """Test NodeMetadata initialization with no data argument."""
    metadata = NodeMetadata()

    assert metadata.created_at is None
    assert metadata.created_by is None
    assert metadata.updated_at is None
    assert metadata.updated_by is None


def test_node_metadata_with_none_data() -> None:
    """Test NodeMetadata initialization with explicit None data."""
    metadata = NodeMetadata(data=None)

    assert metadata.created_at is None
    assert metadata.created_by is None
    assert metadata.updated_at is None
    assert metadata.updated_by is None


def test_node_metadata_with_partial_data_missing_created_by() -> None:
    """Test NodeMetadata with data that has created_by as None."""
    data = {
        "created_at": "2024-01-15T10:30:00Z",
        "created_by": None,
        "updated_at": "2024-01-16T14:45:00Z",
        "updated_by": {"id": "account-2", "display_label": "Editor", "__typename": "CoreAccount"},
    }
    metadata = NodeMetadata(data=data)

    assert metadata.created_at == "2024-01-15T10:30:00Z"
    assert metadata.created_by is None
    assert metadata.updated_at == "2024-01-16T14:45:00Z"
    assert metadata.updated_by is not None
    assert metadata.updated_by.id == "account-2"


def test_node_metadata_with_partial_data_missing_updated_by() -> None:
    """Test NodeMetadata with data that has updated_by as None."""
    data = {
        "created_at": "2024-01-15T10:30:00Z",
        "created_by": {"id": "account-1", "display_label": "Admin", "__typename": "CoreAccount"},
        "updated_at": "2024-01-16T14:45:00Z",
        "updated_by": None,
    }
    metadata = NodeMetadata(data=data)

    assert metadata.created_at == "2024-01-15T10:30:00Z"
    assert metadata.created_by is not None
    assert metadata.created_by.id == "account-1"
    assert metadata.updated_at == "2024-01-16T14:45:00Z"
    assert metadata.updated_by is None


def test_node_metadata_with_partial_data_missing_both() -> None:
    """Test NodeMetadata with data that has both created_by and updated_by as None."""
    data = {
        "created_at": "2024-01-15T10:30:00Z",
        "created_by": None,
        "updated_at": "2024-01-16T14:45:00Z",
        "updated_by": None,
    }
    metadata = NodeMetadata(data=data)

    assert metadata.created_at == "2024-01-15T10:30:00Z"
    assert metadata.created_by is None
    assert metadata.updated_at == "2024-01-16T14:45:00Z"
    assert metadata.updated_by is None


def test_relationship_metadata_with_no_data() -> None:
    """Test RelationshipMetadata initialization with no data argument."""
    metadata = RelationshipMetadata()

    assert metadata.updated_at is None
    assert metadata.updated_by is None


def test_relationship_metadata_with_none_data() -> None:
    """Test RelationshipMetadata initialization with explicit None data."""
    metadata = RelationshipMetadata(data=None)

    assert metadata.updated_at is None
    assert metadata.updated_by is None


def test_relationship_metadata_with_partial_data_missing_updated_by() -> None:
    """Test RelationshipMetadata with data that has updated_by as None."""
    data = {
        "updated_at": "2024-01-17T08:00:00Z",
        "updated_by": None,
    }
    metadata = RelationshipMetadata(data=data)

    assert metadata.updated_at == "2024-01-17T08:00:00Z"
    assert metadata.updated_by is None


def test_relationship_manager_generate_query_data_with_include_metadata() -> None:
    """Test that RelationshipManagerBase._generate_query_data includes metadata when include_metadata=True."""
    data = RelationshipManagerBase._generate_query_data(include_metadata=True)

    assert "count" in data
    assert "edges" in data
    assert "node" in data["edges"]
    assert data["edges"]["node"]["id"] is None
    assert data["edges"]["node"]["hfid"] is None
    assert data["edges"]["node"]["display_label"] is None
    assert data["edges"]["node"]["__typename"] is None

    assert "node_metadata" in data["edges"]
    node_metadata = data["edges"]["node_metadata"]
    assert "created_at" in node_metadata
    assert "created_by" in node_metadata
    assert "updated_at" in node_metadata
    assert "updated_by" in node_metadata
    assert node_metadata["created_by"] == {"id": None, "__typename": None, "display_label": None}
    assert node_metadata["updated_by"] == {"id": None, "__typename": None, "display_label": None}

    assert "relationship_metadata" in data["edges"]
    rel_metadata = data["edges"]["relationship_metadata"]
    assert "updated_at" in rel_metadata
    assert "updated_by" in rel_metadata
    assert rel_metadata["updated_by"] == {"id": None, "__typename": None, "display_label": None}


def test_relationship_manager_generate_query_data_with_include_metadata_and_property() -> None:
    """Test RelationshipManagerBase._generate_query_data with both include_metadata=True and property=True."""
    data = RelationshipManagerBase._generate_query_data(include_metadata=True, property=True)

    assert "node_metadata" in data["edges"]
    assert "relationship_metadata" in data["edges"]
    assert "properties" in data["edges"]

    properties = data["edges"]["properties"]
    assert "is_protected" in properties
    assert "updated_at" in properties
    assert "source" in properties
    assert "owner" in properties


def test_relationship_manager_generate_query_data_without_include_metadata() -> None:
    """Test that RelationshipManagerBase._generate_query_data excludes metadata when include_metadata=False."""
    data = RelationshipManagerBase._generate_query_data(include_metadata=False)

    assert "node_metadata" not in data["edges"]
    assert "relationship_metadata" not in data["edges"]

    assert "count" in data
    assert "edges" in data
    assert "node" in data["edges"]


@pytest.mark.parametrize("client_type", client_types)
async def test_node_is_file_object_true(
    client_type: str, clients: BothClients, file_object_schema: NodeSchemaAPI
) -> None:
    """Test that is_file_object returns True for nodes inheriting from CoreFileObject."""
    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=file_object_schema, branch="main")
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=file_object_schema, branch="main")

    assert node.is_file_object()


@pytest.mark.parametrize("client_type", client_types)
async def test_node_is_file_object_false(
    client_type: str, clients: BothClients, non_file_object_schema: NodeSchemaAPI
) -> None:
    """Test that is_file_object returns False for regular nodes."""
    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=non_file_object_schema, branch="main")
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=non_file_object_schema, branch="main")

    assert not node.is_file_object()


@pytest.mark.parametrize("client_type", client_types)
async def test_node_upload_from_bytes_with_bytes(
    client_type: str, clients: BothClients, file_object_schema: NodeSchemaAPI
) -> None:
    """Test that upload_from_bytes works with bytes on FileObject nodes."""
    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=file_object_schema, branch="main")
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=file_object_schema, branch="main")

    file_content = b"PDF content here"
    node.upload_from_bytes(content=file_content, name="contract.pdf")

    assert node._file_content == file_content
    assert node._file_name == "contract.pdf"


@pytest.mark.parametrize("client_type", client_types)
async def test_node_upload_from_path(client_type: str, clients: BothClients, file_object_schema: NodeSchemaAPI) -> None:
    """Test that upload_from_path works with a Path object."""
    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=file_object_schema, branch="main")
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=file_object_schema, branch="main")

    file_content = b"Content from file path"
    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        tmp.write(file_content)
        tmp.flush()
        tmp_path = Path(tmp.name)

        node.upload_from_path(path=tmp_path)
        assert node._file_content == tmp_path
        assert node._file_name == tmp_path.name


@pytest.mark.parametrize("client_type", client_types)
async def test_node_upload_from_bytes_with_binary_io(
    client_type: str, clients: BothClients, file_object_schema: NodeSchemaAPI
) -> None:
    """Test that upload_from_bytes works with a BinaryIO object."""
    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=file_object_schema, branch="main")
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=file_object_schema, branch="main")

    file_content = b"Content from BinaryIO"
    file_obj = BytesIO(file_content)

    node.upload_from_bytes(content=file_obj, name="uploaded.pdf")

    assert node._file_content == file_obj
    assert node._file_name == "uploaded.pdf"


@pytest.mark.parametrize("client_type", client_types)
async def test_node_upload_from_bytes_on_non_file_object_raises(
    client_type: str, clients: BothClients, non_file_object_schema: NodeSchemaAPI
) -> None:
    """Test that upload_from_bytes raises FeatureNotSupportedError on non-FileObject nodes."""
    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=non_file_object_schema, branch="main")
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=non_file_object_schema, branch="main")

    with pytest.raises(FeatureNotSupportedError, match=r"File upload is not supported"):
        node.upload_from_bytes(content=b"some content", name="file.txt")


@pytest.mark.parametrize("client_type", client_types)
async def test_node_upload_from_path_on_non_file_object_raises(
    client_type: str, clients: BothClients, non_file_object_schema: NodeSchemaAPI
) -> None:
    """Test that upload_from_path raises FeatureNotSupportedError on non-FileObject nodes."""
    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=non_file_object_schema, branch="main")
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=non_file_object_schema, branch="main")

    with pytest.raises(FeatureNotSupportedError, match=r"File upload is not supported"):
        node.upload_from_path(path=Path("/some/file.txt"))


@pytest.mark.parametrize("client_type", client_types)
async def test_node_clear_file(client_type: str, clients: BothClients, file_object_schema: NodeSchemaAPI) -> None:
    """Test that clear_file removes pending file content."""
    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=file_object_schema, branch="main")
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=file_object_schema, branch="main")

    file_content = b"Test content"
    file_name = "file.txt"

    node.upload_from_bytes(content=file_content, name=file_name)
    assert node._file_content == file_content
    assert node._file_name == file_name

    node.clear_file()
    assert node._file_content is None
    assert node._file_name is None


@pytest.mark.parametrize("client_type", client_types)
async def test_node_get_file_for_upload_bytes(
    client_type: str, clients: BothClients, file_object_schema: NodeSchemaAPI
) -> None:
    """Test _get_file_for_upload with bytes returns PreparedFile with BytesIO."""
    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=file_object_schema, branch="main")
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=file_object_schema, branch="main")

    file_content = b"Test content"
    file_name = "test.txt"
    node.upload_from_bytes(content=file_content, name=file_name)

    if isinstance(node, InfrahubNode):
        prepared = await node._get_file_for_upload()
    else:
        prepared = node._get_file_for_upload_sync()

    assert prepared.file_object
    assert prepared.filename == file_name
    assert not prepared.should_close
    assert prepared.file_object.read() == file_content


@pytest.mark.parametrize("client_type", client_types)
async def test_node_get_file_for_upload_path(
    client_type: str, clients: BothClients, file_object_schema: NodeSchemaAPI
) -> None:
    """Test _get_file_for_upload with Path returns PreparedFile with opened file handle."""
    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=file_object_schema, branch="main")
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=file_object_schema, branch="main")

    file_content = b"Content from path"
    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        tmp.write(file_content)
        tmp.flush()
        tmp_path = Path(tmp.name)

        node.upload_from_path(path=tmp_path)

        if isinstance(node, InfrahubNode):
            prepared = await node._get_file_for_upload()
        else:
            prepared = node._get_file_for_upload_sync()

        assert prepared.file_object
        assert prepared.filename == tmp_path.name
        assert prepared.should_close  # Path files should be closed after upload
        assert prepared.file_object.read() == file_content
        prepared.file_object.close()


@pytest.mark.parametrize("client_type", client_types)
async def test_node_get_file_for_upload_binary_io(
    client_type: str, clients: BothClients, file_object_schema: NodeSchemaAPI
) -> None:
    """Test _get_file_for_upload with BinaryIO returns PreparedFile with the same object."""
    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=file_object_schema, branch="main")
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=file_object_schema, branch="main")

    file_content = b"Content from BinaryIO"
    file_name = "test.bin"
    file_obj_input = BytesIO(file_content)
    node.upload_from_bytes(content=file_obj_input, name=file_name)

    if isinstance(node, InfrahubNode):
        prepared = await node._get_file_for_upload()
    else:
        prepared = node._get_file_for_upload_sync()

    assert prepared.file_object is file_obj_input  # Should be the same object
    assert prepared.filename == file_name
    assert not prepared.should_close  # BinaryIO provided by user shouldn't be closed


@pytest.mark.parametrize("client_type", client_types)
async def test_node_get_file_for_upload_none(
    client_type: str, clients: BothClients, file_object_schema: NodeSchemaAPI
) -> None:
    """Test _get_file_for_upload with no file set returns PreparedFile with None values."""
    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=file_object_schema, branch="main")
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=file_object_schema, branch="main")

    if isinstance(node, InfrahubNode):
        prepared = await node._get_file_for_upload()
    else:
        prepared = node._get_file_for_upload_sync()

    assert prepared.file_object is None
    assert prepared.filename is None
    assert not prepared.should_close


@pytest.mark.parametrize("client_type", client_types)
async def test_node_generate_input_data_with_file(
    client_type: str, clients: BothClients, file_object_schema: NodeSchemaAPI
) -> None:
    """Test _generate_input_data places file at mutation level, not inside data."""
    if client_type == "standard":
        node = InfrahubNode(client=clients.standard, schema=file_object_schema, branch="main")
    else:
        node = InfrahubNodeSync(client=clients.sync, schema=file_object_schema, branch="main")

    node.upload_from_bytes(content=b"test content", name="test.txt")

    input_data = node._generate_input_data()

    assert "file" in input_data["data"], "file should be at mutation payload level"
    assert input_data["data"]["file"] == "$file"
    assert "file" not in input_data["data"]["data"], "file should not be inside nested data dict"
    assert "file" in input_data["mutation_variables"]
    assert input_data["mutation_variables"]["file"] is bytes
