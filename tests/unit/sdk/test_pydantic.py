from __future__ import annotations

from typing import Annotated, Optional

import pytest
from pydantic import BaseModel, ConfigDict, Field

from infrahub_sdk.schema.main import (
    AttributeKind,
    AttributeSchema,
    GenericSchema,
    NodeSchema,
    RelationshipSchema,
    SchemaState,
)
from infrahub_sdk.schema.pydantic_utils import (
    GenericModel,
    NodeModel,
    analyze_field,
    field_to_attribute,
    field_to_relationship,
    from_pydantic,
    get_attribute_kind,
    get_kind,
    model_to_node,
)
from infrahub_sdk.schema.pydantic_utils import (
    InfrahubAttributeParam as AttrParam,
)


class MyAllInOneModel(BaseModel):
    name: str
    age: int
    is_active: bool
    opt_age: int | None = None
    default_name: str = "some_default"
    old_opt_age: Optional[int] = None  # noqa: UP007


class AcmeTag(BaseModel):
    name: str = Field(default="test_tag", description="The name of the tag")
    description: Annotated[str | None, AttrParam(kind=AttributeKind.TEXTAREA)] = None
    label: Annotated[str, AttrParam(unique=True), Field(description="The label of the tag")]


class AcmeCar(BaseModel):
    name: str
    tags: list[AcmeTag]
    owner: AcmePerson
    secondary_owner: AcmePerson | None = None


class AcmePerson(BaseModel):
    name: str
    cars: list[AcmeCar] | None = None


# --------------------------------


class Book(NodeModel):
    model_config = ConfigDict(node_schema=NodeSchema(name="Book", namespace="Library", display_labels=["name__value"]))
    title: str
    isbn: Annotated[str, AttrParam(unique=True)]
    created_at: str
    author: LibraryAuthor


class AbstractPerson(GenericModel):
    model_config = ConfigDict(generic_schema=GenericSchema(name="AbstractPerson", namespace="Library"))
    firstname: str = Field(..., description="The first name of the person", pattern=r"^[a-zA-Z]+$")
    lastname: str


class LibraryAuthor(AbstractPerson):
    books: list[Book]


class LibraryReader(AbstractPerson):
    favorite_books: list[Book]
    favorite_authors: list[LibraryAuthor]


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
    assert get_attribute_kind(MyAllInOneModel.model_fields[field_name]) == expected_kind


