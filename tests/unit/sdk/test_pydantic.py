from __future__ import annotations

from typing import ForwardRef, Optional

import pytest
from pydantic import BaseModel

from infrahub_sdk.schema.main import (
    AttributeKind,
    AttributeSchema,
    GenericSchema,
    NodeSchema,
    RelationshipSchema,
    SchemaState,
)
from infrahub_sdk.schema.pydantic_utils import (
    Attribute,
    GenericModel,
    InfrahubConfig,
    NodeModel,
    Relationship,
    SchemaModel,
    analyze_field,
    field_to_attribute,
    field_to_relationship,
    from_pydantic,
    get_attribute_kind,
    get_kind,
    model_to_node,
)


class MyAllInOneModel(NodeModel):
    name: str
    age: int
    is_active: bool
    opt_age: int | None = None
    default_name: str = "some_default"
    old_opt_age: Optional[int] = None


class AcmeTag(NodeModel):
    name: str = Attribute(default="test_tag", description="The name of the tag")
    description: str | None = Attribute(None, kind=AttributeKind.TEXTAREA)
    label: str = Attribute(unique=True, description="The label of the tag")


class AcmeCar(NodeModel):
    name: str
    tags: list[AcmeTag]
    owner: AcmePerson
    secondary_owner: AcmePerson | None = Relationship(peer="AcmePerson", optional=True)


class AcmePerson(NodeModel):
    name: str
    cars: list[AcmeCar] | None = None


# --------------------------------


class Book(NodeModel):
    model_config = InfrahubConfig(name="Book", namespace="Library", display_labels=["name__value"])

    title: str
    isbn: str = Attribute(..., unique=True)
    created_at: str
    author: LibraryAuthor


class AbstractPerson(GenericModel):
    model_config = InfrahubConfig(namespace="Library")
    firstname: str = Attribute(..., description="The first name of the person", pattern=r"^[a-zA-Z]+$")
    lastname: str


class LibraryAuthor(AbstractPerson):
    books: list[Book]


class LibraryReader(AbstractPerson):
    favorite_books: list[Book]
    favorite_authors: list[LibraryAuthor]


@pytest.mark.parametrize(
    "field_name, expected_kind",
    [
        pytest.param("name", "Text", id="name_field"),
        pytest.param("age", "Number", id="age_field"),
        pytest.param("is_active", "Boolean", id="is_active_field"),
        pytest.param("opt_age", "Number", id="opt_age_field"),
        pytest.param("default_name", "Text", id="default_name_field"),
        pytest.param("old_opt_age", "Number", id="old_opt_age_field"),
    ],
)
def test_get_field_kind(field_name, expected_kind):
    assert get_attribute_kind(MyAllInOneModel.model_fields[field_name]) == expected_kind


@pytest.mark.parametrize(
    "field_name, model, expected",
    [
        pytest.param(
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
            id="MyAllInOneModel_name",
        ),
        pytest.param(
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
            id="MyAllInOneModel_age",
        ),
        pytest.param(
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
            id="MyAllInOneModel_is_active",
        ),
        pytest.param(
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
            id="MyAllInOneModel_opt_age",
        ),
        pytest.param(
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
            id="MyAllInOneModel_default_name",
        ),
        pytest.param(
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
            id="MyAllInOneModel_old_opt_age",
        ),
        pytest.param(
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
            id="AcmeTag_description",
        ),
        pytest.param(
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
            id="AcmeTag_name",
        ),
        pytest.param(
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
            id="AcmeTag_label",
        ),
        pytest.param(
            "owner",
            AcmeCar,
            {
                "default": None,
                "is_attribute": False,
                "is_list": False,
                "is_relationship": True,
                "name": "owner",
                "optional": False,
                "primary_type": ForwardRef("AcmePerson"),
            },
            id="AcmeCar_owner",
        ),
        pytest.param(
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
            id="AcmeCar_tags",
        ),
        pytest.param(
            "secondary_owner",
            AcmeCar,
            {
                "default": None,
                "is_attribute": False,
                "is_list": False,
                "is_relationship": True,
                "name": "secondary_owner",
                "optional": True,
                "primary_type": "AcmePerson",
            },
            id="AcmeCar_secondary_owner",
        ),
    ],
)
def test_analyze_field(field_name: str, model: type[BaseModel], expected: dict):
    if field_name in model.model_fields:
        field = model.model_fields[field_name]
    elif issubclass(model, SchemaModel) and field_name in model.__infrahub_relationships__:
        field = model.__infrahub_relationships__[field_name]
    else:
        raise ValueError(f"Field {field_name} not found in model {model}")
    assert analyze_field(field_name=field_name, field=field).to_dict() == expected


