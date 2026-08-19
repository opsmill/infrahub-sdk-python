"""Unit tests for the schema drift-detection logic (offline)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from infrahub_sdk.ctl.schema_drift import (
    BASELINE_PATH,
    SCHEMA_URL,
    TRACKED_DEFINITIONS,
    compute_drift,
    extract_properties,
    fetch_live_properties,
    load_baseline,
    write_baseline,
)

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_httpx import HTTPXMock


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


def test_write_and_load_baseline_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    data = {"NodeSchema": ["name", "namespace"], "AttributeSchema": ["kind", "name"]}
    write_baseline(data, path)
    assert load_baseline(path) == data


def test_fetch_live_properties_extracts_from_response(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=SCHEMA_URL,
        json={"$defs": {"NodeSchema": {"properties": {"namespace": {}, "name": {}}}}},
    )
    props = fetch_live_properties()
    # Sorted names for the tracked definition; other tracked defs default to [].
    assert props["NodeSchema"] == ["name", "namespace"]
    assert props["RelationshipSchema"] == []