@pytest.mark.parametrize(
    "field_name, model, expected",
    [
        (
            "name",
            MyAllInOneModel,
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
            MyAllInOneModel,
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
            MyAllInOneModel,
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
            MyAllInOneModel,
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
            MyAllInOneModel,
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
            MyAllInOneModel,
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
            AcmeTag,
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
            AcmeTag,
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
            AcmeTag,
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
            AcmeCar,
            {
                "default": None,
                "is_attribute": False,
                "is_list": False,
                "is_relationship": True,
                "name": "owner",
                "optional": False,
                "primary_type": AcmePerson,
            },
        ),
        (
            "tags",
            AcmeCar,
            {
                "default": None,
                "is_attribute": False,
                "is_list": True,
                "is_relationship": True,
                "name": "tags",
                "optional": False,
                "primary_type": AcmeTag,
            },
        ),
        (
            "secondary_owner",
            AcmeCar,
            {
                "default": None,
                "is_attribute": False,
                "is_list": False,
                "is_relationship": True,
                "name": "secondary_owner",
                "optional": True,
                "primary_type": AcmePerson,
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
            MyAllInOneModel,
            AttributeSchema(
                name="name",
                kind=AttributeKind.TEXT,
                optional=False,
            ),
        ),
        (
            "age",
            MyAllInOneModel,
            AttributeSchema(
                name="age",
                kind=AttributeKind.NUMBER,
                optional=False,
            ),
        ),
        (
            "is_active",
            MyAllInOneModel,
            AttributeSchema(
                name="is_active",
                kind=AttributeKind.BOOLEAN,
                optional=False,
            ),
        ),
        (
            "opt_age",
            MyAllInOneModel,
            AttributeSchema(
                name="opt_age",
                kind=AttributeKind.NUMBER,
                optional=True,
            ),
        ),
        (
            "default_name",
            MyAllInOneModel,
            AttributeSchema(
                name="default_name",
                kind=AttributeKind.TEXT,
                optional=True,
                default_value="some_default",
            ),
        ),
        (
            "old_opt_age",
            MyAllInOneModel,
            AttributeSchema(
                name="old_opt_age",
                kind=AttributeKind.NUMBER,
                optional=True,
            ),
        ),
        (
            "description",
            AcmeTag,
            AttributeSchema(
                name="description",
                kind=AttributeKind.TEXTAREA,
                optional=True,
            ),
        ),
        (
            "name",
            AcmeTag,
            AttributeSchema(
                name="name",
                description="The name of the tag",
                kind=AttributeKind.TEXT,
                optional=True,
                default_value="test_tag",
            ),
        ),
        (
            "label",
            AcmeTag,
            AttributeSchema(
                name="label",
                description="The label of the tag",
                kind=AttributeKind.TEXT,
                optional=False,
                unique=True,
            ),
        ),
        (
            "firstname",
            AbstractPerson,
            AttributeSchema(
                name="firstname",
                description="The first name of the person",
                kind=AttributeKind.TEXT,
                optional=False,
                regex=r"^[a-zA-Z]+$",
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
            AcmeCar,
            RelationshipSchema(
                name="owner",
                peer="AcmePerson",
                cardinality="one",
                optional=False,
            ),
        ),
        (
            "tags",
            AcmeCar,
            RelationshipSchema(
                name="tags",
                peer="AcmeTag",
                cardinality="many",
                optional=False,
            ),
        ),
        (
            "secondary_owner",
            AcmeCar,
            RelationshipSchema(
                name="secondary_owner",
                peer="AcmePerson",
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


@pytest.mark.parametrize(
    "model, expected",
    [
        (MyAllInOneModel, "MyAllInOneModel"),
        (Book, "LibraryBook"),
        (LibraryAuthor, "LibraryAuthor"),
        (LibraryReader, "LibraryReader"),
        (AbstractPerson, "LibraryAbstractPerson"),
        (AcmeTag, "AcmeTag"),
        (AcmeCar, "AcmeCar"),
        (AcmePerson, "AcmePerson"),
    ],
)
def test_get_kind(model: BaseModel, expected: str):
    assert get_kind(model) == expected


@pytest.mark.parametrize(
    "model, expected",
    [
        (
            MyAllInOneModel,
            NodeSchema(
                name="AllInOneModel",
                namespace="My",
                state=SchemaState.PRESENT,
                attributes=[
                    AttributeSchema(name="name", kind=AttributeKind.TEXT, optional=False),
                    AttributeSchema(name="age", kind=AttributeKind.NUMBER, optional=False),
                    AttributeSchema(name="is_active", kind=AttributeKind.BOOLEAN, optional=False),
                    AttributeSchema(name="opt_age", kind=AttributeKind.NUMBER, optional=True),
                    AttributeSchema(
                        name="default_name", kind=AttributeKind.TEXT, optional=True, default_value="some_default"
                    ),
                    AttributeSchema(name="old_opt_age", kind=AttributeKind.NUMBER, optional=True),
                ],
            ),
        ),
        (
            Book,
            NodeSchema(
                name="Book",
                namespace="Library",
                display_labels=["name__value"],
                state=SchemaState.PRESENT,
                attributes=[
                    AttributeSchema(name="title", kind=AttributeKind.TEXT, optional=False),
                    AttributeSchema(name="isbn", kind=AttributeKind.TEXT, optional=False, unique=True),
                    AttributeSchema(name="created_at", kind=AttributeKind.TEXT, optional=False),
                ],
                relationships=[
                    RelationshipSchema(
                        name="author",
                        peer="LibraryAuthor",
                        cardinality="one",
                        optional=False,
                        relationships=[
                            RelationshipSchema(name="books", peer="LibraryBook", cardinality="many", optional=False),
                        ],
                    ),
                ],
            ),
        ),
        (
            LibraryAuthor,
            NodeSchema(
                name="Author",
                namespace="Library",
                inherit_from=["LibraryAbstractPerson"],
                state=SchemaState.PRESENT,
                relationships=[
                    RelationshipSchema(name="books", peer="LibraryBook", cardinality="many", optional=False),
                ],
            ),
        ),
        (
            LibraryReader,
            NodeSchema(
                name="Reader",
                namespace="Library",
                inherit_from=["LibraryAbstractPerson"],
                state=SchemaState.PRESENT,
                relationships=[
                    RelationshipSchema(name="favorite_books", peer="LibraryBook", cardinality="many", optional=False),
                    RelationshipSchema(
                        name="favorite_authors", peer="LibraryAuthor", cardinality="many", optional=False
                    ),
                ],
            ),
        ),
        (
            AbstractPerson,
            GenericSchema(
                name="AbstractPerson",
                namespace="Library",
                state=SchemaState.PRESENT,
                attributes=[
                    AttributeSchema(
                        name="firstname",
                        kind=AttributeKind.TEXT,
                        optional=False,
                        description="The first name of the person",
                        regex=r"^[a-zA-Z]+$",
                    ),
                    AttributeSchema(name="lastname", kind=AttributeKind.TEXT, optional=False),
                ],
            ),
        ),
        (
            AcmeTag,
            NodeSchema(
                name="Tag",
                namespace="Acme",
                state=SchemaState.PRESENT,
                attributes=[
                    AttributeSchema(
                        name="name",
                        kind=AttributeKind.TEXT,
                        default_value="test_tag",
                        optional=True,
                        description="The name of the tag",
                    ),
                    AttributeSchema(name="description", kind=AttributeKind.TEXTAREA, optional=True),
                    AttributeSchema(
                        name="label",
                        kind=AttributeKind.TEXT,
                        optional=False,
                        unique=True,
                        description="The label of the tag",
                    ),
                ],
            ),
        ),
    ],
)
def test_model_to_node(model: BaseModel, expected: NodeSchema):
    node = model_to_node(model)
    assert node == expected


def test_related_models():
    schemas = from_pydantic(models=[AcmePerson, AcmeCar, AcmeTag])
    assert len(schemas.nodes) == 3


def test_library_models():
    schemas = from_pydantic(models=[Book, AbstractPerson, LibraryAuthor, LibraryReader])
    assert len(schemas.nodes) == 3
    assert len(schemas.generics) == 1
