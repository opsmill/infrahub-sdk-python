from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import typer

if TYPE_CHECKING:
    from infrahub_sdk.schema import MainSchemaTypesAPI

_BOOLEAN_KEYWORDS = {"true": True, "yes": True, "false": False, "no": False}

# Filter suffixes whose GraphQL argument is always Boolean, whatever the attribute or relationship
_BOOLEAN_FILTER_SUFFIXES = ("__isnull", "__is_visible", "__is_protected")
_BOOLEAN_ATTRIBUTE_KINDS = {"Boolean", "Checkbox"}
_INTEGER_ATTRIBUTE_KINDS = {"Number", "NumberPool"}


def _coerce_value(value: str) -> Any:
    """Attempt to coerce a string value to an appropriate Python type.

    Tries, in order: JSON array (for relationship lists), int, float,
    bool (true/false), None (null/none).
    Falls back to the original string if no conversion matches.

    Args:
        value: The raw string value from the CLI.

    Returns:
        The coerced Python value.

    """
    # Try JSON array syntax (e.g. [["blue"], ["red"]] for cardinality-many)
    stripped = value.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass

    # Try integer (preserve leading zeros — "00123" stays a string)
    try:
        int_val = int(value)
        if str(int_val) == value:
            return int_val
    except ValueError:
        pass

    # Try float (preserve leading zeros)
    try:
        float_val = float(value)
        if str(float_val) == value:
            return float_val
    except ValueError:
        pass

    # Try boolean / null
    keyword_map = {**_BOOLEAN_KEYWORDS, "null": None, "none": None}
    lower = value.lower()
    if lower in keyword_map:
        return keyword_map[lower]

    return value


def parse_set_args(set_args: list[str]) -> dict[str, Any]:
    """Parse --set key=value arguments into a dictionary.

    Splits each argument on the first ``=`` sign, allowing values
    to contain additional ``=`` characters. Values are automatically
    coerced to int, float, bool, or None where possible.

    Args:
        set_args: List of "key=value" strings from the CLI.

    Returns:
        Dictionary mapping field names to coerced Python values.

    Raises:
        typer.BadParameter: If any argument is not in key=value format.

    """
    result: dict[str, Any] = {}
    for arg in set_args:
        if "=" not in arg:
            raise typer.BadParameter(f"Invalid format '{arg}'. Expected key=value.")
        key, value = arg.split("=", maxsplit=1)
        key = key.strip()
        if not key:
            raise typer.BadParameter(f"Invalid format '{arg}'. Key must not be empty.")
        result[key] = _coerce_value(value)
    return result


def _filter_value_type(key: str, schema: MainSchemaTypesAPI | None) -> type | None:
    """Return the Python type a filter's GraphQL argument expects, or None to keep it a string."""
    if key.endswith(_BOOLEAN_FILTER_SUFFIXES):
        return bool
    if schema is None or not key.endswith("__value"):
        return None
    attribute = schema.get_attribute_or_none(key.removesuffix("__value"))
    if attribute is None:
        return None
    if attribute.kind in _BOOLEAN_ATTRIBUTE_KINDS:
        return bool
    if attribute.kind in _INTEGER_ATTRIBUTE_KINDS:
        return int
    return None


def _convert_filter_value(key: str, value: str, schema: MainSchemaTypesAPI | None) -> Any:
    """Convert a --filter value to the type its GraphQL argument expects.

    Values for String, ID and other filters are returned unchanged, so
    ``name__value=123`` stays the string ``"123"``.

    Raises:
        typer.BadParameter: If the value cannot be converted to the expected type.

    """
    expected_type = _filter_value_type(key, schema)
    if expected_type is bool:
        lower = value.strip().lower()
        if lower not in _BOOLEAN_KEYWORDS:
            raise typer.BadParameter(f"Invalid value '{value}' for filter '{key}'. Expected true or false.")
        return _BOOLEAN_KEYWORDS[lower]
    if expected_type is int:
        try:
            return int(value)
        except ValueError:
            raise typer.BadParameter(f"Invalid value '{value}' for filter '{key}'. Expected an integer.") from None
    return value


def parse_filter_args(filter_args: list[str], schema: MainSchemaTypesAPI | None = None) -> dict[str, Any]:
    """Parse --filter arguments into kwargs for client.filters().

    Uses the same split-on-first-``=`` logic as :func:`parse_set_args`.
    Keys are expected to follow SDK filter conventions
    (e.g. ``attribute__value``, ``relationship__id``) but format
    validation is left to the SDK.

    Values are converted to the type the filter expects: ``__isnull``,
    ``__is_visible`` and ``__is_protected`` filters become booleans, and
    when ``schema`` is given, ``<attribute>__value`` filters on Boolean or
    Number attributes become booleans or integers. All other values stay
    strings.

    Args:
        filter_args: List of "attr__value=x" strings from the CLI.
        schema: Schema of the kind being queried, used to type attribute value filters.

    Returns:
        Dictionary of filter kwargs to pass to client.filters().

    Raises:
        typer.BadParameter: If any argument is not in key=value format,
            or a value cannot be converted to the type its filter expects.

    """
    result: dict[str, Any] = {}
    for arg in filter_args:
        if "=" not in arg:
            raise typer.BadParameter(f"Invalid format '{arg}'. Expected key=value.")
        key, value = arg.split("=", maxsplit=1)
        key = key.strip()
        if not key:
            raise typer.BadParameter(f"Invalid format '{arg}'. Key must not be empty.")
        result[key] = _convert_filter_value(key, value, schema)
    return result


def validate_set_fields(
    data: dict[str, Any],
    attribute_names: list[str],
    relationship_names: list[str],
) -> None:
    """Validate that all keys in data are valid attribute or relationship names.

    Args:
        data: Parsed set data from parse_set_args.
        attribute_names: Valid attribute names from schema.
        relationship_names: Valid relationship names from schema.

    Raises:
        typer.BadParameter: If any key is not a valid field name,
            with a message listing valid fields.

    """
    valid_fields = set(attribute_names) | set(relationship_names)
    invalid_keys = sorted(set(data.keys()) - valid_fields)
    if invalid_keys:
        valid_sorted = sorted(valid_fields)
        raise typer.BadParameter(
            f"Unknown field(s): {', '.join(invalid_keys)}. Valid fields: {', '.join(valid_sorted)}"
        )
