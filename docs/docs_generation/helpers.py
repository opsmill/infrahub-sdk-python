from __future__ import annotations

from collections import defaultdict
from typing import Any

from pydantic_settings import EnvSettingsSource

from infrahub_sdk.config import ConfigBase


def get_env_vars() -> dict[str, list[str]]:
    """Extract environment variable names for each field of ``ConfigBase``.

    Returns:
        Mapping of field name to list of upper-cased environment variable names.
    """
    env_vars: dict[str, list[str]] = defaultdict(list)
    settings = ConfigBase()
    env_settings = EnvSettingsSource(settings.__class__, env_prefix=settings.model_config.get("env_prefix", ""))

    for field_name, field in settings.model_fields.items():
        for field_key, field_env_name, _ in env_settings._extract_field_info(field, field_name):
            env_vars[field_key].append(field_env_name.upper())

    return env_vars


def _resolve_allof(prop: dict[str, Any], definitions: dict[str, Any]) -> tuple[list[Any], str]:
    """Resolve an ``allOf`` JSON Schema reference to extract enum choices and type."""
    if "allOf" not in prop:
        return [], ""
    ref_name = prop["allOf"][0]["$ref"].split("/")[-1]
    ref_def = definitions.get(ref_name, {})
    return ref_def.get("enum", []), ref_def.get("type", "")


def _resolve_anyof_type(prop: dict[str, Any]) -> str:
    """Resolve an ``anyOf`` to a comma-separated type string, excluding ``null``."""
    if "anyOf" not in prop:
        return ""
    return ", ".join(i["type"] for i in prop["anyOf"] if "type" in i and i["type"] != "null")


def build_config_properties() -> list[dict[str, Any]]:
    """Build the list of configuration properties for SDK config documentation.

    Returns:
        List of dicts with keys: ``name``, ``description``, ``type``,
        ``choices``, ``default``, ``env_vars``.
    """
    schema = ConfigBase.model_json_schema()
    env_vars = get_env_vars()
    definitions = schema.get("$defs", {})

    properties = []
    for name, prop in schema["properties"].items():
        choices, kind = _resolve_allof(prop, definitions)
        composed_type = _resolve_anyof_type(prop)

        properties.append(
            {
                "name": name,
                "description": prop.get("description", ""),
                "type": prop.get("type", kind) or composed_type or "object",
                "choices": choices,
                "default": prop.get("default", ""),
                "env_vars": env_vars.get(name, []),
            }
        )

    return properties
