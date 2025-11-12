import sys

try:
    from .cli_commands import app
except ImportError as exc:
    sys.exit(
        f"Module {exc.name} is not available, install the 'ctl' extra of the infrahub-sdk package, "
        f"`pip install 'infrahub-sdk[ctl]'` or run `uv sync --extra ctl`."
    )

__all__ = ["app"]
