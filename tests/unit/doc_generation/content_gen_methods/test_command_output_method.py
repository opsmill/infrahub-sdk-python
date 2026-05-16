from __future__ import annotations

from pathlib import Path
from unittest.mock import create_autospec

from invoke import Context, Result

from docs.docs_generation import ACommand, CommandOutputDocContentGenMethod


class StubCommand(ACommand):
    def __init__(self, cmd: str) -> None:
        self.cmd = cmd

    def build(self) -> str:
        return self.cmd


class TestCommandOutputDocContentGenMethod:
    def test_apply_runs_command_and_reads_output(self, tmp_path: Path) -> None:
        """The method executes the command via context.run, then reads the output file.

        The content is read from the temp file whose path was appended via --output.
        """
        output_content = "# Generated docs"

        # Arrange
        def fake_run(cmd: str, **kwargs: object) -> Result:
            parts = cmd.split("--output ")
            output_path = Path(parts[1].strip())
            output_path.write_text(output_content, encoding="utf-8")
            return Result()

        mock_context = create_autospec(Context, instance=True)
        mock_context.run.side_effect = fake_run

        method = CommandOutputDocContentGenMethod(
            context=mock_context,
            working_directory=tmp_path,
            command=StubCommand("some_command"),
        )

        # Act
        result = method.apply()

        # Assert
        assert result == output_content

    def test_apply_appends_output_flag(self, tmp_path: Path) -> None:
        """Verify that --output <tmpfile> is appended to the command."""
        captured_cmd: list[str] = []

        # Arrange
        def fake_run(cmd: str, **kwargs: object) -> Result:
            captured_cmd.append(cmd)
            parts = cmd.split("--output ")
            Path(parts[1].strip()).write_text("", encoding="utf-8")
            return Result()

        mock_context = create_autospec(Context, instance=True)
        mock_context.run.side_effect = fake_run

        method = CommandOutputDocContentGenMethod(
            context=mock_context,
            working_directory=tmp_path,
            command=StubCommand("base_cmd"),
        )

        # Act
        method.apply()

        # Assert
        assert captured_cmd[0].startswith("base_cmd --output ")
