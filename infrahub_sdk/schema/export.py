from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

from .generated.write import InfrahubSchemaWrite

if TYPE_CHECKING:
    from collections.abc import Mapping

EXPORT_ELEMENT_SECTIONS = ("generics", "nodes")


class SchemaExportMode(str, Enum):
    BRIEF = "BRIEF"
    """Leaves out the values that Infrahub derives again when the export is loaded."""

    FULL = "FULL"
    """Writes every value of the user-defined nodes and generics that a schema file can carry."""


class SchemaExportDocument(InfrahubSchemaWrite):
    """Schema file returned by the schema export endpoint, valid as a schema load payload."""

    infrahub_version: str


def split_by_namespace(document: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Split an exported schema, as the server returned it, into one document per namespace.

    Namespaces keep the order of the input. Each document holds every other top-level field of the input, and holds `generics` or `nodes` only
    when its namespace has some. Fields are copied as they are, including fields this SDK version does not know.
    """
    shared = {key: value for key, value in document.items() if key not in EXPORT_ELEMENT_SECTIONS}
    documents: dict[str, dict[str, Any]] = {}
    for section in EXPORT_ELEMENT_SECTIONS:
        for element in document.get(section, []):
            namespace_document = documents.setdefault(element["namespace"], dict(shared))
            namespace_document.setdefault(section, []).append(element)
    return documents
