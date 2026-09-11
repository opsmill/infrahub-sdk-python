from __future__ import annotations

import json

from infrahub_sdk import exceptions
from infrahub_sdk.exceptions import authentication_error_from_response, graphql_error_from_response
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


def star_imported_names() -> dict[str, object]:
    namespace: dict[str, object] = {}
    exec("from infrahub_sdk.exceptions import *", namespace)  # noqa: S102
    return {name: value for name, value in namespace.items() if not name.startswith("__")}


def test_snapshot_matches_the_exported_exceptions() -> None:
    """infrahub_sdk.exceptions is the supported import path.

    Nothing may drop out of it, and a new exception must be added to the snapshot, so the surface
    stays a deliberate choice rather than a side effect.
    """
    assert current_names() == load_snapshot()


def test_star_import_gives_the_exception_classes_and_nothing_else() -> None:
    """What `import *` hands an end user is the classes they catch.

    Without a declared `__all__` the wildcard also carries the `base` and `factory` submodule names,
    which are an artefact of the package layout and shadow those names in the caller's scope. The
    raise-time factories stay importable by name; they are simply not part of the wildcard.
    """
    assert set(star_imported_names()) == load_snapshot()


def test_the_raise_time_factories_are_still_importable_by_name() -> None:
    """Narrowing the wildcard must not take the supported explicit imports with it.

    The import at the top of this module is the assertion; these calls confirm the names resolve to
    the factories rather than to something else the façade happens to bind.
    """
    assert callable(authentication_error_from_response)
    assert callable(graphql_error_from_response)
