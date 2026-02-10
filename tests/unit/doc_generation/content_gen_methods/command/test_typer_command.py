from __future__ import annotations

from doc_generation.content_gen_methods import TyperGroupCommand, TyperSingleCommand


class TestTyperSingleCommand:
    def test_build_exec_cmd(self) -> None:
        # Arrange
        cmd = TyperSingleCommand(name="dump")

        # Act
        result = cmd.build()

        # Assert
        assert "uv run typer --func dump" in result
        assert "infrahub_sdk.ctl.cli_commands" in result
        assert 'utils docs --name "infrahubctl dump"' in result


class TestTyperGroupCommand:
    def test_build_exec_cmd(self) -> None:
        # Arrange
        cmd = TyperGroupCommand(name="branch")

        # Act
        result = cmd.build()

        # Assert
        assert "uv run typer infrahub_sdk.ctl.branch" in result
        assert 'utils docs --name "infrahubctl branch"' in result
