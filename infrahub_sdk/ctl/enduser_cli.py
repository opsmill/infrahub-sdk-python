"""Entry point for the ``infrahub`` end-user CLI.

This module mirrors the pattern used by ``infrahub_sdk.ctl.cli`` but loads
the end-user command set from ``enduser_commands`` instead.
"""

from __future__ import annotations

import sys

try:
    from .enduser_commands import app
except ImportError as exc:
    sys.exit(
        f"Module {exc.name} is not available, install the 'ctl' extra of the infrahub-sdk package, "
        f"`pip install 'infrahub-sdk[ctl]'` or run `uv sync --extra ctl`."
    )

__all__ = ["app"]
