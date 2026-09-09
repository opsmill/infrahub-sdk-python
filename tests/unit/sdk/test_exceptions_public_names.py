from __future__ import annotations

import json

from infrahub_sdk import exceptions
from tests.helpers.fixtures import read_fixture


def load_snapshot() -> set[str]:
    return set(json.loads(read_fixture(file_name="public_names.json", fixture_subdir="error_catalogue")))


def current_names() -> set[str]:
    return {
        name
        for name in dir(exceptions)
        if not name.startswith("_")
        and isinstance(getattr(exceptions, name), type)
        and issubclass(getattr(exceptions, name), BaseException)
    }


def test_snapshot_matches_the_exported_exceptions() -> None:
    """infrahub_sdk.exceptions is the supported import path.

    Nothing may drop out of it, and a new exception must be added to the snapshot, so the surface
    stays a deliberate choice rather than a side effect.
    """
    assert current_names() == load_snapshot()
