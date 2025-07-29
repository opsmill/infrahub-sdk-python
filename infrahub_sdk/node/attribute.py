from __future__ import annotations

import ipaddress
from typing import TYPE_CHECKING, Any, Callable, get_args

from ..protocols_base import CoreNodeBase
from ..uuidt import UUIDT
from .constants import IP_TYPES, PROPERTIES_FLAG, PROPERTIES_OBJECT, SAFE_VALUE
from .property import NodeProperty

if TYPE_CHECKING:
    from ..schema import AttributeSchemaAPI


class Attribute:
    """Represents an attribute of a Node, including its schema, value, and properties."""

    def __init__(self, name: str, schema: AttributeSchemaAPI, data: Any | dict):
        """
        Args:
            name (str): The name of the attribute.
            schema (AttributeSchema): The schema defining the attribute.
            data (Union[Any, dict]): The data for the attribute, either in raw form or as a dictionary.
        """
        self.name = name
        self._schema = schema

        if not isinstance(data, dict) or "value" not in data.keys():
            data = {"value": data}

        self._properties_flag = PROPERTIES_FLAG
        self._properties_object = PROPERTIES_OBJECT
        self._properties = self._properties_flag + self._properties_object

        self._read_only = ["updated_at", "is_inherited"]

        self.id: str | None = data.get("id", None)

        self._value: Any | None = data.get("value", None)
        self.value_has_been_mutated = False
        self.is_default: bool | None = data.get("is_default", None)
        self.is_from_profile: bool | None = data.get("is_from_profile", None)

        if self._value:
            value_mapper: dict[str, Callable] = {
                "IPHost": ipaddress.ip_interface,
                "IPNetwork": ipaddress.ip_network,
            }
            mapper = value_mapper.get(schema.kind, lambda value: value)
            self._value = mapper(data.get("value"))

        self.is_inherited: bool | None = data.get("is_inherited", None)
        self.updated_at: str | None = data.get("updated_at", None)

        self.is_visible: bool | None = data.get("is_visible", None)
        self.is_protected: bool | None = data.get("is_protected", None)

        self.source: NodeProperty | None = None
        self.owner: NodeProperty | None = None

        for prop_name in self._properties_object:
            if data.get(prop_name):
                setattr(self, prop_name, NodeProperty(data=data.get(prop_name)))  # type: ignore[arg-type]

    @property
    def value(self) -> Any:
        return self._value

    @value.setter
    def value(self, value: Any) -> None:
        self._value = value
        self.value_has_been_mutated = True

    def _generate_input_data(self) -> dict | None:
        data: dict[str, Any] = {}
        variables: dict[str, Any] = {}

        if self.value is None:
            return data

        if isinstance(self.value, str):
            if SAFE_VALUE.match(self.value):
                data["value"] = self.value
            else:
                var_name = f"value_{UUIDT.new().hex}"
                variables[var_name] = self.value
                data["value"] = f"${var_name}"
        elif isinstance(self.value, get_args(IP_TYPES)):
            data["value"] = self.value.with_prefixlen
        elif isinstance(self.value, CoreNodeBase) and self.value.is_resource_pool():
            data["from_pool"] = {"id": self.value.id}
        else:
            data["value"] = self.value

        for prop_name in self._properties_flag:
            if getattr(self, prop_name) is not None:
                data[prop_name] = getattr(self, prop_name)

        for prop_name in self._properties_object:
            if getattr(self, prop_name) is not None:
                data[prop_name] = getattr(self, prop_name)._generate_input_data()

        return {"data": data, "variables": variables}

    def _generate_query_data(self, property: bool = False) -> dict | None:
        data: dict[str, Any] = {"value": None}

        if property:
            data.update({"is_default": None, "is_from_profile": None})

            for prop_name in self._properties_flag:
                data[prop_name] = None
            for prop_name in self._properties_object:
                data[prop_name] = {"id": None, "display_label": None, "__typename": None}

        return data

    def _generate_mutation_query(self) -> dict[str, Any]:
        if isinstance(self.value, CoreNodeBase) and self.value.is_resource_pool():
            # If it points to a pool, ask for the value of the pool allocated resource
            return {self.name: {"value": None}}
        return {}
