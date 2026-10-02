"""Tests for how the SDK reports reads of node fields it never fetched."""

from __future__ import annotations

import asyncio
import inspect
import re
import types
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

import infrahub_sdk
from infrahub_sdk.exceptions import FieldNotLoadedError, FieldNotLoadedWarning
from infrahub_sdk.node import field_access
from infrahub_sdk.node.field_access import (
    build_unloaded_message,
    internal_field_access,
    report_unloaded_read,
    with_internal_field_access,
)
from infrahub_sdk.node.selection import Selection

if TYPE_CHECKING:
    from collections.abc import Callable

WARNING_SUFFIX = " This will raise FieldNotLoadedError in infrahub-sdk 2.0."

EXCLUDE_SELECTION = Selection.from_args(include=None, exclude=["description"], only=None)
EXCLUDE_MESSAGE = (
    "InfraDevice.description was not fetched (selection: exclude=['description']). "
    "Add it to the selection, or call fetch(), before reading it."
)
ONLY_SELECTION = Selection.from_args(include=None, exclude=None, only=["name"])
ONLY_MESSAGE = (
    "InfraDevice.description was not fetched (selection: only=['name']). "
    "Add it to the selection, or call fetch(), before reading it."
)
PEER_FLOOR_SELECTION = Selection.for_peer(
    parent=Selection.from_args(include=None, exclude=None, only=["site"]),
    parent_kind="InfraDevice",
    rel_name="site",
    peer_floor=True,
)
PEER_FLOOR_MESSAGE = (
    "InfraSite.description was not fetched: this node only carries the identity floor "
    "(peer of InfraDevice.site). Hydrate it with fetch(only=[...]) before reading it."
)
UNKNOWN_ORIGIN_MESSAGE = (
    "InfraDevice.description is not known to the SDK (origin unknown). "
    "Fetch the node with a selection that includes it before reading it."
)


def _relocate_into_sdk(func: Callable[[], None]) -> Callable[[], None]:
    """Return a copy of ``func`` whose frames report a file inside the infrahub_sdk package."""
    assert isinstance(func, types.FunctionType)
    sdk_file = Path(infrahub_sdk.__file__).parent / "node" / "simulated_accessor.py"
    code = func.__code__.replace(co_filename=str(sdk_file))
    return types.FunctionType(code, func.__globals__, func.__name__, func.__defaults__, func.__closure__)


def _read_description() -> None:
    report_unloaded_read("InfraDevice", "description", None, strict=False)


def _access_description() -> None:
    sdk_read_description()


# Stand-ins for a field accessor calling into the node, which then calls report_unloaded_read.
sdk_read_description = _relocate_into_sdk(_read_description)
sdk_access_description = _relocate_into_sdk(_access_description)


@dataclass
class MessageCase:
    name: str
    kind: str
    selection: Selection | None
    expected: str


MESSAGE_CASES = [
    MessageCase(name="sdk-selection", kind="InfraDevice", selection=EXCLUDE_SELECTION, expected=EXCLUDE_MESSAGE),
    MessageCase(name="only-selection", kind="InfraDevice", selection=ONLY_SELECTION, expected=ONLY_MESSAGE),
    MessageCase(name="peer-floor", kind="InfraSite", selection=PEER_FLOOR_SELECTION, expected=PEER_FLOOR_MESSAGE),
    MessageCase(name="origin-unknown", kind="InfraDevice", selection=None, expected=UNKNOWN_ORIGIN_MESSAGE),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in MESSAGE_CASES])
def test_build_unloaded_message(case: MessageCase) -> None:
    assert build_unloaded_message(case.kind, "description", case.selection) == case.expected


def test_report_unloaded_read_warns_with_suffix_at_caller() -> None:
    with pytest.warns(FieldNotLoadedWarning) as record:
        report_unloaded_read("InfraDevice", "description", EXCLUDE_SELECTION, strict=False)

    assert len(record) == 1
    assert type(record[0].message) is FieldNotLoadedWarning
    assert str(record[0].message) == EXCLUDE_MESSAGE + WARNING_SUFFIX
    assert record[0].filename == __file__


def test_report_unloaded_read_warning_skips_every_sdk_frame() -> None:
    with pytest.warns(FieldNotLoadedWarning) as record:
        sdk_access_description()

    assert len(record) == 1
    assert str(record[0].message) == UNKNOWN_ORIGIN_MESSAGE + WARNING_SUFFIX
    assert record[0].filename == __file__


@dataclass
class StrictCase:
    name: str
    kind: str
    selection: Selection | None
    expected_message: str
    expected_label: str | None


