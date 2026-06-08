from __future__ import annotations

import ipaddress
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, NamedTuple, get_args

from ..uuidt import UUIDT
from .constants import ATTRIBUTE_METADATA_OBJECT, IP_TYPES, PROPERTIES_FLAG, PROPERTIES_OBJECT, SAFE_VALUE
from .property import NodeProperty

if TYPE_CHECKING:
    from ..schema import AttributeSchemaAPI


class _GraphQLPayloadAttribute(NamedTuple):
    """Result of resolving an attribute value for a GraphQL mutation.

    Attributes:
        payload: Key/value entries to include in the mutation payload
            (e.g. ``{"value": ...}`` or ``{"from_pool": ...}``).
        variables: GraphQL variable bindings for unsafe string values.
        needs_metadata: When ``True``, the payload needs to append property flags/objects

    """

    payload: dict[str, Any]
    variables: dict[str, Any]
    needs_metadata: bool

    def to_dict(self) -> dict[str, Any]:
        return {"data": self.payload, "variables": self.variables}

    def add_properties(self, properties_flag: dict[str, Any], properties_object: dict[str, str | None]) -> None:
        if not self.needs_metadata:
            return
        for prop_name, prop in properties_flag.items():
            self.payload[prop_name] = prop

        for prop_name, prop in properties_object.items():
            self.payload[prop_name] = prop


class Attribute:
    """Represents an attribute of a Node, including its schema, value, and properties."""

    def __init__(self, name: str, schema: AttributeSchemaAPI, data: Any | dict) -> None:
        """Initialize the attribute.

        Args:
            name (str): The name of the attribute.
            schema (AttributeSchema): The schema defining the attribute.
            data (Union[Any, dict]): The data for the attribute, either in raw form or as a dictionary.

        """
        self.name = name
        self._schema = schema
        self._from_pool: dict[str, Any] | None = None

        if isinstance(data, dict) and "from_pool" in data:
            self._from_pool = data.pop("from_pool")
            data.setdefault("value", None)
        elif not isinstance(data, dict) or "value" not in data:
            data = {"value": data}

        self._properties_flag = PROPERTIES_FLAG
        self._properties_object = PROPERTIES_OBJECT
        self._properties = self._properties_flag + self._properties_object

        self._read_only = ["updated_at", "is_inherited"]

        self.id: str | None = data.get("id")

        self._value: Any | None = data.get("value")
        self.value_has_been_mutated = False
        self.is_default: bool | None = data.get("is_default")
        self.is_from_profile: bool | None = data.get("is_from_profile")

        if self._value:
            value_mapper: dict[str, Callable] = {
                "IPHost": ipaddress.ip_interface,
                "IPNetwork": ipaddress.ip_network,
            }
            mapper = value_mapper.get(schema.kind, lambda value: value)
            self._value = mapper(data.get("value"))

        self.is_inherited: bool | None = data.get("is_inherited")
        self.updated_at: str | None = data.get("updated_at")

        self.is_protected: bool | None = data.get("is_protected")

        self.source: NodeProperty | None = None
        self.owner: NodeProperty | None = None
        self.updated_by: NodeProperty | None = None

        for prop_name in self._properties_object:
            if data.get(prop_name):
                setattr(self, prop_name, NodeProperty(data=data.get(prop_name)))  # type: ignore[arg-type]

        for prop_name in ATTRIBUTE_METADATA_OBJECT:
            if data.get(prop_name):
                setattr(self, prop_name, NodeProperty(data=data.get(prop_name)))  # type: ignore[arg-type]

    @property
    def value(self) -> Any:
        return self._value

    @value.setter
    def value(self, value: Any) -> None:
        self._value = value
        self.value_has_been_mutated = True

    def _initialize_graphql_payload(self) -> _GraphQLPayloadAttribute:
        """Resolve the attribute value into a GraphQL mutation payload object."""
        # Pool-based allocation (dict data or resource-pool node)
        if self._from_pool is not None:
            return _GraphQLPayloadAttribute(payload={"from_pool": self._from_pool}, variables={}, needs_metadata=True)
        if hasattr(self.value, "is_resource_pool") and self.value.is_resource_pool():
            return _GraphQLPayloadAttribute(
                payload={"from_pool": {"id": self.value.id}}, variables={}, needs_metadata=True
            )

        # Null value
        if self.value is None:
            data = {"value": None} if (self._schema.optional and self.value_has_been_mutated) else {}
            return _GraphQLPayloadAttribute(payload=data, variables={}, needs_metadata=False)

        # Unsafe strings need a variable binding to avoid injection
        if isinstance(self.value, str) and not SAFE_VALUE.match(self.value):
            var_name = f"value_{UUIDT.new().hex}"
            return _GraphQLPayloadAttribute(
                payload={"value": f"${var_name}"},
                variables={var_name: self.value},
                needs_metadata=True,
            )

        # Safe strings, IP types, and everything else
        value = self.value.with_prefixlen if isinstance(self.value, get_args(IP_TYPES)) else self.value
        return _GraphQLPayloadAttribute(payload={"value": value}, variables={}, needs_metadata=True)

    def _generate_input_data(self) -> _GraphQLPayloadAttribute:
        """Build the input payload for a GraphQL mutation on this attribute.

        Returns a ResolvedValue object, which contains all the data required.
        """
        graphql_payload = self._initialize_graphql_payload()

        properties_flag: dict[str, Any] = {
            property_name: getattr(self, property_name)
            for property_name in self._properties_flag
            if getattr(self, property_name) is not None
        }
        properties_object: dict[str, str | None] = {
            property_name: getattr(self, property_name)._generate_input_data()
            for property_name in self._properties_object
            if getattr(self, property_name) is not None
        }
        graphql_payload.add_properties(properties_flag, properties_object)

        return graphql_payload

    def _generate_query_data(self, property: bool = False, include_metadata: bool = False) -> dict | None:
        data: dict[str, Any] = {"value": None}

        if property:
            data.update({"is_default": None, "is_from_profile": None})

            for prop_name in self._properties_flag:
                data[prop_name] = None
            for prop_name in self._properties_object:
                data[prop_name] = {"id": None, "display_label": None, "__typename": None}

        if include_metadata:
            data["updated_at"] = None
            for prop_name in ATTRIBUTE_METADATA_OBJECT:
                data[prop_name] = {"id": None, "display_label": None, "__typename": None}

        return data

    def _generate_mutation_query(self) -> dict[str, Any]:
        if self.is_from_pool_attribute():
            # If it points to a pool, ask for the value of the pool allocated resource
            return {self.name: {"value": None}}
        return {}

    def is_from_pool_attribute(self) -> bool:
        """Check whether this attribute's value is sourced from a resource pool.

        Returns:
            True if the attribute value is a resource pool node or was explicitly allocated from a pool.

        """
        return (
            hasattr(self.value, "is_resource_pool") and self.value.is_resource_pool()
        ) or self._from_pool is not None
