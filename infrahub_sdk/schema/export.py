from __future__ import annotations

from enum import Enum

from .generated.write import GenericSchemaWrite, InfrahubSchemaWrite, NodeSchemaWrite


class SchemaExportMode(str, Enum):
    BRIEF = "BRIEF"
    """Leaves out the values that Infrahub derives again when the export is loaded."""

    FULL = "FULL"
    """Writes every value of the user-defined nodes and generics that a schema file can carry."""


class SchemaExportDocument(InfrahubSchemaWrite):
    """Schema file returned by the schema export endpoint, valid as a schema load payload."""

    infrahub_version: str


def split_by_namespace(document: SchemaExportDocument) -> dict[str, SchemaExportDocument]:
    """Split an exported schema into one document per namespace, keeping the order of the input.

    A document only sets `generics` or `nodes` when its namespace has some, so a dump with
    `exclude_unset=True` leaves out an empty list.
    """
    generics: dict[str, list[GenericSchemaWrite]] = {}
    nodes: dict[str, list[NodeSchemaWrite]] = {}
    for generic in document.generics:
        generics.setdefault(generic.namespace, []).append(generic)
    for node in document.nodes:
        nodes.setdefault(node.namespace, []).append(node)

    documents: dict[str, SchemaExportDocument] = {}
    for namespace in [*generics, *nodes]:
        if namespace in documents:
            continue
        namespace_document = SchemaExportDocument(version=document.version, infrahub_version=document.infrahub_version)
        if namespace in generics:
            namespace_document.generics = generics[namespace]
        if namespace in nodes:
            namespace_document.nodes = nodes[namespace]
        documents[namespace] = namespace_document
    return documents
