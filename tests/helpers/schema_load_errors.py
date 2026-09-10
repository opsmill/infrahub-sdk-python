"""Builders and schema payloads shared by the tests of `infrahubctl schema load` error rendering.

Two payload shapes are covered by those tests:

- field-level: one entry per failing field, located on that field (`body/schemas/0/nodes/0/namespace`);
- schema-level (Infrahub 1.11.0+): one `value_error` entry per schema, located on the schema entry
  (`body/schemas/0`), whose message joins every violation as `<field path>: <message> (received: <value>)`
  separated by `; `.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.console import Console

from infrahub_sdk.ctl import schema as schema_module
from infrahub_sdk.ctl.schema import display_schema_load_errors
from infrahub_sdk.yaml import SchemaFile

if TYPE_CHECKING:
    import pytest

HEADER = "Unable to load the schema:\n"


def schema_files(*schemas: dict[str, Any]) -> list[SchemaFile]:
    return [SchemaFile(location=Path(f"schema-{index}.yml"), content=schema) for index, schema in enumerate(schemas)]


def schema_level_error(message: str, schema_index: int = 0, err_type: str = "value_error") -> dict[str, Any]:
    return {"type": err_type, "loc": ["body", "schemas", schema_index], "msg": message, "input": {}}


def field_level_error(
    loc: list[Any], msg: str = "Boom", err_type: str = "value_error", **extra: object
) -> dict[str, Any]:
    return {"type": err_type, "loc": loc, "msg": msg, **extra}


def make_console() -> tuple[Console, StringIO]:
    output = StringIO()
    return Console(file=output, width=1000), output


def render(errors: list[dict[str, Any]], *schemas: dict[str, Any]) -> str:
    console, output = make_console()
    display_schema_load_errors(response={"detail": errors}, schemas_data=schema_files(*schemas), output=console)
    return output.getvalue()


def capture_console(monkeypatch: pytest.MonkeyPatch) -> StringIO:
    """Replace the module console and return the buffer it writes to."""
    console, output = make_console()
    monkeypatch.setattr(schema_module, "console", console)
    return output


DEVICE = {
    "name": "Device",
    "namespace": "Infra",
    "attributes": [
        {"name": "serial", "kind": "Text", "parameters": {"regex": "["}},
        {"name": "status", "kind": "Dropdown", "choices": [{"name": "active"}, {"name": "x", "label": 1}]},
    ],
    "relationships": [{"name": "site", "peer": "LocationSite"}, {"name": "tags", "peer": "BuiltinTag"}],
    "display_labels": ["name__value"],
}
SPEED_ATTRIBUTE = {"name": "speed", "kind": "Number", "made_up": True}
TAG_EXTENSION = {"kind": "BuiltinTag", "attributes": [SPEED_ATTRIBUTE]}
SCHEMA = {"version": "1.0", "nodes": [DEVICE], "generics": [{"name": "Generic", "namespace": "Infra"}]}
EXTENSION_SCHEMA = {
    "version": "1.0",
    "extensions": {
        "nodes": [TAG_EXTENSION],
        "generics": [{"kind": "CoreNode", "label": 1}],
        "relationships": [{"name": "site", "peer": 1}],
    },
}
VALID_NODE = {"name": "Device", "namespace": "Infra", "attributes": [{"name": "name", "kind": "Text"}]}
VALID_SCHEMA = {"version": "1.0", "nodes": [VALID_NODE]}
OTHER_SCHEMA = {"version": "1.0", "nodes": [{"name": "Other", "namespace": "Test"}]}
# Rejected offline by `validate_schema`: lowercase namespace and a too-short attribute name.
INVALID_SCHEMA = {
    "version": "1.0",
    "nodes": [{"name": "Device", "namespace": "infra", "attributes": [{"name": "n", "kind": "Text"}]}],
}
