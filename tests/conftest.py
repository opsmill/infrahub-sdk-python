import os
from collections.abc import Generator

import pytest
import pytest_asyncio

from infrahub_sdk.ctl import config

pytest_plugins = ["pytester"]

ENV_VARS_TO_CLEAN = ["INFRAHUB_ADDRESS", "INFRAHUB_TOKEN", "INFRAHUB_BRANCH", "INFRAHUB_USERNAME", "INFRAHUB_PASSWORD"]


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
