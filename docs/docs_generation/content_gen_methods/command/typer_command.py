from __future__ import annotations

from abc import ABC

from .command import ACommand


class ATyperCommand(ACommand, ABC):
    def __init__(self, name: str) -> None:
        self.name = name


class TyperSingleCommand(ATyperCommand):
    """A single (non-group) infrahubctl command."""

    def build(self) -> str:
        return (
            f'uv run typer --func {self.name} infrahub_sdk.ctl.cli_commands utils docs --name "infrahubctl {self.name}"'
        )


class TyperGroupCommand(ATyperCommand):
    """An infrahubctl command group (e.g. ``branch``, ``schema``)."""

    def build(self) -> str:
        return f'uv run typer infrahub_sdk.ctl.{self.name} utils docs --name "infrahubctl {self.name}"'
