"""Drift guard for the generated user-facing write/read schema models.

The SDK repo cannot regenerate these models on its own (they are rendered from the
backend's schema definitions), so this checks what the SDK can verify standalone:
the generated files are present, carry the do-not-edit header, expose the expected
model families, and satisfy the write/read structural invariants (write forbids extra
fields; read is a superset of write). The full regeneration drift is enforced by the
monorepo's generated-file CI, which regenerates and fails on any diff.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from infrahub_sdk.schema import InfrahubSchemaRead, InfrahubSchemaWrite
from infrahub_sdk.schema.generated import read as read_module
from infrahub_sdk.schema.generated import write as write_module

if TYPE_CHECKING:
    from pydantic import BaseModel

_GENERATED_DIR = Path(write_module.__file__).parent
# Each family pairs its write-variant class name with its read-variant class name.
_FAMILY_PAIRS = [
    ("AttributeSchemaWrite", "AttributeSchemaRead"),
    ("RelationshipSchemaWrite", "RelationshipSchemaRead"),
    ("BaseNodeSchemaWrite", "BaseNodeSchemaRead"),
    ("NodeSchemaWrite", "NodeSchemaRead"),
    ("GenericSchemaWrite", "GenericSchemaRead"),
]
_WRITE_FAMILIES = [write for write, _ in _FAMILY_PAIRS]


@pytest.mark.parametrize("filename", ["write.py", "read.py"])
def test_generated_files_present_with_do_not_edit_header(filename: str) -> None:
    path = _GENERATED_DIR / filename
    assert path.is_file(), f"Generated schema model file is missing: {path}"
    assert "do not edit" in path.read_text().splitlines()[0].lower()


@pytest.mark.parametrize(("write_family", "read_family"), _FAMILY_PAIRS)
def test_expected_model_families_present_in_each_variant(write_family: str, read_family: str) -> None:
    assert hasattr(write_module, write_family), f"write variant is missing {write_family}"
    assert hasattr(read_module, read_family), f"read variant is missing {read_family}"


@pytest.mark.parametrize("family", _WRITE_FAMILIES)
def test_write_variant_forbids_extra_fields(family: str) -> None:
    model: type[BaseModel] = getattr(write_module, family)
    assert model.model_config.get("extra") == "forbid", (
        f"write variant {family} must set extra='forbid' so non-settable fields are rejected"
    )


@pytest.mark.parametrize(("write_family", "read_family"), _FAMILY_PAIRS)
def test_read_variant_is_superset_of_write_variant(write_family: str, read_family: str) -> None:
    write_model: type[BaseModel] = getattr(write_module, write_family)
    read_model: type[BaseModel] = getattr(read_module, read_family)
    write_fields = set(write_model.model_fields)
    read_fields = set(read_model.model_fields)
    missing = write_fields - read_fields
    assert not missing, f"read variant {read_family} must expose every write field; missing: {sorted(missing)}"


def test_write_variant_carries_read_level_fields_absent() -> None:
    # `inherited` is a read-level attribute field and must not exist on the write variant.
    assert "inherited" not in write_module.AttributeSchemaWrite.model_fields
    assert "inherited" in read_module.AttributeSchemaRead.model_fields


def test_document_root_models_import_with_nodes_and_generics() -> None:
    for root in (InfrahubSchemaWrite, InfrahubSchemaRead):
        assert "nodes" in root.model_fields, f"{root.__name__} must expose a 'nodes' field"
        assert "generics" in root.model_fields, f"{root.__name__} must expose a 'generics' field"
    # The write root is not extra=forbid so schema-level keys outside the model are tolerated.
    assert InfrahubSchemaWrite.model_config.get("extra") != "forbid"
