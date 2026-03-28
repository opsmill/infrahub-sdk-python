from __future__ import annotations

from typing import Any

import typer


def parse_set_args(set_args: list[str]) -> dict[str, str]:
    """Parse --set key=value arguments into a dictionary.

    Splits each argument on the first ``=`` sign, allowing values
    to contain additional ``=`` characters.

    Args:
        set_args: List of "key=value" strings from the CLI.

    Returns:
        Dictionary mapping field names to string values.

    Raises:
        typer.BadParameter: If any argument is not in key=value format.
    """
    result: dict[str, str] = {}
    for arg in set_args:
        if "=" not in arg:
            raise typer.BadParameter(f"Invalid format '{arg}'. Expected key=value.")
        key, value = arg.split("=", maxsplit=1)
        key = key.strip()
        if not key:
            raise typer.BadParameter(f"Invalid format '{arg}'. Key must not be empty.")
        result[key] = value
    return result


def parse_filter_args(filter_args: list[str]) -> dict[str, Any]:
    """Parse --filter arguments into kwargs for client.filters().

    Uses the same split-on-first-``=`` logic as :func:`parse_set_args`.
    Keys are expected to follow SDK filter conventions
    (e.g. ``attribute__value``, ``relationship__id``) but format
    validation is left to the SDK.

    Args:
        filter_args: List of "attr__value=x" strings from the CLI.

    Returns:
        Dictionary of filter kwargs to pass to client.filters().

    Raises:
        typer.BadParameter: If any argument is not in key=value format.
    """
    result: dict[str, Any] = {}
    for arg in filter_args:
        if "=" not in arg:
            raise typer.BadParameter(f"Invalid format '{arg}'. Expected key=value.")
        key, value = arg.split("=", maxsplit=1)
        key = key.strip()
        if not key:
            raise typer.BadParameter(f"Invalid format '{arg}'. Key must not be empty.")
        result[key] = value
    return result


def validate_set_fields(
    data: dict[str, str],
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