@pytest.mark.parametrize(
    "field_name, model, expected",
    [
        pytest.param(
            "name",
            MyAllInOneModel,
            AttributeSchema(
                name="name",
                kind=AttributeKind.TEXT,
                optional=False,
            ),
            id="MyAllInOneModel_name",
        ),
        pytest.param(
            "age",
            MyAllInOneModel,
            AttributeSchema(
                name="age",
                kind=AttributeKind.NUMBER,
                optional=False,
            ),
            id="MyAllInOneModel_age",
        ),
        pytest.param(
            "is_active",
            MyAllInOneModel,
            AttributeSchema(
                name="is_active",
                kind=AttributeKind.BOOLEAN,
                optional=False,
            ),
            id="MyAllInOneModel_is_active",
        ),
        pytest.param(
            "opt_age",
            MyAllInOneModel,
            AttributeSchema(
                name="opt_age",
                kind=AttributeKind.NUMBER,
                optional=True,
            ),
            id="MyAllInOneModel_opt_age",
        ),
        pytest.param(
            "default_name",
            MyAllInOneModel,
            AttributeSchema(
                name="default_name",
                kind=AttributeKind.TEXT,
                optional=True,
                default_value="some_default",
            ),
            id="MyAllInOneModel_default_name",
        ),
        pytest.param(
            "old_opt_age",
            MyAllInOneModel,
            AttributeSchema(
                name="old_opt_age",
                kind=AttributeKind.NUMBER,
                optional=True,
            ),
            id="MyAllInOneModel_old_opt_age",
        ),
        pytest.param(
            "description",
            AcmeTag,
            AttributeSchema(
                name="description",
                kind=AttributeKind.TEXTAREA,
                optional=True,
            ),
            id="AcmeTag_description",
        ),
        pytest.param(
            "name",
            AcmeTag,
            AttributeSchema(
                name="name",
                description="The name of the tag",
                kind=AttributeKind.TEXT,
                optional=True,
                default_value="test_tag",
            ),
            id="AcmeTag_name",
        ),
        pytest.param(
            "label",
            AcmeTag,
            AttributeSchema(
                name="label",
                description="The label of the tag",
                kind=AttributeKind.TEXT,
                optional=False,
                unique=True,
            ),
            id="AcmeTag_label",
        ),
        pytest.param(
            "firstname",
            AbstractPerson,
            AttributeSchema(
                name="firstname",
                description="The first name of the person",
                kind=AttributeKind.TEXT,
                optional=False,
                regex=r"^[a-zA-Z]+$",
            ),
            id="AbstractPerson_firstname",
        ),
    ],
)
def test_field_to_attribute(field_name: str, model: type[BaseModel], expected: AttributeSchema):
    field = model.model_fields[field_name]
    field_info = analyze_field(field_name, field)
    assert field_to_attribute(field_name, field_info, field) == expected


@pytest.mark.parametrize(
    "field_name, model, expected",
    [
        pytest.param(
            "owner",
            AcmeCar,
            RelationshipSchema(
                name="owner",
                peer="AcmePerson",
                cardinality="one",
                optional=False,
            ),
            id="AcmeCar_owner",
        ),
        pytest.param(
            "tags",
            AcmeCar,
            RelationshipSchema(
                name="tags",
                peer="AcmeTag",
                cardinality="many",
                optional=False,
            ),
            id="AcmeCar_tags",
        ),
        pytest.param(
            "secondary_owner",
            AcmeCar,
            RelationshipSchema(
                name="secondary_owner",
                peer="AcmePerson",
                cardinality="one",
                optional=True,
            ),
            id="AcmeCar_secondary_owner",
        ),
    ],
)
def test_field_to_relationship(field_name: str, model: type[BaseModel | SchemaModel], expected: RelationshipSchema):
    if field_name in model.model_fields:
        field = model.model_fields[field_name]
    elif issubclass(model, SchemaModel) and field_name in model.__infrahub_relationships__:
        field = model.__infrahub_relationships__[field_name]
    else:
        raise ValueError(f"Field {field_name} not found in model {model}")
    field_info = analyze_field(field_name, field)
    assert field_to_relationship(field_name, field_info, field) == expected


@pytest.mark.parametrize(
    "model, expected",
    [
        pytest.param(MyAllInOneModel, "MyAllInOneModel", id="MyAllInOneModel"),
        pytest.param(Book, "LibraryBook", id="Book"),
        pytest.param(LibraryAuthor, "LibraryAuthor", id="LibraryAuthor"),
        pytest.param(LibraryReader, "LibraryReader", id="LibraryReader"),
        pytest.param(AbstractPerson, "LibraryAbstractPerson", id="AbstractPerson"),
        pytest.param(AcmeTag, "AcmeTag", id="AcmeTag"),
        pytest.param(AcmeCar, "AcmeCar", id="AcmeCar"),
        pytest.param(AcmePerson, "AcmePerson", id="AcmePerson"),
    ],
)
def test_get_kind(model: type[BaseModel], expected: str):
    assert get_kind(model) == expected


@pytest.mark.parametrize(
    "model, expected",
    [
        pytest.param(
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
            id="MyAllInOneModel",
        ),
        pytest.param(
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
            id="Book",
        ),
        pytest.param(
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
            id="LibraryAuthor",
        ),
        pytest.param(
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
            id="LibraryReader",
        ),
        pytest.param(
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
            id="AbstractPerson",
        ),
        pytest.param(
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
            id="AcmeTag",
        ),
    ],
)
def test_model_to_node(model: type[BaseModel], expected: NodeSchema):
    node = model_to_node(model)
    assert node == expected


def test_related_models():
    schemas = from_pydantic(models=[AcmePerson, AcmeCar, AcmeTag])
    assert len(schemas.nodes) == 3


# def test_library_models():
#     schemas = from_pydantic(models=[Book, AbstractPerson, LibraryAuthor, LibraryReader])
#     assert len(schemas.nodes) == 3
#     assert len(schemas.generics) == 1
