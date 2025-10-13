from enum import Enum

from infrahub_sdk.graphql.query import Mutation, Query


class MyStrEnum(str, Enum):
    VALUE1 = "value1"
    VALUE2 = "value2"


class MyIntEnum(int, Enum):
    VALUE1 = 12
    VALUE2 = 24


def test_query_rendering_no_vars(query_data_no_filter) -> None:
    query = Query(query=query_data_no_filter)

    expected_query = """
query {
    device {
        name {
            value
        }
        description {
            value
        }
        interfaces {
            name {
                value
            }
        }
    }
}
"""
    assert query.render_first_line() == "query {"
    assert query.render() == expected_query


def test_query_rendering_empty_filter(query_data_empty_filter) -> None:
    query = Query(query=query_data_empty_filter)

    expected_query = """
query {
    device {
        name {
            value
        }
        description {
            value
        }
        interfaces {
            name {
                value
            }
        }
    }
}
"""
    assert query.render_first_line() == "query {"
    assert query.render() == expected_query


def test_query_rendering_with_filters_and_vars(query_data_filters_01) -> None:
    query = Query(query=query_data_filters_01, variables={"name": str, "enabled": bool})

    expected_query = """
query ($name: String!, $enabled: Boolean!) {
    device(name__value: $name) {
        name {
            value
        }
        description {
            value
        }
        interfaces(enabled__value: $enabled) {
            name {
                value
            }
        }
    }
}
"""
    assert query.render_first_line() == "query ($name: String!, $enabled: Boolean!) {"
    assert query.render() == expected_query


def test_query_rendering_with_filters(query_data_filters_02) -> None:
    query = Query(query=query_data_filters_02)

    expected_query = """
query {
    device(name__value: "myname", integer__value: 44, enumstr__value: VALUE2) {
        name {
            value
        }
        interfaces(enabled__value: true, enumint__value: VALUE1) {
            name {
                value
            }
        }
    }
}
"""
    assert query.render() == expected_query


def test_query_rendering_with_filters_convert_enum(query_data_filters_02) -> None:
    query = Query(query=query_data_filters_02)

    expected_query = """
query {
    device(name__value: "myname", integer__value: 44, enumstr__value: "value2") {
        name {
            value
        }
        interfaces(enabled__value: true, enumint__value: 12) {
            name {
                value
            }
        }
    }
}
"""
    assert query.render(convert_enum=True) == expected_query


def test_mutation_rendering_no_vars(input_data_01) -> None:
    query_data = {"ok": None, "object": {"id": None}}

    query = Mutation(mutation="myobject_create", query=query_data, input_data=input_data_01)

    expected_query = """
mutation {
    myobject_create(
        data: {
            name: {
                value: $name
            }
            some_number: {
                value: 88
            }
            some_bool: {
                value: true
            }
            some_list: {
                value: [
                    "value1",
                    33,
                ]
            }
            query: {
                value: "my_query"
            }
        }
    ){
        ok
        object {
            id
        }
    }
}
"""
    assert query.render_first_line() == "mutation {"
    assert query.render() == expected_query


def test_mutation_rendering_many_relationships() -> None:
    query_data = {"ok": None, "object": {"id": None}}
    input_data = {
        "data": {
            "description": {"value": "JFK Airport"},
            "name": {"value": "JFK1"},
            "tags": [
                {"id": "b44c6a7d-3b9c-466a-b6e3-a547b0ecc965"},
                {"id": "c5dffab1-e3f1-4039-9a1e-c0df1705d612"},
            ],
        }
    }

    query = Mutation(mutation="myobject_create", query=query_data, input_data=input_data)

    expected_query = """
mutation {
    myobject_create(
        data: {
            description: {
                value: "JFK Airport"
            }
            name: {
                value: "JFK1"
            }
            tags: [
                {
                    id: "b44c6a7d-3b9c-466a-b6e3-a547b0ecc965"
                },
                {
                    id: "c5dffab1-e3f1-4039-9a1e-c0df1705d612"
                },
            ]
        }
    ){
        ok
        object {
            id
        }
    }
}
"""
    assert query.render_first_line() == "mutation {"
    assert query.render() == expected_query


def test_mutation_rendering_enum() -> None:
    query_data = {"ok": None, "object": {"id": None}}
    input_data = {
        "data": {
            "description": {"value": MyStrEnum.VALUE1},
            "size": {"value": MyIntEnum.VALUE2},
        }
    }

    query = Mutation(mutation="myobject", query=query_data, input_data=input_data)

    expected_query = """
mutation {
    myobject(
        data: {
            description: {
                value: VALUE1
            }
            size: {
                value: VALUE2
            }
        }
    ){
        ok
        object {
            id
        }
    }
}
"""
    assert query.render_first_line() == "mutation {"
    assert query.render() == expected_query


def test_mutation_rendering_with_vars(input_data_01) -> None:
    query_data = {"ok": None, "object": {"id": None}}
    variables = {"name": str, "description": str, "number": int}
    query = Mutation(
        mutation="myobject_create",
        query=query_data,
        input_data=input_data_01,
        variables=variables,
    )

    expected_query = """
mutation ($name: String!, $description: String!, $number: Int!) {
    myobject_create(
        data: {
            name: {
                value: $name
            }
            some_number: {
                value: 88
            }
            some_bool: {
                value: true
            }
            some_list: {
                value: [
                    "value1",
                    33,
                ]
            }
            query: {
                value: "my_query"
            }
        }
    ){
        ok
        object {
            id
        }
    }
}
"""
    assert query.render_first_line() == "mutation ($name: String!, $description: String!, $number: Int!) {"
    assert query.render() == expected_query
