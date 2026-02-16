from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from invoke import Context

    from .command import ACommand

from .base import ADocContentGenMethod


class CommandOutputDocContentGenMethod(ADocContentGenMethod):
    """Run a command and return the content it writes to a temporary file.

    ``--output <tmpfile>`` is appended to the command automatically.

    Args:
        context: Invoke execution context.
        working_directory: Directory in which the command is executed.
        command: An ``ACommand`` whose ``build()`` returns the base command string.

    Example::

        method = CommandOutputDocContentGenMethod(
            context=ctx,
            working_directory=project_root,
            command=TyperCommand(module="infrahub_sdk.ctl.cli_commands", name="dump", app_name="infrahubctl", is_function=True),
        )
        content = method.apply()
    """

    def __init__(self, context: Context, working_directory: Path, command: ACommand) -> None:
        self.context = context
        self.working_directory = working_directory
        self.command = command

    def apply(self) -> str:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".mdx", delete=False, encoding="utf-8") as tmp:
            tmp_path = Path(tmp.name)

        try:
            full_cmd = f"{self.command.build()} --output {tmp_path}"
            with self.context.cd(self.working_directory):
                self.context.run(full_cmd)

            return tmp_path.read_text(encoding="utf-8")
        finally:
            tmp_path.unlink(missing_ok=True)
