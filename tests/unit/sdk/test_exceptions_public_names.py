from __future__ import annotations

import json

from infrahub_sdk import exceptions
from infrahub_sdk.exceptions import authentication_error_from_response, base, graphql_error_from_response
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


def classes_defined_in(module: object) -> set[str]:
    """The exception classes a module defines itself, ignoring any it merely imported."""
    return {
        name
        for name, value in vars(module).items()
        if isinstance(value, type) and issubclass(value, BaseException) and value.__module__ == module.__name__  # type: ignore[attr-defined]
    }


def test_the_facade_lists_every_class_base_declares() -> None:
    """The façade writes its exports out by hand, so nothing may drift out of step with `base`.

    A class added to `base.__all__` has to be added to both lists in
    `infrahub_sdk/exceptions/__init__.py`: the import block and `__all__`.
    """
    assert set(exceptions.__all__) == set(base.__all__)


def test_every_name_the_facade_declares_is_bound() -> None:
    """A name in `__all__` that the import block omits would only fail at a caller's `import *`."""
    missing = sorted(name for name in exceptions.__all__ if not hasattr(exceptions, name))

    assert missing == [], f"declared in __all__ but never imported: {missing}"


def test_base_declares_every_exception_it_defines() -> None:
    """An exception class left out of `base.__all__` never reaches the façade at all.

    Without this the omission is invisible: the class is simply absent everywhere downstream, so the
    snapshot below still matches and nothing else notices.
    """
    undeclared = sorted(classes_defined_in(base) - set(base.__all__))

    assert undeclared == [], f"defined in base.py but missing from base.__all__: {undeclared}"


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
