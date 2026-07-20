"""Detect drift between the Infrahub JSON schema and the formatter's baseline.

The canonical key ordering in :mod:`infrahub_sdk.ctl.schema_format` is written
against a known set of schema properties. When Infrahub adds, removes, or
renames a property in the published JSON schema
(https://schema.infrahub.app/infrahub/schema/latest.json), that ordering may
need updating so the new key lands in a sensible slot rather than being
preserved as an unrecognised key.

This module compares the live schema against a committed baseline
(``schema_properties.json``) and reports the difference. It backs the
``schema-drift-check`` invoke task (a warn-only CI step) and the
``schema-drift-update`` task that refreshes the baseline. It never raises on
drift — reporting is the caller's job.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from .schema_format import SCHEMA_URL

# The JSON-schema ``$defs`` whose property sets the formatter orders. Each maps
# to a canonical key list in ``schema_format`` (nodes/generics, attributes,
# relationships, dropdown choices, and node extensions).
TRACKED_DEFINITIONS = [
    "NodeSchema",
    "GenericSchema",
    "AttributeSchema",
    "RelationshipSchema",
    "DropdownChoice",
    "NodeExtensionSchema",
]

BASELINE_PATH = Path(__file__).parent / "schema_properties.json"


def extract_properties(schema: dict[str, Any]) -> dict[str, list[str]]:
    """Extract the sorted property names of each tracked definition.

    Args:
        schema: The parsed JSON schema document.

    Returns:
        A mapping of definition name to its sorted list of property names.

    """
    definitions = schema.get("$defs") or schema.get("definitions") or {}
    return {name: sorted(definitions.get(name, {}).get("properties", {})) for name in TRACKED_DEFINITIONS}


def fetch_live_properties(url: str = SCHEMA_URL, timeout: float = 30.0) -> dict[str, list[str]]:
    """Fetch the live JSON schema and return its tracked property sets.

    Args:
        url: The schema URL to fetch.
        timeout: Request timeout in seconds.

    Returns:
        A mapping of definition name to its sorted list of property names.

    Raises:
        httpx.HTTPError: If the schema cannot be fetched.

    """
    response = httpx.get(url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return extract_properties(response.json())


def load_baseline(path: Path = BASELINE_PATH) -> dict[str, list[str]]:
    """Load the committed baseline property sets."""
    return json.loads(path.read_text(encoding="utf-8"))


def write_baseline(properties: dict[str, list[str]], path: Path = BASELINE_PATH) -> None:
    """Write ``properties`` to the baseline file as sorted, indented JSON."""
    path.write_text(json.dumps(properties, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def compute_drift(live: dict[str, list[str]], baseline: dict[str, list[str]]) -> dict[str, dict[str, list[str]]]:
    """Compare live and baseline property sets.

    Args:
        live: Property sets from the live schema.
        baseline: Property sets from the committed baseline.

    Returns:
        A mapping of definition name to ``{"added": [...], "removed": [...]}``,
        containing only the definitions that changed.

    """
    drift: dict[str, dict[str, list[str]]] = {}
    for name in TRACKED_DEFINITIONS:
        live_set = set(live.get(name, []))
        baseline_set = set(baseline.get(name, []))
        added = sorted(live_set - baseline_set)
        removed = sorted(baseline_set - live_set)
        if added or removed:
            drift[name] = {"added": added, "removed": removed}
    return drift
