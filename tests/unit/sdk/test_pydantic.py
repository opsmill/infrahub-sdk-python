from __future__ import annotations

from typing import Annotated, Optional

import pytest
from pydantic import BaseModel, Field

from infrahub_sdk.schema.main import AttributeKind, AttributeSchema, RelationshipSchema
from infrahub_sdk.schema.pydantic_utils import (
    InfrahubAttributeParam as AttrParam,
)
from infrahub_sdk.schema.pydantic_utils import (
    analyze_field,
    field_to_attribute,
    field_to_relationship,
    from_pydantic,
    get_attribute_kind,
)


class MyModel(BaseModel):
    name: str
    age: int
    is_active: bool
    opt_age: int | None = None
    default_name: str = "some_default"
    old_opt_age: Optional[int] = None  # noqa: UP007


class Tag(BaseModel):
    name: str = Field(default="test_tag", description="The name of the tag")
    description: Annotated[str | None, AttrParam(kind=AttributeKind.TEXTAREA)] = None
    label: Annotated[str, AttrParam(unique=True), Field(description="The label of the tag")]


class Car(BaseModel):
    name: str
    tags: list[Tag]
    owner: Person
    secondary_owner: Person | None = None


class Person(BaseModel):
    name: str
    cars: list[Car] | None = None


@pytest.mark.parametrize(
    "field_name, expected_kind",
    [
        ("name", "Text"),
        ("age", "Number"),
        ("is_active", "Boolean"),
        ("opt_age", "Number"),
        ("default_name", "Text"),
        ("old_opt_age", "Number"),
    ],
)
def test_get_field_kind(field_name, expected_kind):
    assert get_attribute_kind(MyModel.model_fields[field_name]) == expected_kind


@pytest.mark.parametrize(
    "field_name, model, expected",
    [
        (
            "name",
            MyModel,
            {
                "default": None,
                "is_attribute": True,
                "is_list": False,
                "is_relationship": False,
                "name": "name",
                "optional": False,
                "primary_type": str,
            },
        ),
        (
            "age",
            MyModel,
            {
                "default": None,
                "is_attribute": True,
                "is_list": False,
                "is_relationship": False,
                "name": "age",
                "optional": False,
                "primary_type": int,
            },
        ),
        (
            "is_active",
            MyModel,
            {
                "default": None,
                "is_attribute": True,
                "is_list": False,
                "is_relationship": False,
                "name": "is_active",
                "optional": False,
                "primary_type": bool,
            },
        ),
        (
            "opt_age",
            MyModel,
            {
                "default": None,
                "is_attribute": True,
                "is_list": False,
                "is_relationship": False,
                "name": "opt_age",
                "optional": True,
                "primary_type": int,
            },
        ),
        (
            "default_name",
            MyModel,
            {
                "default": "some_default",
                "is_attribute": True,
                "is_list": False,
                "is_relationship": False,
                "name": "default_name",
                "optional": True,
                "primary_type": str,
            },
        ),
        (
            "old_opt_age",
            MyModel,
            {
                "default": None,
                "is_attribute": True,
                "is_list": False,
                "is_relationship": False,
                "name": "old_opt_age",
                "optional": True,
                "primary_type": int,
            },
        ),
        (
            "description",
            Tag,
            {
                "default": None,
                "is_attribute": True,
                "is_list": False,
                "is_relationship": False,
                "name": "description",
                "optional": True,
                "primary_type": str,
            },
        ),
        (
            "name",
            Tag,
            {
                "default": "test_tag",
                "is_attribute": True,
                "is_list": False,
                "is_relationship": False,
                "name": "name",
                "optional": True,
                "primary_type": str,
            },
        ),
        (
            "label",
            Tag,
            {
                "default": None,
                "is_attribute": True,
                "is_list": False,
                "is_relationship": False,
                "name": "label",
                "optional": False,
                "primary_type": str,
            },
        ),
        (
            "owner",
            Car,
            {
                "default": None,
                "is_attribute": False,
                "is_list": False,
                "is_relationship": True,
                "name": "owner",
                "optional": False,
                "primary_type": Person,
            },
        ),
        (
            "tags",
            Car,
            {
                "default": None,
                "is_attribute": False,
                "is_list": True,
                "is_relationship": True,
                "name": "tags",
                "optional": False,
                "primary_type": Tag,
            },
        ),
        (
            "secondary_owner",
            Car,
            {
                "default": None,
                "is_attribute": False,
                "is_list": False,
                "is_relationship": True,
                "name": "secondary_owner",
                "optional": True,
                "primary_type": Person,
            },
        ),
    ],
)
def test_analyze_field(field_name: str, model: BaseModel, expected: dict):
    assert analyze_field(field_name, model.model_fields[field_name]).to_dict() == expected


@pytest.mark.parametrize(
    "field_name, model, expected",
    [
        (
            "name",
            MyModel,
            AttributeSchema(
                name="name",
                kind=AttributeKind.TEXT,
                optional=False,
            ),
        ),
        (
            "age",
            MyModel,
            AttributeSchema(
                name="age",
                kind=AttributeKind.NUMBER,
                optional=False,
            ),
        ),
        (
            "is_active",
            MyModel,
            AttributeSchema(
                name="is_active",
                kind=AttributeKind.BOOLEAN,
                optional=False,
            ),
        ),
        (
            "opt_age",
            MyModel,
            AttributeSchema(
                name="opt_age",
                kind=AttributeKind.NUMBER,
                optional=True,
            ),
        ),
        (
            "default_name",
            MyModel,
            AttributeSchema(
                name="default_name",
                kind=AttributeKind.TEXT,
                optional=True,
                default="some_default",
            ),
        ),
        (
            "old_opt_age",
            MyModel,
            AttributeSchema(
                name="old_opt_age",
                kind=AttributeKind.NUMBER,
                optional=True,
            ),
        ),
        (
            "description",
            Tag,
            AttributeSchema(
                name="description",
                kind=AttributeKind.TEXTAREA,
                optional=True,
            ),
        ),
        (
            "name",
            Tag,
            AttributeSchema(
                name="name",
                description="The name of the tag",
                kind=AttributeKind.TEXT,
                optional=True,
            ),
        ),
        (
            "label",
            Tag,
            AttributeSchema(
                name="label",
                description="The label of the tag",
                kind=AttributeKind.TEXT,
                optional=False,
                unique=True,
            ),
        ),
    ],
)
def test_field_to_attribute(field_name: str, model: BaseModel, expected: AttributeSchema):
    field = model.model_fields[field_name]
    field_info = analyze_field(field_name, field)
    assert field_to_attribute(field_name, field_info, field) == expected


@pytest.mark.parametrize(
    "field_name, model, expected",
    [
        (
            "owner",
            Car,
            RelationshipSchema(
                name="owner",
                peer="TestingPerson",
                cardinality="one",
                optional=False,
            ),
        ),
        (
            "tags",
            Car,
            RelationshipSchema(
                name="tags",
                peer="TestingTag",
                cardinality="many",
                optional=False,
            ),
        ),
        (
            "secondary_owner",
            Car,
            RelationshipSchema(
                name="secondary_owner",
                peer="TestingPerson",
                cardinality="one",
                optional=True,
            ),
        ),
    ],
)
def test_field_to_relationship(field_name: str, model: BaseModel, expected: RelationshipSchema):
    field = model.model_fields[field_name]
    field_info = analyze_field(field_name, field)
    assert field_to_relationship(field_name, field_info, field) == expected


def test_related_models():
    schemas = from_pydantic(models=[Person, Car, Tag])
    assert len(schemas.nodes) == 3