STRICT_CASES = [
    StrictCase(
        name="sdk-selection",
        kind="InfraDevice",
        selection=EXCLUDE_SELECTION,
        expected_message=EXCLUDE_MESSAGE,
        expected_label="exclude=['description']",
    ),
    StrictCase(
        name="only-selection",
        kind="InfraDevice",
        selection=ONLY_SELECTION,
        expected_message=ONLY_MESSAGE,
        expected_label="only=['name']",
    ),
    StrictCase(
        name="peer-floor",
        kind="InfraSite",
        selection=PEER_FLOOR_SELECTION,
        expected_message=PEER_FLOOR_MESSAGE,
        expected_label="peer of InfraDevice.site, fetched with only=['site']",
    ),
    StrictCase(
        name="origin-unknown",
        kind="InfraDevice",
        selection=None,
        expected_message=UNKNOWN_ORIGIN_MESSAGE,
        expected_label=None,
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in STRICT_CASES])
def test_report_unloaded_read_raises_when_switch_is_on(monkeypatch: pytest.MonkeyPatch, case: StrictCase) -> None:
    monkeypatch.setattr(field_access, "_STRICT_FIELD_ACCESS", True)

    with pytest.raises(FieldNotLoadedError, match=f"^{re.escape(case.expected_message)}$") as excinfo:
        report_unloaded_read(case.kind, "description", case.selection, strict=False)

    assert excinfo.value.kind == case.kind
    assert excinfo.value.field == "description"
    assert excinfo.value.selection == case.expected_label
    assert excinfo.value.message == case.expected_message


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in STRICT_CASES])
def test_report_unloaded_read_raises_for_strict_node(case: StrictCase) -> None:
    with pytest.raises(FieldNotLoadedError, match=f"^{re.escape(case.expected_message)}$") as excinfo:
        report_unloaded_read(case.kind, "description", case.selection, strict=True)

    assert excinfo.value.kind == case.kind
    assert excinfo.value.field == "description"
    assert excinfo.value.selection == case.expected_label
    assert excinfo.value.message == case.expected_message


def test_internal_field_access_context_manager_silences_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    with warnings.catch_warnings(record=True) as record:
        warnings.simplefilter("always")
        with internal_field_access():
            report_unloaded_read("InfraDevice", "description", EXCLUDE_SELECTION, strict=False)
            report_unloaded_read("InfraDevice", "description", EXCLUDE_SELECTION, strict=True)
            monkeypatch.setattr(field_access, "_STRICT_FIELD_ACCESS", True)
            report_unloaded_read("InfraDevice", "description", None, strict=False)

    assert record == []
    with pytest.raises(FieldNotLoadedError, match=re.escape(UNKNOWN_ORIGIN_MESSAGE)):
        report_unloaded_read("InfraDevice", "description", None, strict=False)


def test_internal_field_access_restores_outer_state_when_nested() -> None:
    with internal_field_access():
        with internal_field_access():
            report_unloaded_read("InfraDevice", "description", None, strict=True)
        report_unloaded_read("InfraDevice", "description", None, strict=True)

    with pytest.raises(FieldNotLoadedError, match=re.escape(UNKNOWN_ORIGIN_MESSAGE)):
        report_unloaded_read("InfraDevice", "description", None, strict=True)


def test_internal_field_access_is_reset_when_the_block_raises() -> None:
    def fail_inside() -> None:
        with internal_field_access():
            raise KeyError("boom")

    with pytest.raises(KeyError, match="boom"):
        fail_inside()

    with pytest.raises(FieldNotLoadedError, match=re.escape(UNKNOWN_ORIGIN_MESSAGE)):
        report_unloaded_read("InfraDevice", "description", None, strict=True)


def test_with_internal_field_access_on_sync_function() -> None:
    @with_internal_field_access
    def read_internally(field: str) -> str:
        report_unloaded_read("InfraDevice", field, None, strict=True)
        return f"read {field}"

    assert read_internally.__name__ == "read_internally"
    assert not inspect.iscoroutinefunction(read_internally)
    assert read_internally("description") == "read description"
    with pytest.raises(FieldNotLoadedError, match=re.escape(UNKNOWN_ORIGIN_MESSAGE)):
        report_unloaded_read("InfraDevice", "description", None, strict=True)


async def test_with_internal_field_access_on_coroutine_function() -> None:
    @with_internal_field_access
    async def read_internally(field: str) -> str:
        await asyncio.sleep(0)
        report_unloaded_read("InfraDevice", field, None, strict=True)
        with warnings.catch_warnings(record=True) as record:
            warnings.simplefilter("always")
            report_unloaded_read("InfraDevice", field, None, strict=False)
        assert record == []
        return f"read {field}"

    assert read_internally.__name__ == "read_internally"
    assert inspect.iscoroutinefunction(read_internally)
    assert await read_internally("description") == "read description"
    with pytest.raises(FieldNotLoadedError, match=re.escape(UNKNOWN_ORIGIN_MESSAGE)):
        report_unloaded_read("InfraDevice", "description", None, strict=True)


async def test_internal_field_access_does_not_leak_into_concurrent_tasks() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    @with_internal_field_access
    async def hold_internal_access() -> None:
        entered.set()
        await release.wait()

    holder = asyncio.create_task(hold_internal_access())
    await entered.wait()
    try:
        with pytest.raises(FieldNotLoadedError, match=re.escape(UNKNOWN_ORIGIN_MESSAGE)):
            report_unloaded_read("InfraDevice", "description", None, strict=True)
    finally:
        release.set()
        await holder


def test_reports_from_one_call_site_are_deduplicated() -> None:
    with warnings.catch_warnings(record=True) as record:
        warnings.simplefilter("default")
        # A loop over two nodes: the message carries no node id, so Python reports the call site once.
        for _node_id in ("device-1", "device-2"):
            report_unloaded_read("InfraDevice", "description", EXCLUDE_SELECTION, strict=False)

    assert len(record) == 1
    assert str(record[0].message) == EXCLUDE_MESSAGE + WARNING_SUFFIX


def test_reports_from_distinct_call_sites_are_not_deduplicated() -> None:
    with warnings.catch_warnings(record=True) as record:
        warnings.simplefilter("default")
        report_unloaded_read("InfraDevice", "description", EXCLUDE_SELECTION, strict=False)
        report_unloaded_read("InfraDevice", "description", EXCLUDE_SELECTION, strict=False)

    assert len(record) == 2
    assert record[0].lineno != record[1].lineno
