"""Guards for the Rich rendering environment pinned in ``tests/conftest.py``.

CLI-output assertions elsewhere in this suite compare against text whose colour and width Rich
decides. ``pytest_configure`` pins that decision; these tests pin the pinning, so a future edit
that loosens it fails here with an explanation rather than as a scatter of puzzling
output-comparison failures across the ctl tests.
"""

from __future__ import annotations

import os
from importlib.metadata import version
from io import StringIO

import pytest
from rich.console import Console

from tests.conftest import RENDER_ENV, RENDER_ENV_TO_CLEAN

# (major, minor) of the installed Rich. Rich started honouring ``FORCE_COLOR`` in 12.6, and changed
# what an empty value means in 14.0; ``pyproject.toml`` allows ``rich>=12`` with no upper bound.
RICH_VERSION = tuple(int(part) for part in version("rich").split(".")[:2])
RICH_HONOURS_FORCE_COLOR = RICH_VERSION >= (12, 6)


def test_render_env_is_pinned() -> None:
    """The hook in conftest ran, and ran before this module was imported."""
    for name in RENDER_ENV_TO_CLEAN:
        assert name not in os.environ, f"{name} must be unset: a set value makes Rich claim it writes to a terminal"
    for name, value in RENDER_ENV.items():
        assert os.environ.get(name) == value


@pytest.mark.parametrize("term", ["dumb", "unknown", "xterm-256color", "screen", ""])
def test_console_width_survives_any_term(term: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """``TERM`` must not change the rendered width, whatever the developer's shell exports.

    Rich clamps the width to 80 and ignores ``COLUMNS`` on a *dumb* terminal, but
    ``is_dumb_terminal`` is ``is_terminal and TERM in ("dumb", "unknown")`` -- so the clamp needs
    Rich to also believe it is on a terminal. Captured test output never is, and the conftest hook
    removes the one variable (``FORCE_COLOR``) that would make Rich claim otherwise. That is why
    the hook does not pin ``TERM``, and why pinning it to a non-dumb value would be a no-op.
    """
    monkeypatch.setenv("TERM", term)

    console = Console(file=StringIO())

    assert console.is_terminal is False
    assert console.is_dumb_terminal is False
    assert console.width == int(RENDER_ENV["COLUMNS"])
    assert console.no_color is True


@pytest.mark.parametrize("force_color", ["1", "3"])
def test_force_color_is_what_would_clamp_the_width(force_color: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the failure mode the hook exists to prevent.

    With ``FORCE_COLOR`` set, Rich treats the captured output as a terminal; combined with
    ``TERM=dumb`` that drops it to width 80, which truncates the wide tables the CLI-output
    fixtures record. This is the state a developer's shell puts the suite in. Rich before 12.6
    does not read the variable at all, so there the width stays pinned whatever the shell exports.
    """
    monkeypatch.setenv("FORCE_COLOR", force_color)
    monkeypatch.setenv("TERM", "dumb")

    console = Console(file=StringIO())

    assert console.is_terminal is RICH_HONOURS_FORCE_COLOR
    assert console.is_dumb_terminal is RICH_HONOURS_FORCE_COLOR
    assert console.width == (80 if RICH_HONOURS_FORCE_COLOR else int(RENDER_ENV["COLUMNS"]))


def test_empty_force_color_is_why_the_hook_removes_rather_than_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the one value whose meaning depends on the Rich version, which rules out any override.

    Rich 12.6 through 13 test ``FORCE_COLOR is not None``, so ``export FORCE_COLOR=`` forces a
    terminal just as ``1`` does. Rich 14 adopted the https://force-color.org/ convention, under
    which the empty string means "not a terminal": ``is_terminal`` returns ``False`` before it even
    consults ``isatty()``. Overriding the variable with a falsy value would therefore defuse it on
    one version and arm it on the other; removing it is the only fix that is correct on both, which
    is why ``RENDER_ENV_TO_CLEAN`` exists.
    """
    monkeypatch.setenv("FORCE_COLOR", "")
    monkeypatch.setenv("TERM", "dumb")

    console = Console(file=StringIO())

    forces_terminal = RICH_HONOURS_FORCE_COLOR and RICH_VERSION < (14, 0)
    assert console.is_terminal is forces_terminal
    assert console.is_dumb_terminal is forces_terminal
    assert console.width == (80 if forces_terminal else int(RENDER_ENV["COLUMNS"]))
