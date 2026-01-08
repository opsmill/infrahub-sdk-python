from __future__ import annotations

import os
from typing import Any

import pytest

from infrahub_sdk.utils import str_to_bool

BUILD_NAME = os.environ.get("INFRAHUB_BUILD_NAME", "infrahub")
TEST_IN_DOCKER = str_to_bool(os.environ.get("INFRAHUB_TEST_IN_DOCKER", "false"))


@pytest.fixture(scope="module")
def schema_extension_01() -> dict[str, Any]:
    return {
        "version": "1.0",
        "nodes": [
            {
                "name": "Rack",
                "namespace": "Infra",
                "description": "A Rack represents a physical two- or four-post equipment rack.",
                "label": "Rack",
                "default_filter": "name__value",
                "display_labels": ["name__value"],
                "attributes": [
                    {"name": "name", "kind": "Text"},
                    {"name": "description", "kind": "Text", "optional": True},
                ],
                "relationships": [
                    {
                        "name": "tags",
                        "peer": "BuiltinTag",
                        "optional": True,
                        "cardinality": "many",
                        "kind": "Attribute",
                    },
                ],
            }
        ],
        "extensions": {
            "nodes": [
                {
                    "kind": "BuiltinTag",
                    "relationships": [
                        {
                            "name": "racks",
                            "peer": "InfraRack",
                            "optional": True,
                            "cardinality": "many",
                            "kind": "Generic",
                        }
                    ],
                }
            ]
        },
    }


@pytest.fixture(scope="module")
def schema_extension_02() -> dict[str, Any]:
    return {
        "version": "1.0",
        "nodes": [
            {
                "name": "Contract",
                "namespace": "Procurement",
                "description": "Generic Contract",
                "label": "Contract",
                "display_labels": ["contract_ref__value"],
                "order_by": ["contract_ref__value"],
                "attributes": [
                    {
                        "name": "contract_ref",
                        "label": "Contract Reference",
                        "kind": "Text",
                        "unique": True,
                    },
                    {"name": "description", "kind": "Text", "optional": True},
                ],
                "relationships": [
                    {
                        "name": "tags",
                        "peer": "BuiltinTag",
                        "optional": True,
                        "cardinality": "many",
                        "kind": "Attribute",
                    },
                ],
            }
        ],
        "extensions": {
            "nodes": [
                {
                    "kind": "BuiltinTag",
                    "relationships": [
                        {
                            "name": "contracts",
                            "peer": "ProcurementContract",
                            "optional": True,
                            "cardinality": "many",
                            "kind": "Generic",
                        }
                    ],
                }
            ]
        },
    }


@pytest.fixture(scope="module")
def hierarchical_schema() -> dict[str, Any]:
    return {
        "version": "1.0",
        "generics": [
            {
                "name": "Generic",
                "namespace": "Location",
                "description": "Generic hierarchical location",
                "label": "Location",
                "hierarchical": True,
                "human_friendly_id": ["name__value"],
                "include_in_menu": True,
                "attributes": [
                    {"name": "name", "kind": "Text", "unique": True, "order_weight": 900},
                ],
            }
        ],
        "nodes": [
            {
                "name": "Country",
                "namespace": "Location",
                "description": "A country within a continent.",
                "inherit_from": ["LocationGeneric"],
                "generate_profile": False,
                "default_filter": "name__value",
                "order_by": ["name__value"],
                "display_labels": ["name__value"],
                "children": "LocationSite",
                "attributes": [{"name": "shortname", "kind": "Text"}],
            },
            {
                "name": "Site",
                "namespace": "Location",
                "description": "A site within a country.",
                "inherit_from": ["LocationGeneric"],
                "default_filter": "name__value",
                "order_by": ["name__value"],
                "display_labels": ["name__value"],
                "children": "",
                "parent": "LocationCountry",
                "attributes": [{"name": "shortname", "kind": "Text"}],
            },
        ],
    }


@pytest.fixture(scope="module")
def ipam_schema() -> dict[str, Any]:
    return {
        "version": "1.0",
        "nodes": [
            {
                "name": "IPPrefix",
                "namespace": "Ipam",
                "include_in_menu": False,
                "inherit_from": ["BuiltinIPPrefix"],
                "description": "IPv4 or IPv6 network",
                "icon": "mdi:ip-network",
                "label": "IP Prefix",
            },
            {
                "name": "IPAddress",
                "namespace": "Ipam",
                "include_in_menu": False,
                "inherit_from": ["BuiltinIPAddress"],
                "description": "IP Address",
                "icon": "mdi:ip-outline",
                "label": "IP Address",
            },
            {
                "name": "Device",
                "namespace": "Infra",
                "label": "Device",
                "human_friendly_id": ["name__value"],
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
                    }
                ],
            },
        ],
    }
