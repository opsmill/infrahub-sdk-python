from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import jinja2

from .. import protocols as sdk_protocols
from ..schema import (
    AttributeSchemaAPI,
    GenericSchema,
    GenericSchemaAPI,
    MainSchemaTypesAll,
    NodeSchema,
    NodeSchemaAPI,
    ProfileSchemaAPI,
    RelationshipSchemaAPI,
    TemplateSchemaAPI,
)
from .constants import ATTRIBUTE_KIND_MAP, CORE_BASE_CLASS_TO_SYNCIFY, TEMPLATE_FILE_NAME


def load_template() -> str:
    path = Path(__file__).parent / TEMPLATE_FILE_NAME
    return path.read_text()


def move_to_end_of_list(lst: list, item: str) -> list:
    """Move an item to the end of a list if it exists in the list"""
    if item in lst:
        lst.remove(item)
        lst.append(item)
    return lst


class CodeGenerator:
    def __init__(self, schema: dict[str, MainSchemaTypesAll]):
        self.generics: dict[str, GenericSchemaAPI | GenericSchema] = {}
        self.nodes: dict[str, NodeSchemaAPI | NodeSchema] = {}
        self.profiles: dict[str, ProfileSchemaAPI] = {}
        self.templates: dict[str, TemplateSchemaAPI] = {}

        for name, schema_type in schema.items():
            if isinstance(schema_type, (GenericSchemaAPI, GenericSchema)):
                self.generics[name] = schema_type
            if isinstance(schema_type, (NodeSchemaAPI, NodeSchema)):
                self.nodes[name] = schema_type
            if isinstance(schema_type, ProfileSchemaAPI):
                self.profiles[name] = schema_type
            if isinstance(schema_type, TemplateSchemaAPI):
                self.templates[name] = schema_type

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
        self.sorted_templates = self._sort_and_filter_models(
            self.templates, filters=["CoreObjectTemplate"] + self.base_protocols
        )

    def render(self, sync: bool = True) -> str:
        jinja2_env = jinja2.Environment(loader=jinja2.BaseLoader(), trim_blocks=True, lstrip_blocks=True)
        jinja2_env.filters["render_attribute"] = self._jinja2_filter_render_attribute
        jinja2_env.filters["render_relationship"] = self._jinja2_filter_render_relationship
        jinja2_env.filters["syncify"] = self._jinja2_filter_syncify

        template = jinja2_env.from_string(load_template())
        return template.render(
            generics=self.sorted_generics,
            nodes=self.sorted_nodes,
            profiles=self.sorted_profiles,
            templates=self.sorted_templates,
            base_protocols=self.base_protocols,
            core_node_name="CoreNodeSync" if sync else "CoreNode",
            sync=sync,
        )

    @staticmethod
    def _jinja2_filter_syncify(value: str | list, sync: bool = False) -> str | list:
        """Filter to help with the convertion to sync

        If a string is provided, append Sync to the end of the string
        If a list is provided, search for CoreNode and replace it with CoreNodeSync
        """
        if isinstance(value, list):
            # Order the list based on the CORE_BASE_CLASS_TO_SYNCIFY list to ensure the base classes are always last
            for item in CORE_BASE_CLASS_TO_SYNCIFY:
                value = move_to_end_of_list(value, item)

        if not sync:
            return value

        if isinstance(value, str):
            return f"{value}Sync"

        if isinstance(value, list):
            return [f"{item}Sync" if item in CORE_BASE_CLASS_TO_SYNCIFY else item for item in value]

        return value

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
