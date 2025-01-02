from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import jinja2

from . import protocols as sdk_protocols
from .ctl.constants import PROTOCOLS_TEMPLATE
from .schema import (
    AttributeSchemaAPI,
    GenericSchema,
    GenericSchemaAPI,
    MainSchemaTypesAll,
    NodeSchema,
    NodeSchemaAPI,
    ProfileSchemaAPI,
    RelationshipSchemaAPI,
)

ATTRIBUTE_KIND_MAP = {
    "ID": "String",
    "Text": "String",
    "TextArea": "String",
    "DateTime": "DateTime",
    "Email": "String",
    "Password": "String",
    "HashedPassword": "HashedPassword",
    "URL": "URL",
    "File": "String",
    "MacAddress": "MacAddress",
    "Color": "String",
    "Dropdown": "Dropdown",
    "Number": "Integer",
    "Bandwidth": "Integer",
    "IPHost": "IPHost",
    "IPNetwork": "IPNetwork",
    "Boolean": "Boolean",
    "Checkbox": "Boolean",
    "List": "ListAttribute",
    "JSON": "JSONAttribute",
    "Any": "AnyAttribute",
}


class CodeGenerator:
    def __init__(self, schema: dict[str, MainSchemaTypesAll]):
        self.generics: dict[str, GenericSchemaAPI | GenericSchema] = {}
        self.nodes: dict[str, NodeSchemaAPI | NodeSchema] = {}
        self.profiles: dict[str, ProfileSchemaAPI] = {}

        for name, schema_type in schema.items():
            if isinstance(schema_type, (GenericSchemaAPI, GenericSchema)):
                self.generics[name] = schema_type
            if isinstance(schema_type, (NodeSchemaAPI, NodeSchema)):
                self.nodes[name] = schema_type
            if isinstance(schema_type, ProfileSchemaAPI):
                self.profiles[name] = schema_type

        self.base_protocols = [
            e
            for e in dir(sdk_protocols)
            if not e.startswith("__")
            and not e.endswith("__")
            and e
            not in ("TYPE_CHECKING", "CoreNode", "Optional", "Protocol", "Union", "annotations", "runtime_checkable")
        ]

        self.sorted_generics = self._sort_and_filter_models(self.generics, filters=["CoreNode"] + self.base_protocols)
        self.sorted_nodes = self._sort_and_filter_models(self.nodes, filters=["CoreNode"] + self.base_protocols)
        self.sorted_profiles = self._sort_and_filter_models(
            self.profiles, filters=["CoreProfile"] + self.base_protocols
        )

    def render(self, sync: bool = True) -> str:
        jinja2_env = jinja2.Environment(loader=jinja2.BaseLoader(), trim_blocks=True, lstrip_blocks=True)
        jinja2_env.filters["inheritance"] = self._jinja2_filter_inheritance
        jinja2_env.filters["render_attribute"] = self._jinja2_filter_render_attribute
        jinja2_env.filters["render_relationship"] = self._jinja2_filter_render_relationship

        template = jinja2_env.from_string(PROTOCOLS_TEMPLATE)
        return template.render(
            generics=self.sorted_generics,
            nodes=self.sorted_nodes,
            profiles=self.sorted_profiles,
            base_protocols=self.base_protocols,
            sync=sync,
        )

    @staticmethod
    def _jinja2_filter_inheritance(value: dict[str, Any]) -> str:
        inherit_from: list[str] = value.get("inherit_from", [])

        if not inherit_from:
            return "CoreNode"
        return ", ".join(inherit_from)

    @staticmethod
    def _jinja2_filter_render_attribute(value: AttributeSchemaAPI) -> str:
        attribute_kind: str = ATTRIBUTE_KIND_MAP[value.kind]

        if value.optional:
            attribute_kind += "Optional"

        return f"{value.name}: {attribute_kind}"

    @staticmethod
    def _jinja2_filter_render_relationship(value: RelationshipSchemaAPI, sync: bool = False) -> str:
        name = value.name
        cardinality = value.cardinality

        type_ = "RelatedNode"
        if cardinality == "many":
            type_ = "RelationshipManager"

        if sync:
            type_ += "Sync"

        return f"{name}: {type_}"

    @staticmethod
    def _sort_and_filter_models(
        models: Mapping[str, MainSchemaTypesAll], filters: list[str] | None = None
    ) -> list[MainSchemaTypesAll]:
        if filters is None:
            filters = ["CoreNode"]

        filtered: list[MainSchemaTypesAll] = []
        for name, model in models.items():
            if name in filters:
                continue
            filtered.append(model)

        return sorted(filtered, key=lambda k: k.name)
