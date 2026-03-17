"""Unit tests for Attribute._generate_input_data covering all code paths."""

from __future__ import annotations

from typing import Any

import pytest

from infrahub_sdk.node.attribute import Attribute
from infrahub_sdk.protocols_base import CoreNodeBase
from infrahub_sdk.schema import AttributeSchemaAPI
from infrahub_sdk.schema.main import AttributeKind

# ──────────────────────────────────────────────
# Value resolution: from_pool (dict-based)
# ──────────────────────────────────────────────


class TestFromPoolDict:
    def test_from_pool_with_id(self) -> None:
        pool_data = {"id": "pool-uuid-1"}
        attr = Attribute(name="vlan_id", schema=_make_schema(AttributeKind.NUMBER), data={"from_pool": pool_data})

        result = attr._generate_input_data()

        assert result.payload == {"from_pool": {"id": "pool-uuid-1"}}
        assert result.variables == {}

    def test_from_pool_with_id_and_identifier(self) -> None:
        pool_data = {"id": "pool-uuid-1", "identifier": "test"}
        attr = Attribute(name="vlan_id", schema=_make_schema(AttributeKind.NUMBER), data={"from_pool": pool_data})

        result = attr._generate_input_data()

        assert result.payload == {"from_pool": {"id": "pool-uuid-1", "identifier": "test"}}
        assert result.variables == {}

    def test_from_pool_with_pool_name(self) -> None:
        """from_pool can be a plain string (pool name), e.g. from_pool: 'VLAN ID Pool'."""
        attr = Attribute(
            name="vlan_id", schema=_make_schema(AttributeKind.NUMBER, optional=True), data={"from_pool": "VLAN ID Pool"}
        )

        result = attr._generate_input_data()

        assert result.payload == {"from_pool": "VLAN ID Pool"}
        assert result.variables == {}
        assert "value" not in result.payload

    def test_from_pool_value_is_none(self) -> None:
        """from_pool pops 'from_pool' and sets Attribute.value to None; value should NOT appear in payload."""
        attr = Attribute(
            name="vlan_id", schema=_make_schema(AttributeKind.NUMBER), data={"from_pool": {"id": "pool-uuid-1"}}
        )

        assert attr.value is None
        result = attr._generate_input_data()
        assert "value" not in result.payload


# ──────────────────────────────────────────────
# Value resolution: from_pool (node-based)
# ──────────────────────────────────────────────


class TestFromPoolNode:
    def test_pool_node_generates_from_pool(self) -> None:
        pool_node = _FakeNode(node_id="node-pool-uuid", is_pool=True)

        attr = Attribute(name="vlan_id", schema=_make_schema(AttributeKind.NUMBER), data=pool_node)

        result = attr._generate_input_data()

        assert result.payload == {"from_pool": {"id": "node-pool-uuid"}}
        assert result.variables == {}

    def test_non_pool_node_treated_as_regular_value(self) -> None:
        """A CoreNodeBase that is NOT a resource pool should go through the normal value path."""
        node = _FakeNode(node_id="regular-node-uuid", is_pool=False)
        attr = Attribute(name="vlan_id", schema=_make_schema(AttributeKind.NUMBER), data=node)

        result = attr._generate_input_data()

        assert result.payload == {"value": node}


# ──────────────────────────────────────────────
# Value resolution: null values
# ──────────────────────────────────────────────


class TestNullValue:
    def test_null_value_not_mutated(self) -> None:
        """None value that was never mutated → empty payload, no properties."""
        attr = Attribute(name="test_attr", schema=_make_schema(AttributeKind.TEXT), data={"value": None})

        result = attr._generate_input_data()

        assert result.payload == {}
        assert result.variables == {}
        assert result.needs_metadata is False

    def test_null_value_mutated_optional(self) -> None:
        """None value on an optional attr that was mutated → explicit null."""
        attr = Attribute(
            name="test_attr", schema=_make_schema(AttributeKind.TEXT, optional=True), data={"value": "initial"}
        )
        attr.value = None  # triggers value_has_been_mutated

        result = attr._generate_input_data()

        assert result.payload == {"value": None}
        assert result.needs_metadata is False

    def test_null_value_mutated_non_optional(self) -> None:
        """None value on a non-optional attr that was mutated → empty payload (same as not mutated)."""
        attr = Attribute(
            name="test_attr", schema=_make_schema(AttributeKind.TEXT, optional=False), data={"value": "initial"}
        )
        attr.value = None

        result = attr._generate_input_data()

        assert result.payload == {}
        assert result.needs_metadata is False


