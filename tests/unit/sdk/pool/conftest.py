from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import ujson

from infrahub_sdk.schema import BranchSupportType, NodeSchema, NodeSchemaAPI
from infrahub_sdk.utils import get_fixtures_dir

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock


@pytest.fixture
async def ipam_ipprefix_schema() -> NodeSchemaAPI:
    data = {
        "name": "IPNetwork",
        "namespace": "Ipam",
        "default_filter": "prefix__value",
        "display_labels": ["prefix_value"],
        "order_by": ["prefix_value"],
        "inherit_from": ["BuiltinIPAddress"],
    }
    return NodeSchema(**data).convert_api()


@pytest.fixture
async def simple_device_schema() -> NodeSchemaAPI:
    data = {
        "name": "Device",
        "namespace": "Infra",
        "label": "Device",
        "default_filter": "name__value",
        "order_by": ["name__value"],
        "display_labels": ["name__value"],
        "attributes": [{"name": "name", "kind": "Text", "unique": True}],
        "relationships": [
            {
                "name": "primary_address",
                "peer": "IpamIPAddress",
                "label": "Primary IP Address",
                "optional": True,
                "cardinality": "one",
                "kind": "Attribute",
            },
            {
                "name": "ip_address_pool",
                "peer": "CoreIPAddressPool",
                "label": "Address allocator",
                "optional": True,
                "cardinality": "one",
                "kind": "Attribute",
            },
        ],
    }
    return NodeSchema(**data).convert_api()


@pytest.fixture
async def ipam_ipprefix_data() -> dict[str, Any]:
    return {
        "node": {
            "__typename": "IpamIPPrefix",
            "id": "llllllll-llll-llll-llll-llllllllllll",
            "display_label": "192.0.2.0/24",
            "prefix": {
                "is_protected": True,
                "owner": None,
                "source": {
                    "__typename": "Account",
                    "display_label": "CRM",
                    "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                },
                "value": "192.0.2.0/24",
            },
            "description": {
                "is_protected": False,
                "owner": None,
                "source": None,
                "value": None,
            },
            "member_type": {
                "is_protected": True,
                "owner": None,
                "source": {
                    "__typename": "Account",
                    "display_label": "CRM",
                    "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                },
                "value": "address",
            },
            "is_pool": {
                "is_protected": True,
                "owner": None,
                "source": {
                    "__typename": "Account",
                    "display_label": "CRM",
                    "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                },
                "value": False,
            },
            "ip_namespace": {
                "properties": {
                    "is_protected": True,
                    "owner": None,
                    "source": {
                        "__typename": "Account",
                        "display_label": "CRM",
                        "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                    },
                },
                "node": {
                    "id": "rrrrrrrr-rrrr-rrrr-rrrr-rrrrrrrrrrrr",
                    "display_label": "default",
                    "__typename": "IpamNamespace",
                },
            },
        }
    }


@pytest.fixture
async def ipaddress_pool_schema() -> NodeSchemaAPI:
    data = {
        "name": "IPAddressPool",
        "namespace": "Core",
        "description": "A pool of IP address resources",
        "label": "IP Address Pool",
        "default_filter": "name__value",
        "order_by": ["name__value"],
        "display_labels": ["name__value"],
        "include_in_menu": False,
        "branch": BranchSupportType.AGNOSTIC.value,
        "inherit_from": ["CoreResourcePool"],
        "attributes": [
            {
                "name": "default_address_type",
                "kind": "Text",
                "optional": False,
                "description": "The object type to create when reserving a resource in the pool",
            },
            {
                "name": "default_prefix_length",
                "kind": "Number",
                "optional": True,
            },
        ],
        "relationships": [
            {
                "name": "resources",
                "peer": "BuiltinIPPrefix",
                "kind": "Attribute",
                "identifier": "ipaddresspool__resource",
                "cardinality": "many",
                "optional": False,
                "order_weight": 4000,
            },
            {
                "name": "ip_namespace",
                "peer": "BuiltinIPNamespace",
                "kind": "Attribute",
                "identifier": "ipaddresspool__ipnamespace",
                "cardinality": "one",
                "optional": False,
                "order_weight": 5000,
            },
        ],
    }
    return NodeSchema(**data).convert_api()


@pytest.fixture
async def ipprefix_pool_schema() -> NodeSchemaAPI:
    data = {
        "name": "IPPrefixPool",
        "namespace": "Core",
        "description": "A pool of IP prefix resources",
        "label": "IP Prefix Pool",
        "include_in_menu": False,
        "branch": BranchSupportType.AGNOSTIC.value,
        "inherit_from": ["CoreResourcePool"],
        "attributes": [
            {
                "name": "default_prefix_length",
                "kind": "Number",
                "description": "The default prefix length as an integer for prefixes allocated from this pool.",
                "optional": True,
                "order_weight": 5000,
            },
            {
                "name": "default_member_type",
                "kind": "Text",
                "enum": ["prefix", "address"],
                "default_value": "prefix",
                "optional": True,
                "order_weight": 3000,
            },
            {
                "name": "default_prefix_type",
                "kind": "Text",
                "optional": True,
                "order_weight": 4000,
            },
        ],
        "relationships": [
            {
                "name": "resources",
                "peer": "BuiltinIPPrefix",
                "kind": "Attribute",
                "identifier": "prefixpool__resource",
                "cardinality": "many",
                "branch": BranchSupportType.AGNOSTIC.value,
                "optional": False,
                "order_weight": 6000,
            },
            {
                "name": "ip_namespace",
                "peer": "BuiltinIPNamespace",
                "kind": "Attribute",
                "identifier": "prefixpool__ipnamespace",
                "cardinality": "one",
                "branch": BranchSupportType.AGNOSTIC.value,
                "optional": False,
                "order_weight": 7000,
            },
        ],
    }
    return NodeSchema(**data).convert_api()


@pytest.fixture
async def mock_schema_query_ipam(httpx_mock: HTTPXMock) -> HTTPXMock:
    response_text = (get_fixtures_dir() / "schema_ipam.json").read_text(encoding="UTF-8")

    httpx_mock.add_response(
        method="GET", url="http://mock/api/schema?branch=main", json=ujson.loads(response_text), is_reusable=True
    )
    return httpx_mock


@pytest.fixture
async def vlan_schema() -> NodeSchemaAPI:
    data = {
        "name": "VLAN",
        "namespace": "Infra",
        "label": "VLAN",
        "default_filter": "name__value",
        "order_by": ["name__value"],
        "display_labels": ["name__value"],
        "attributes": [
            {"name": "name", "kind": "Text", "unique": True},
            {"name": "vlan_id", "kind": "Number"},
            {"name": "role", "kind": "Text", "optional": True},
            {"name": "status", "kind": "Text", "optional": True},
        ],
        "relationships": [],
    }
    return NodeSchema(**data).convert_api()
