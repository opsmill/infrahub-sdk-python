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

from infrahub_sdk.schema.generated import read as read_module
from infrahub_sdk.schema.generated import write as write_module

if TYPE_CHECKING:
    from pydantic import BaseModel

_GENERATED_DIR = Path(write_module.__file__).parent
_EXPECTED_FAMILIES = [
    "GeneratedAttributeSchema",
    "GeneratedRelationshipSchema",
    "GeneratedBaseNodeSchema",
    "GeneratedNodeSchema",
    "GeneratedGenericSchema",
]


@pytest.mark.parametrize("filename", ["write.py", "read.py"])
def test_generated_files_present_with_do_not_edit_header(filename: str) -> None:
    path = _GENERATED_DIR / filename
    assert path.is_file(), f"Generated schema model file is missing: {path}"
    assert "do not edit" in path.read_text().splitlines()[0].lower()


@pytest.mark.parametrize("family", _EXPECTED_FAMILIES)
def test_expected_model_families_present_in_both_variants(family: str) -> None:
    assert hasattr(write_module, family), f"write variant is missing {family}"
    assert hasattr(read_module, family), f"read variant is missing {family}"


@pytest.mark.parametrize("family", _EXPECTED_FAMILIES)
def test_write_variant_forbids_extra_fields(family: str) -> None:
    model: type[BaseModel] = getattr(write_module, family)
    assert model.model_config.get("extra") == "forbid", (
        f"write variant {family} must set extra='forbid' so non-settable fields are rejected"
    )


@pytest.mark.parametrize("family", _EXPECTED_FAMILIES)
def test_read_variant_is_superset_of_write_variant(family: str) -> None:
    write_model: type[BaseModel] = getattr(write_module, family)
    read_model: type[BaseModel] = getattr(read_module, family)
    write_fields = set(write_model.model_fields)
    read_fields = set(read_model.model_fields)
    missing = write_fields - read_fields
    assert not missing, f"read variant {family} must expose every write field; missing: {sorted(missing)}"


def test_write_variant_carries_read_level_fields_absent() -> None:
    # `inherited` is a read-level attribute field and must not exist on the write variant.
    assert "inherited" not in write_module.GeneratedAttributeSchema.model_fields
    assert "inherited" in read_module.GeneratedAttributeSchema.model_fields