# ──────────────────────────────────────────────
# Value resolution: strings (safe vs unsafe)
# ──────────────────────────────────────────────


class TestStringValues:
    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("simple", id="alphanumeric"),
            pytest.param("user.name", id="dots"),
            pytest.param("/opt/repos/infrahub", id="filepath"),
            pytest.param("https://github.com/opsmill", id="url"),
            pytest.param("", id="empty-string"),
        ],
    )
    def test_safe_string(self, value: str) -> None:
        attr = Attribute(name="test_attr", schema=_make_schema(AttributeKind.TEXT), data=value)

        result = attr._generate_input_data()

        assert result.payload == {"value": value}
        assert result.variables == {}

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param('has "quotes"', id="quotes"),
            pytest.param("has\nnewline", id="newline"),
            pytest.param("special{chars}", id="braces"),
        ],
    )
    def test_unsafe_string_uses_variable_binding(self, value: str) -> None:
        attr = Attribute(name="test_attr", schema=_make_schema(AttributeKind.TEXT), data=value)

        result = attr._generate_input_data()

        # payload["value"] should be a variable reference like "$value_<hex>"
        assert "value" in result.payload
        assert result.payload["value"].startswith("$value_")
        # The actual string should be in variables
        assert len(result.variables) == 1
        var_name = next(iter(result.variables))
        assert result.variables[var_name] == value


# ──────────────────────────────────────────────
# Value resolution: IP types
# ──────────────────────────────────────────────


class TestIPValues:
    def test_ipv4_interface(self) -> None:
        attr = Attribute(name="address", schema=_make_schema(AttributeKind.IPHOST), data={"value": "10.0.0.1/24"})

        result = attr._generate_input_data()

        assert result.payload["value"] == "10.0.0.1/24"
        assert result.variables == {}

    def test_ipv6_interface(self) -> None:
        attr = Attribute(name="address", schema=_make_schema(AttributeKind.IPHOST), data={"value": "2001:db8::1/64"})

        result = attr._generate_input_data()

        assert result.payload["value"] == "2001:db8::1/64"

    def test_ipv4_network(self) -> None:
        attr = Attribute(name="network", schema=_make_schema(AttributeKind.IPNETWORK), data={"value": "10.0.0.0/24"})

        result = attr._generate_input_data()

        assert result.payload["value"] == "10.0.0.0/24"

    def test_ipv6_network(self) -> None:
        attr = Attribute(name="network", schema=_make_schema(AttributeKind.IPNETWORK), data={"value": "2001:db8::/32"})

        result = attr._generate_input_data()

        assert result.payload["value"] == "2001:db8::/32"


# ──────────────────────────────────────────────
# Value resolution: other scalars
# ──────────────────────────────────────────────


class TestScalarValues:
    def test_number_value(self) -> None:
        attr = Attribute(name="vlan_id", schema=_make_schema(AttributeKind.NUMBER), data=42)

        result = attr._generate_input_data()

        assert result.payload == {"value": 42}
        assert result.variables == {}

    def test_boolean_value(self) -> None:
        attr = Attribute(name="enabled", schema=_make_schema(AttributeKind.BOOLEAN), data=True)

        result = attr._generate_input_data()

        assert result.payload == {"value": True}


# ──────────────────────────────────────────────
# Property handling
# ──────────────────────────────────────────────


