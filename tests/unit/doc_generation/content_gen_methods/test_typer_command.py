from __future__ import annotations

from doc_generation.content_gen_methods import TyperCommand


class TestTyperCommand:
    def test_build_registered_group(self) -> None:
        """Default variant builds a registered-group style command."""
        cmd = TyperCommand(module="infrahub_sdk.ctl.cli_commands", name="dump", app_name="infrahubctl")

        result = cmd.build()

        assert result == 'uv run typer infrahub_sdk.ctl.cli_commands.dump utils docs --name "infrahubctl dump"'

    def test_build_registered_function(self) -> None:
        """is_function=True builds a --func style command."""
        cmd = TyperCommand(
            module="infrahub_sdk.ctl.cli_commands", name="dump", app_name="infrahubctl", is_function=True
        )

        result = cmd.build()

        assert result == 'uv run typer --func dump infrahub_sdk.ctl.cli_commands utils docs --name "infrahubctl dump"'
