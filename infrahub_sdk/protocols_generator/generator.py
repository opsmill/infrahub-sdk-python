from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import jinja2
from typing_extensions import assert_never

from .. import protocols as sdk_protocols
from ..schema import (
    AttributeSchemaAPI,
    GenericSchema,
    GenericSchemaAPI,
    MainSchemaTypesAll,
    NodeSchema,
    NodeSchemaAPI,
    ProfileSchemaAPI,
    RelationshipCardinality,
    RelationshipSchemaAPI,
    TemplateSchemaAPI,
)
from .constants import ATTRIBUTE_KIND_MAP, CORE_BASE_CLASS_TO_SYNCIFY, HEADER_FILE_NAME, TEMPLATE_FILE_NAME
from .target import ProtocolTarget


def load_template(file_name: str = TEMPLATE_FILE_NAME) -> str:
    path = Path(__file__).parent / file_name
    return path.read_text()


def move_to_end_of_list(lst: list, item: str) -> list:
    """Move an item to the end of a list if it exists in the list."""
    if item in lst:
        lst.remove(item)
        lst.append(item)
    return lst


class CodeGenerator:
    def __init__(
        self, schema: dict[str, MainSchemaTypesAll], target: ProtocolTarget = ProtocolTarget.USER_SCHEMA
    ) -> None:
        self.target: ProtocolTarget = target
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

        match self.target:
            case ProtocolTarget.USER_SCHEMA:
                self.base_protocols = [
                    e
                    for e in dir(sdk_protocols)
                    if not e.startswith("__")
                    and not e.endswith("__")
                    and e
                    not in {
                        "TYPE_CHECKING",
                        "CoreNode",
                        "Optional",
                        "Protocol",
                        "Union",
                        "annotations",
                        "runtime_checkable",
                    }
                ]
            case ProtocolTarget.SDK_CORE:
                # Nothing can be imported from the module being generated.
                self.base_protocols = []
            case _:
                assert_never(self.target)

        self.sorted_generics = self._sort_and_filter_models(self.generics, filters=["CoreNode", *self.base_protocols])
        self.sorted_nodes = self._sort_and_filter_models(self.nodes, filters=["CoreNode", *self.base_protocols])
        self.sorted_profiles = self._sort_and_filter_models(
            self.profiles, filters=["CoreProfile", *self.base_protocols]
        )
        self.sorted_templates = self._sort_and_filter_models(
            self.templates, filters=["CoreObjectTemplate", *self.base_protocols]
        )

        # Which referenced names have a Sync counterpart to switch to when rendering sync output.
        # The two positions resolve names differently for a user schema: a peer may be any core
        # kind, while an inheritance list only ever switches the few base classes. Generating the
        # core module makes both the same, since every class in it is local.
        match self.target:
            case ProtocolTarget.USER_SCHEMA:
                self._inherited_sync_names = frozenset(CORE_BASE_CLASS_TO_SYNCIFY)
                self._peer_sync_names = frozenset(
                    name for name in self.base_protocols if f"{name}Sync" in self.base_protocols
                )
            case ProtocolTarget.SDK_CORE:
                local_names = self._local_class_names() | {"CoreNode"}
                self._inherited_sync_names = local_names
                self._peer_sync_names = local_names
            case _:
                assert_never(self.target)

    def render(self, sync: bool = True) -> str:
        """Render the protocols module.

        ``sync`` selects which variant to render for ``USER_SCHEMA``. ``SDK_CORE`` renders both
        variants into a single module, so it does not apply there.
        """
        jinja2_env = jinja2.Environment(
            loader=jinja2.BaseLoader(),
            trim_blocks=True,
            lstrip_blocks=True,
            autoescape=False,  # noqa: S701
        )
        jinja2_env.filters["render_attribute"] = self._jinja2_filter_render_attribute
        jinja2_env.filters["render_relationship"] = self._jinja2_filter_render_relationship
        jinja2_env.filters["syncify"] = self._jinja2_filter_syncify

        header = jinja2_env.from_string(load_template(HEADER_FILE_NAME))
        body = jinja2_env.from_string(load_template(TEMPLATE_FILE_NAME))

        match self.target:
            case ProtocolTarget.USER_SCHEMA:
                return header.render(sync=sync, base_protocols=self.base_protocols, core=False) + self._render_body(
                    body, sync=sync, suffix=""
                )
            case ProtocolTarget.SDK_CORE:
                return (
                    header.render(sync=False, base_protocols=self.base_protocols, core=True)
                    + self._render_body(body, sync=False, suffix="")
                    + self._render_body(body, sync=True, suffix="Sync")
                )
            case _:
                assert_never(self.target)

    def _render_body(self, body: jinja2.Template, sync: bool, suffix: str) -> str:
        return body.render(
            generics=self.sorted_generics,
            nodes=self.sorted_nodes,
            profiles=self.sorted_profiles,
            templates=self.sorted_templates,
            core_node_name="CoreNodeSync" if sync else "CoreNode",
            sync=sync,
            suffix=suffix,
        )

    def _local_class_names(self) -> frozenset[str]:
        return frozenset(
            f"{model.namespace}{model.name}"
            for model in (*self.sorted_generics, *self.sorted_nodes, *self.sorted_profiles, *self.sorted_templates)
        )

    def _jinja2_filter_syncify(self, value: str | list, sync: bool = False) -> str | list:
        """Filter to help with the convertion to sync.

        If a string is provided, append Sync to the end of the string
        If a list is provided, append Sync to the items that have a Sync counterpart
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
            return [f"{item}Sync" if item in self._inherited_sync_names else item for item in value]

        return value

    @staticmethod
    def _jinja2_filter_render_attribute(value: AttributeSchemaAPI) -> str:
        attribute_kind: str = ATTRIBUTE_KIND_MAP[value.kind]

        if value.optional and value.default_value is None:
            attribute_kind += "Optional"

        return f"{value.name}: {attribute_kind}"

    def _jinja2_filter_render_relationship(self, value: RelationshipSchemaAPI, sync: bool = False) -> str:
        name = value.name
        cardinality = value.cardinality
        peer = value.peer

        # Cardinality-one relationships use a descriptor so they can be assigned an id string,
        # an HFID, a peer node or ``None`` while still reading back as a typed ``RelatedNode``.
        type_ = "RelationshipAttribute"
        if cardinality == RelationshipCardinality.MANY:
            type_ = "RelationshipManager"

        if sync:
            type_ += "Sync"
            # Peers with a dedicated ``*Sync`` variant are referenced by it in sync output. The
            # rest keep their name, because they already are the sync class.
            if peer in self._peer_sync_names:
                peer = f"{peer}Sync"

        return f"{name}: {type_}[{peer}]"

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

        # Sorted on the kind, which is the name each class renders as. Case is ignored so the file
        # reads in alphabetical order, with the kind itself breaking ties: a key that can compare
        # two kinds equal would leave them ordered by however the caller supplied them.
        return sorted(filtered, key=lambda k: (k.kind.lower(), k.kind))
