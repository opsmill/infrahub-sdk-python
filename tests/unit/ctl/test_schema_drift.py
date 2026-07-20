"""Unit tests for the schema drift-detection logic (offline)."""

from __future__ import annotations

import json

from infrahub_sdk.ctl.schema_drift import (
    BASELINE_PATH,
    TRACKED_DEFINITIONS,
    compute_drift,
    extract_properties,
    load_baseline,
)


def test_extract_properties_reads_defs() -> None:
    schema = {
        "$defs": {
            "NodeSchema": {"properties": {"name": {}, "namespace": {}}},
            "AttributeSchema": {"properties": {"kind": {}, "name": {}}},
        }
    }
    result = extract_properties(schema)

    # Every tracked definition is present; values are sorted; unknown defs empty.
    assert set(result) == set(TRACKED_DEFINITIONS)
    assert result["NodeSchema"] == ["name", "namespace"]
    assert result["AttributeSchema"] == ["kind", "name"]
    assert result["RelationshipSchema"] == []


def test_compute_drift_detects_added_and_removed() -> None:
    baseline = {"NodeSchema": ["name", "namespace", "label"]}
    live = {"NodeSchema": ["name", "namespace", "new_field"]}

    drift = compute_drift(live=live, baseline=baseline)

    assert drift == {"NodeSchema": {"added": ["new_field"], "removed": ["label"]}}


def test_compute_drift_empty_when_in_sync() -> None:
    props = {"NodeSchema": ["name", "namespace"]}
    assert compute_drift(live=props, baseline=props) == {}


def test_committed_baseline_is_valid_and_complete() -> None:
    baseline = load_baseline()
    # The shipped baseline covers exactly the tracked definitions and is JSON.
    assert set(baseline) == set(TRACKED_DEFINITIONS)
    assert all(isinstance(props, list) for props in baseline.values())
    # Round-trips through json (guards against a hand-edit breaking the file).
    assert json.loads(BASELINE_PATH.read_text(encoding="utf-8")) == baseline
