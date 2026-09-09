"""Guards for the Rich rendering environment pinned in ``tests/conftest.py``.

CLI-output assertions elsewhere in this suite compare against text whose colour and width Rich
decides. ``pytest_configure`` pins that decision; these tests pin the pinning, so a future edit
that loosens it fails here with an explanation rather than as a scatter of puzzling
output-comparison failures across the ctl tests.
"""

from __future__ import annotations

import os
from io import StringIO

import pytest
from rich.console import Console

from tests.conftest import RENDER_ENV, RENDER_ENV_TO_CLEAN


def test_render_env_is_pinned() -> None:
    """The hook in conftest ran, and ran before this module was imported."""
    for name in RENDER_ENV_TO_CLEAN:
        assert name not in os.environ, f"{name} must be unset: Rich reads any value as 'this is a terminal'"
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


@pytest.mark.parametrize("force_color", ["1", "3", ""])
def test_force_color_is_what_would_clamp_the_width(force_color: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the failure mode the hook exists to prevent.

    With ``FORCE_COLOR`` set, Rich treats the captured output as a terminal; combined with
    ``TERM=dumb`` that drops it to width 80, which truncates the wide tables the CLI-output
    fixtures record. This is the state a developer's shell puts the suite in, and the reason
    ``FORCE_COLOR`` is removed rather than merely overridden.

    The empty string is the case that makes *removal* the only correct fix: Rich tests
    ``FORCE_COLOR is not None``, so ``export FORCE_COLOR=`` forces a terminal just as ``1`` does,
    and overriding the variable with a falsy value would not defuse it.
    """
    monkeypatch.setenv("FORCE_COLOR", force_color)
    monkeypatch.setenv("TERM", "dumb")

    console = Console(file=StringIO())

    assert console.is_dumb_terminal is True
    assert console.width == 80