class TestProperties:
    def test_no_properties_set(self) -> None:
        """When no properties are set, payload only has the value."""
        attr = Attribute(name="test_attr", schema=_make_schema(AttributeKind.TEXT), data="hello")

        result = attr._generate_input_data()

        assert result.payload == {"value": "hello"}

    def test_flag_property_is_protected(self) -> None:
        attr = Attribute(
            name="test_attr", schema=_make_schema(AttributeKind.TEXT), data={"value": "hello", "is_protected": True}
        )

        result = attr._generate_input_data()

        assert result.payload["value"] == "hello"
        assert result.payload["is_protected"] is True

    def test_object_property_source(self) -> None:
        attr = Attribute(
            name="test_attr",
            schema=_make_schema(AttributeKind.TEXT),
            data={"value": "hello", "source": {"id": "source-uuid", "display_label": "Git", "__typename": "CoreGit"}},
        )

        result = attr._generate_input_data()

        assert result.payload["value"] == "hello"
        assert result.payload["source"] == "source-uuid"

    def test_object_property_owner(self) -> None:
        attr = Attribute(
            name="test_attr",
            schema=_make_schema(AttributeKind.TEXT),
            data={
                "value": "hello",
                "owner": {"id": "owner-uuid", "display_label": "Admin", "__typename": "CoreAccount"},
            },
        )

        result = attr._generate_input_data()

        assert result.payload["owner"] == "owner-uuid"

    def test_both_flag_and_object_properties(self) -> None:
        attr = Attribute(
            name="test_attr",
            schema=_make_schema(AttributeKind.TEXT),
            data={
                "value": "hello",
                "is_protected": True,
                "source": {"id": "src-uuid", "display_label": "Git", "__typename": "CoreGit"},
            },
        )

        result = attr._generate_input_data()

        assert result.payload["value"] == "hello"
        assert result.payload["is_protected"] is True
        assert result.payload["source"] == "src-uuid"

    def test_properties_not_appended_for_null_value(self) -> None:
        """When need_additional_properties is False (null non-mutated), properties are ignored."""
        attr = Attribute(
            name="test_attr",
            schema=_make_schema(AttributeKind.TEXT),
            data={
                "value": None,
                "is_protected": True,
                "source": {"id": "src-uuid", "display_label": "Git", "__typename": "CoreGit"},
            },
        )

        result = attr._generate_input_data()

        # Null value, not mutated → empty payload, properties NOT appended
        assert result.payload == {}

    def test_properties_appended_for_from_pool(self) -> None:
        """from_pool payloads have need_additional_properties=True, so properties are included."""
        attr = Attribute(
            name="vlan_id",
            schema=_make_schema(AttributeKind.NUMBER),
            data={"from_pool": {"id": "pool-uuid"}, "is_protected": True},
        )

        result = attr._generate_input_data()

        assert result.payload["from_pool"] == {"id": "pool-uuid"}
        assert result.payload["is_protected"] is True


# ──────────────────────────────────────────────
# Return type: to_dict() integration
# ──────────────────────────────────────────────


class TestToDictIntegration:
    def test_to_dict_simple_value(self) -> None:
        attr = Attribute(name="test_attr", schema=_make_schema(AttributeKind.TEXT), data="hello")

        result = attr._generate_input_data().to_dict()

        assert result == {"data": {"value": "hello"}, "variables": {}}

    def test_to_dict_with_variables(self) -> None:
        attr = Attribute(name="test_attr", schema=_make_schema(AttributeKind.TEXT), data='has "quotes"')

        result = attr._generate_input_data().to_dict()

        assert "data" in result
        assert "variables" in result
        assert len(result["variables"]) == 1
        var_name = next(iter(result["variables"]))
        assert result["variables"][var_name] == 'has "quotes"'
        assert result["data"]["value"] == f"${var_name}"


def _make_schema(kind: AttributeKind = AttributeKind.TEXT, optional: bool = False) -> AttributeSchemaAPI:
    return AttributeSchemaAPI(name="test_attr", kind=kind, optional=optional)


class _FakeNode(CoreNodeBase):
    """Minimal CoreNodeBase implementation for testing."""

    def __init__(self, node_id: str, is_pool: bool) -> None:
        self.id = node_id
        self._is_pool = is_pool
        self._schema: Any = None
        self._internal_id = ""
        self.display_label = None
        self.typename = None

    @property
    def hfid(self) -> list[str] | None:
        return None

    @property
    def hfid_str(self) -> str | None:
        return None

    def get_human_friendly_id(self) -> list[str] | None:
        return None

    def get_human_friendly_id_as_string(self, include_kind: bool = False) -> str | None:
        return None

    def get_kind(self) -> str:
        return ""

    def get_all_kinds(self) -> list[str]:
        return []

    def get_branch(self) -> str:
        return ""

    def is_ip_prefix(self) -> bool:
        return False

    def is_ip_address(self) -> bool:
        return False

    def is_resource_pool(self) -> bool:
        return self._is_pool

    def get_raw_graphql_data(self) -> dict | None:
        return None
