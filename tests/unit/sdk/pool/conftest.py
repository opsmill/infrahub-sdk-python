from __future__ import annotations

from typing import Any

import pytest

from infrahub_sdk.schema import BranchSupportType, NodeSchema, NodeSchemaAPI


@pytest.fixture
async def ipaddress_pool_schema() -> NodeSchemaAPI:
    data: dict[str, Any] = {
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
    data: dict[str, Any] = {
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
