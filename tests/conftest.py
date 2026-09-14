import os
from collections.abc import Generator

import pytest
import pytest_asyncio

from infrahub_sdk.ctl import config

pytest_plugins = ["pytester"]

ENV_VARS_TO_CLEAN = ["INFRAHUB_ADDRESS", "INFRAHUB_TOKEN", "INFRAHUB_BRANCH", "INFRAHUB_USERNAME", "INFRAHUB_PASSWORD"]


# Rendering environment for every test in this suite.
#
# Rich snapshots ``no_color`` when a ``Console`` is constructed, and a ``Console`` reports
# itself as a terminal if ``FORCE_COLOR`` is set -- on Rich 12.6 through 13 to *any* value, empty
# string included; from Rich 14 to any non-empty value. Removing the variable is the one strategy that
# is correct on both, so it is removed rather than overridden. Many ``infrahub_sdk.ctl`` modules
# build a module-level ``Console()``, and that happens while pytest
# imports the test modules -- before any fixture can run. So the environment has to be pinned
# from a hook that runs ahead of collection, which is what ``pytest_configure`` does.
#
# Without this, a developer whose shell exports ``FORCE_COLOR`` (or whose terminal is narrower
# than the CLI-output fixtures) gets ANSI escapes and truncated Rich tables in captured output,
# and every test that asserts on CLI text fails locally while staying green in CI.
#
# ``TERM`` is deliberately left alone: ``TERM=dumb`` puts Rich in its dumb-terminal path, which
# pins the width to 80 and ignores ``COLUMNS``, truncating the wide tables these fixtures record.
RENDER_ENV = {"NO_COLOR": "1", "COLUMNS": "200"}
RENDER_ENV_TO_CLEAN = ["FORCE_COLOR"]


def pytest_configure(config: pytest.Config) -> None:
    """Pin Rich's colour and width before any test module is imported."""
    for name in RENDER_ENV_TO_CLEAN:
        os.environ.pop(name, None)
    os.environ.update(RENDER_ENV)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    pytest_asyncio_tests = (item for item in items if pytest_asyncio.is_async_test(item))
    session_scope_marker = pytest.mark.asyncio(loop_scope="session")
    for async_test in pytest_asyncio_tests:
        async_test.add_marker(session_scope_marker, append=False)


@pytest.fixture(scope="session", autouse=True)
def execute_before_any_test() -> None:
    config.SETTINGS.load_and_exit()
    config.SETTINGS.active.server_address = "http://mock"


@pytest.fixture(scope="session", autouse=True)
def clean_env_vars() -> Generator:
    """Cleans the environment variables before any test is run."""
    original_values = {}
    for name in ENV_VARS_TO_CLEAN:
        original_values[name] = os.environ.get(name)
        if original_values[name] is not None:
            del os.environ[name]

    yield

    for name in ENV_VARS_TO_CLEAN:
        if original_values[name] is not None:
            os.environ[name] = original_values[name]
