import sys

import pytest
from typer.testing import CliRunner

from infrahub_sdk.ctl.cli import app

runner = CliRunner()

requires_python_310 = pytest.mark.skipif(sys.version_info < (3, 10), reason="Requires Python 3.10 or higher")


@requires_python_310
def test_main_app():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "[OPTIONS] COMMAND [ARGS]" in result.stdout


def test_validate_all_commands_have_names():
    assert app.registered_commands
    for command in app.registered_commands:
        assert command.name


def test_validate_all_groups_have_names():
    assert app.registered_groups
    for group in app.registered_groups:
        assert group.name
