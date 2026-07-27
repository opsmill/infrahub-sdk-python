"""Drift guard for the generated user-facing write/read schema models.

The SDK repo cannot regenerate these models on its own (they are rendered from the
backend's schema definitions), so this checks what the SDK can verify standalone:
the generated files are present, carry the do-not-edit header, expose the expected
model families, and satisfy the write/read structural invariants (write drops extra
fields silently; read is a superset of write). The full regeneration drift is enforced by the
monorepo's generated-file CI, which regenerates and fails on any diff.

The attribute family is a discriminated union on ``kind``: a shared ``AttributeSchemaBase``
carries every field except ``parameters``, and each variant narrows ``kind`` and adds its own
``parameters`` model. The public ``AttributeSchema{Write,Read}`` name is the union alias, so
class-level checks introspect the base and the variants rather than the alias.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from infrahub_sdk.schema import InfrahubSchemaRead, InfrahubSchemaWrite
from infrahub_sdk.schema.generated import enums as enums_module
from infrahub_sdk.schema.generated import read as read_module
from infrahub_sdk.schema.generated import write as write_module

if TYPE_CHECKING:
    from pydantic import BaseModel

_GENERATED_DIR = Path(write_module.__file__).parent
# Plain (non-union) families pair their write-variant class name with their read-variant class name.
_FAMILY_PAIRS = [
    ("RelationshipSchemaWrite", "RelationshipSchemaRead"),
    ("BaseNodeSchemaWrite", "BaseNodeSchemaRead"),
    ("NodeSchemaWrite", "NodeSchemaRead"),
    ("GenericSchemaWrite", "GenericSchemaRead"),
]
_WRITE_FAMILIES = [write for write, _ in _FAMILY_PAIRS]

# The attribute union's shared base plus its kind-discriminated variants (bare names; a variant's
# class is ``<name>Write`` / ``<name>Read``).
_ATTRIBUTE_BASE = "AttributeSchemaBase"
_ATTRIBUTE_VARIANTS = [
    "TextAttribute",
    "NumberAttribute",
    "ListAttribute",
    "NumberPoolAttribute",
    "GenericAttribute",
]


def _attribute_write_classes() -> list[type[BaseModel]]:
    return [getattr(write_module, _ATTRIBUTE_BASE + "Write")] + [
        getattr(write_module, variant + "Write") for variant in _ATTRIBUTE_VARIANTS
    ]


def _attribute_read_classes() -> list[type[BaseModel]]:
    return [getattr(read_module, _ATTRIBUTE_BASE + "Read")] + [
        getattr(read_module, variant + "Read") for variant in _ATTRIBUTE_VARIANTS
    ]


def _aggregate_fields(models: list[type[BaseModel]]) -> set[str]:
    fields: set[str] = set()
    for model in models:
        fields |= set(model.model_fields)
    return fields


@pytest.mark.parametrize("filename", ["write.py", "read.py"])
def test_generated_files_present_with_do_not_edit_header(filename: str) -> None:
    path = _GENERATED_DIR / filename
    assert path.is_file(), f"Generated schema model file is missing: {path}"
    assert "do not edit" in path.read_text().splitlines()[0].lower()


@pytest.mark.parametrize(("write_family", "read_family"), _FAMILY_PAIRS)
def test_expected_model_families_present_in_each_variant(write_family: str, read_family: str) -> None:
    assert hasattr(write_module, write_family), f"write variant is missing {write_family}"
    assert hasattr(read_module, read_family), f"read variant is missing {read_family}"


def test_attribute_union_families_present_in_each_variant() -> None:
    # The public union alias and every variant (plus the shared base) must exist in both variants.
    for name in ["AttributeSchema", _ATTRIBUTE_BASE, *_ATTRIBUTE_VARIANTS]:
        assert hasattr(write_module, name + "Write"), f"write variant is missing {name}Write"
        assert hasattr(read_module, name + "Read"), f"read variant is missing {name}Read"


@pytest.mark.parametrize("family", _WRITE_FAMILIES)
def test_write_variant_ignores_extra_fields(family: str) -> None:
    model: type[BaseModel] = getattr(write_module, family)
    assert model.model_config.get("extra") == "ignore", (
        f"write variant {family} must set extra='ignore' so non-settable fields are dropped, not rejected"
    )


def test_attribute_write_base_and_variants_ignore_extra_fields() -> None:
    for model in _attribute_write_classes():
        assert model.model_config.get("extra") == "ignore", (
            f"write attribute model {model.__name__} must set extra='ignore'"
        )


@pytest.mark.parametrize(("write_family", "read_family"), _FAMILY_PAIRS)
def test_read_variant_is_superset_of_write_variant(write_family: str, read_family: str) -> None:
    write_model: type[BaseModel] = getattr(write_module, write_family)
    read_model: type[BaseModel] = getattr(read_module, read_family)
    write_fields = set(write_model.model_fields)
    read_fields = set(read_model.model_fields)
    missing = write_fields - read_fields
    assert not missing, f"read variant {read_family} must expose every write field; missing: {sorted(missing)}"


def test_attribute_read_is_superset_of_attribute_write() -> None:
    # Aggregated across the base and every variant, read must expose every write field.
    write_fields = _aggregate_fields(_attribute_write_classes())
    read_fields = _aggregate_fields(_attribute_read_classes())
    missing = write_fields - read_fields
    assert not missing, f"read attribute variants must expose every write field; missing: {sorted(missing)}"


def test_write_variant_carries_read_level_fields_absent() -> None:
    # `inherited` is a read-level attribute field carried on the shared base; it must be absent on
    # the write base and present on the read base.
    write_base = getattr(write_module, _ATTRIBUTE_BASE + "Write")
    read_base = getattr(read_module, _ATTRIBUTE_BASE + "Read")
    assert "inherited" not in write_base.model_fields
    assert "inherited" in read_base.model_fields


def test_attribute_parameters_only_on_variants_not_base() -> None:
    # `parameters` is what the union discriminates, so it lives on the variants, not the base.
    write_base = getattr(write_module, _ATTRIBUTE_BASE + "Write")
    assert "parameters" not in write_base.model_fields
    for variant in _ATTRIBUTE_VARIANTS:
        model = getattr(write_module, variant + "Write")
        assert "parameters" in model.model_fields, f"{model.__name__} must carry a parameters field"


def test_document_root_models_import_with_nodes_and_generics() -> None:
    for root in (InfrahubSchemaWrite, InfrahubSchemaRead):
        assert "nodes" in root.model_fields, f"{root.__name__} must expose a 'nodes' field"
        assert "generics" in root.model_fields, f"{root.__name__} must expose a 'generics' field"
    # The write root drops unknown top-level keys silently (tolerated, not rejected).
    assert InfrahubSchemaWrite.model_config.get("extra") == "ignore"


def test_write_root_exposes_extensions_field() -> None:
    # Extensions are part of the write contract (write-only); the read root does not carry them.
    assert "extensions" in InfrahubSchemaWrite.model_fields
    assert "extensions" not in InfrahubSchemaRead.model_fields


@pytest.mark.parametrize("name", ["NodeExtensionWrite", "SchemaExtensionWrite"])
def test_extension_models_present_on_write_variant_only(name: str) -> None:
    assert hasattr(write_module, name), f"write variant is missing {name}"
    assert not hasattr(read_module, name.replace("Write", "Read")), (
        f"extension models are write-only; read variant must not define {name.replace('Write', 'Read')}"
    )


@pytest.mark.parametrize("name", ["NodeExtensionWrite", "SchemaExtensionWrite"])
def test_extension_models_ignore_extra_fields(name: str) -> None:
    model: type[BaseModel] = getattr(write_module, name)
    assert model.model_config.get("extra") == "ignore", f"extension model {name} must set extra='ignore'"


# Constrained fields are typed with dedicated (str, Enum) classes emitted into enums.py rather
# than inline Literals. Each generated enum's ordered values must match this contract.
_EXPECTED_ENUM_VALUES = {
    "BranchSupportType": ["aware", "agnostic", "local"],
    "RelationshipKind": ["Generic", "Attribute", "Component", "Parent", "Group", "Hierarchy", "Profile", "Template"],
    "RelationshipCardinality": ["one", "many"],
    "RelationshipDirection": ["bidirectional", "outbound", "inbound"],
    "RelationshipDeleteBehavior": ["no-action", "cascade"],
    "AllowOverrideType": ["none", "any"],
    "SchemaState": ["present", "absent"],
    "SchemaAttributeDisplay": ["default", "extra"],
    "ComputedAttributeKind": ["User", "Jinja2", "TransformPython"],
}


@pytest.mark.parametrize("enum_name", sorted(_EXPECTED_ENUM_VALUES))
def test_generated_enums_are_str_enum_classes_with_expected_values(enum_name: str) -> None:
    enum_cls = getattr(enums_module, enum_name)
    assert issubclass(enum_cls, Enum), f"{enum_name} must be an Enum class"
    assert issubclass(enum_cls, str), f"{enum_name} must be a str-backed enum"
    assert [member.value for member in enum_cls] == _EXPECTED_ENUM_VALUES[enum_name]


def test_attribute_kind_enum_present_without_deprecated_string_member() -> None:
    assert issubclass(enums_module.AttributeKind, Enum)
    assert issubclass(enums_module.AttributeKind, str)
    values = [member.value for member in enums_module.AttributeKind]
    # The deprecated "String" kind is dropped from the generated enum.
    assert "String" not in values
    assert "Text" in values


def test_constrained_fields_are_typed_with_generated_enums() -> None:
    # The constrained fields reference the dedicated enum classes, not inline Literals.
    assert (
        write_module.RelationshipSchemaWrite.model_fields["cardinality"].annotation
        is enums_module.RelationshipCardinality
    )
    assert write_module.RelationshipSchemaWrite.model_fields["kind"].annotation is enums_module.RelationshipKind
    assert write_module.AttributeSchemaBaseWrite.model_fields["kind"].annotation is enums_module.AttributeKind
    assert (
        read_module.RelationshipSchemaRead.model_fields["cardinality"].annotation
        is enums_module.RelationshipCardinality
    )


def test_use_enum_values_keeps_runtime_field_values_as_plain_strings() -> None:
    # use_enum_values means a constructed model stores the plain string, so equality against
    # both the raw string and the enum member holds and serialization is unchanged.
    # Passing the raw string is intentional here: the field is typed as the enum, but the point of
    # this test is that pydantic coerces a plain string at runtime, so the static complaint is expected.
    relationship = write_module.RelationshipSchemaWrite(name="interfaces", peer="InfraInterface", cardinality="one")  # ty: ignore[invalid-argument-type]
    assert relationship.cardinality == "one"
    assert relationship.cardinality == enums_module.RelationshipCardinality.ONE
    assert isinstance(relationship.cardinality, str)
    # Discriminates the mode: without use_enum_values the value would be a RelationshipCardinality
    # member (also a str, so the assertions above cannot tell the modes apart). A plain string is
    # not an instance of the enum, so this fails if use_enum_values is ever dropped on regeneration.
    assert not isinstance(relationship.cardinality, enums_module.RelationshipCardinality)


@pytest.mark.parametrize("name", ["ProfileSchemaRead", "TemplateSchemaRead"])
def test_profile_template_read_models_present_on_read_variant_only(name: str) -> None:
    # Profiles and templates are read-only projections; only the read variant defines them.
    model: type[BaseModel] = getattr(read_module, name)
    assert "inherit_from" in model.model_fields, f"{name} must expose an 'inherit_from' field"
    assert not hasattr(write_module, name.replace("Read", "Write")), (
        f"profile/template models are read-only; write variant must not define {name.replace('Read', 'Write')}"
    )
