from __future__ import annotations

import json
from enum import Enum
from typing import Any

from pydantic import BaseModel

from .constants import VARIABLE_TYPE_MAPPING


def convert_to_graphql_as_string(value: Any, convert_enum: bool = False) -> str:  # noqa: PLR0911
    """Convert a Python value to its GraphQL string representation.

    This function handles various Python types and converts them to their appropriate
    GraphQL string format, including proper quoting, formatting, and special handling
    for different data types.

    Args:
        value: The value to convert to GraphQL string format. Can be None, str, bool,
            int, float, Enum, list, BaseModel, or any other type.
        convert_enum: If True, converts Enum values to their underlying value instead
            of their name. Defaults to False.

    Returns:
        str: The GraphQL string representation of the value.

    Examples:
        >>> convert_to_graphql_as_string("hello")
        '"hello"'
        >>> convert_to_graphql_as_string(True)
        'true'
        >>> convert_to_graphql_as_string([1, 2, 3])
        '[1, 2, 3]'
        >>> convert_to_graphql_as_string(None)
        'null'
    """
    if value is None:
        return "null"
    if isinstance(value, str) and value.startswith("$"):
        return value
    if isinstance(value, Enum):
        if convert_enum:
            return convert_to_graphql_as_string(value=value.value, convert_enum=True)
        return value.name
    if isinstance(value, str):
        # Use json.dumps() to properly escape the string according to JSON rules,
        # which are compatible with GraphQL string escaping
        return json.dumps(value)
    if isinstance(value, bool):
        return repr(value).lower()
    if isinstance(value, list):
        values_as_string = [convert_to_graphql_as_string(value=item, convert_enum=convert_enum) for item in value]
        return "[" + ", ".join(values_as_string) + "]"
    if isinstance(value, BaseModel):
        data = value.model_dump()
        return (
            "{ "
            + ", ".join(
                f"{key}: {convert_to_graphql_as_string(value=val, convert_enum=convert_enum)}"
                for key, val in data.items()
            )
            + " }"
        )

    return str(value)


def render_variables_to_string(data: dict[str, type[str | int | float | bool]]) -> str:
    """Render a dict into a variable string that will be used in a GraphQL Query.

    The $ sign will be automatically added to the name of the query.
    """
    vars_dict = {}
    for key, value in data.items():
        for class_type, var_string in VARIABLE_TYPE_MAPPING:
            if value == class_type:
                vars_dict[f"${key}"] = var_string

    return ", ".join([f"{key}: {value}" for key, value in vars_dict.items()])


def render_query_block(data: dict, offset: int = 4, indentation: int = 4, convert_enum: bool = False) -> list[str]:
    """Render a dictionary structure as a GraphQL query block with proper formatting.

    This function recursively processes a dictionary to generate GraphQL query syntax
    with proper indentation, handling of aliases, filters, and nested structures.
    Special keys like "@filters" and "@alias" are processed for GraphQL-specific
    formatting.

    Args:
        data: Dictionary representing the GraphQL query structure. Can contain
            nested dictionaries, special keys like "@filters" and "@alias", and
            various value types.
        offset: Number of spaces to use for initial indentation. Defaults to 4.
        indentation: Number of spaces to add for each nesting level. Defaults to 4.
        convert_enum: If True, converts Enum values to their underlying value.
            Defaults to False.

    Returns:
        list[str]: List of formatted lines representing the GraphQL query block.

    Examples:
        >>> data = {"user": {"name": None, "email": None}}
        >>> render_query_block(data)
        ['    user {', '        name', '        email', '    }']

        >>> data = {"user": {"@alias": "u", "@filters": {"id": 123}, "name": None}}
        >>> render_query_block(data)
        ['    u: user(id: 123) {', '        name', '    }']
    """
    FILTERS_KEY = "@filters"
    ALIAS_KEY = "@alias"
    KEYWORDS_TO_SKIP = [FILTERS_KEY, ALIAS_KEY]

    offset_str = " " * offset
    lines = []
    for key, value in data.items():
        if key in KEYWORDS_TO_SKIP:
            continue
        if value is None:
            lines.append(f"{offset_str}{key}")
        elif isinstance(value, dict) and len(value) == 1 and ALIAS_KEY in value and value[ALIAS_KEY]:
            lines.append(f"{offset_str}{value[ALIAS_KEY]}: {key}")
        elif isinstance(value, dict):
            if value.get(ALIAS_KEY):
                key_str = f"{value[ALIAS_KEY]}: {key}"
            else:
                key_str = key

            if value.get(FILTERS_KEY):
                filters_str = ", ".join(
                    [
                        f"{key2}: {convert_to_graphql_as_string(value=value2, convert_enum=convert_enum)}"
                        for key2, value2 in value[FILTERS_KEY].items()
                    ]
                )
                lines.append(f"{offset_str}{key_str}({filters_str}) " + "{")
            else:
                lines.append(f"{offset_str}{key_str} " + "{")

            lines.extend(
                render_query_block(
                    data=value, offset=offset + indentation, indentation=indentation, convert_enum=convert_enum
                )
            )
            lines.append(offset_str + "}")

    return lines


def render_input_block(data: dict, offset: int = 4, indentation: int = 4, convert_enum: bool = False) -> list[str]:
    """Render a dictionary structure as a GraphQL input block with proper formatting.

    This function recursively processes a dictionary to generate GraphQL input syntax
    with proper indentation, handling nested objects, arrays, and various data types.
    Unlike query blocks, input blocks don't handle special keys like "@filters" or
    "@alias" and focus on data structure representation.

    Args:
        data: Dictionary representing the GraphQL input structure. Can contain
            nested dictionaries, lists, and various value types.
        offset: Number of spaces to use for initial indentation. Defaults to 4.
        indentation: Number of spaces to add for each nesting level. Defaults to 4.
        convert_enum: If True, converts Enum values to their underlying value.
            Defaults to False.

    Returns:
        list[str]: List of formatted lines representing the GraphQL input block.

    Examples:
        >>> data = {"name": "John", "age": 30}
        >>> render_input_block(data)
        ['    name: "John"', '    age: 30']

        >>> data = {"user": {"name": "John", "hobbies": ["reading", "coding"]}}
        >>> render_input_block(data)
        ['    user: {', '        name: "John"', '        hobbies: [', '            "reading",', '            "coding",', '        ]', '    }']
    """
    offset_str = " " * offset
    lines = []
    for key, value in data.items():
        if isinstance(value, dict):
            lines.append(f"{offset_str}{key}: " + "{")
            lines.extend(
                render_input_block(
                    data=value, offset=offset + indentation, indentation=indentation, convert_enum=convert_enum
                )
            )
            lines.append(offset_str + "}")
        elif isinstance(value, list):
            lines.append(f"{offset_str}{key}: " + "[")
            for item in value:
                if isinstance(item, dict):
                    lines.append(f"{offset_str}{' ' * indentation}" + "{")
                    lines.extend(
                        render_input_block(
                            data=item,
                            offset=offset + indentation + indentation,
                            indentation=indentation,
                            convert_enum=convert_enum,
                        )
                    )
                    lines.append(f"{offset_str}{' ' * indentation}" + "},")
                else:
                    lines.append(
                        f"{offset_str}{' ' * indentation}{convert_to_graphql_as_string(value=item, convert_enum=convert_enum)},"
                    )
            lines.append(offset_str + "]")
        else:
            lines.append(f"{offset_str}{key}: {convert_to_graphql_as_string(value=value, convert_enum=convert_enum)}")
    return lines
