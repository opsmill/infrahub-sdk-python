"""Reporting of reads of node fields whose value the SDK never fetched."""

from __future__ import annotations

import inspect
import os
import sys
import warnings
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, ParamSpec, TypeVar, cast

import infrahub_sdk

from ..exceptions import FieldNotLoadedError, FieldNotLoadedWarning

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from .selection import Selection

P = ParamSpec("P")
R = TypeVar("R")

# Single switch point: flipping it makes every unknown read raise instead of warn.
_STRICT_FIELD_ACCESS: bool = False

_INTERNAL_ACCESS: ContextVar[bool] = ContextVar("infrahub_sdk_internal_field_access", default=False)

_SDK_PATH_PREFIX = str(Path(infrahub_sdk.__file__).parent) + os.sep

_WARNING_SUFFIX = "This will raise FieldNotLoadedError in infrahub-sdk 2.0."


@contextmanager
def internal_field_access() -> Iterator[None]:
    """Silence unknown-read reporting for reads the SDK makes itself within the block.

    The block must not start async tasks or call user code: both would inherit the silenced context.
    """
    token = _INTERNAL_ACCESS.set(True)
    try:
        yield
    finally:
        _INTERNAL_ACCESS.reset(token)


def with_internal_field_access(func: Callable[P, R]) -> Callable[P, R]:
    """Run ``func``, a plain function or a coroutine function, under :func:`internal_field_access`."""
    if inspect.iscoroutinefunction(func):

        @wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> object:
            with internal_field_access():
                return await func(*args, **kwargs)

        return cast("Callable[P, R]", async_wrapper)

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        with internal_field_access():
            return func(*args, **kwargs)

    return wrapper


def build_unloaded_message(kind: str, field: str, selection: Selection | None, hint_fetch: bool = False) -> str:
    """Return the message for an unknown read of ``<kind>.<field>``, without the node id.

    ``hint_fetch`` adds ``fetch()`` to the advice, for a field that can be fetched on its own: a cardinality-many
    relationship.
    """
    if selection is None:
        return (
            f"{kind}.{field} is not known to the SDK (origin unknown). "
            "Fetch the node with a selection that includes it before reading it."
        )
    if selection.peer_floor:
        return (
            f"{kind}.{field} was not fetched: this node only carries its identity fields "
            f"(peer of {selection.peer_of}). Call fetch() on {selection.peer_of}, "
            "or query with prefetch_relationships=True, before reading it."
        )
    advice = (
        "Add it to the selection, or call fetch() on it, before reading it."
        if hint_fetch
        else "Add it to the selection before reading it."
    )
    return f"{kind}.{field} was not fetched (selection: {selection.describe()}). {advice}"


def report_unloaded_read(
    kind: str, field: str, selection: Selection | None, strict: bool, hint_fetch: bool = False
) -> None:
    """Report a read of a field the SDK does not know: silent for internal reads, else raise or warn.

    ``hint_fetch`` is passed on to :func:`build_unloaded_message`.

    Raises:
        FieldNotLoadedError: If strict field access is switched on, or ``strict`` is set for the node.

    """
    if _INTERNAL_ACCESS.get():
        return

    message = build_unloaded_message(kind, field, selection, hint_fetch=hint_fetch)
    if _STRICT_FIELD_ACCESS or strict:
        raise FieldNotLoadedError(
            kind=kind,
            field=field,
            selection=selection.describe() if selection is not None else None,
            message=message,
        )
    warnings.warn(f"{message} {_WARNING_SUFFIX}", FieldNotLoadedWarning, stacklevel=_external_stacklevel())


def _external_stacklevel() -> int:
    """Return the ``stacklevel`` that points the caller's warning at the first frame outside infrahub_sdk."""
    frame = sys._getframe(1)
    level = 1
    while frame.f_back is not None and frame.f_code.co_filename.startswith(_SDK_PATH_PREFIX):
        frame = frame.f_back
        level += 1
    return level
