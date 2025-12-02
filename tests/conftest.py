import asyncio
import os
from collections.abc import Generator

import pytest

from infrahub_sdk.ctl import config

pytest_plugins = ["pytester"]

ENV_VARS_TO_CLEAN = ["INFRAHUB_ADDRESS", "INFRAHUB_TOKEN", "INFRAHUB_BRANCH", "INFRAHUB_USERNAME", "INFRAHUB_PASSWORD"]


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop]:
    """Overrides pytest default function scoped event loop"""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


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
