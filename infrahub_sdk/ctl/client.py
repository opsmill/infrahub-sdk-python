from __future__ import annotations

from typing import Any

from .. import InfrahubClient, InfrahubClientSync
from ..config import Config
from ..ctl import config


def initialize_client(
    branch: str | None = None,
    identifier: str | None = None,
    timeout: int | None = None,
    max_concurrent_execution: int | None = None,
    retry_on_failure: bool | None = None,
) -> InfrahubClient:
    return InfrahubClient(
        config=_define_config(
            branch=branch,
            identifier=identifier,
            timeout=timeout,
            max_concurrent_execution=max_concurrent_execution,
            retry_on_failure=retry_on_failure,
        )
    )


def initialize_client_sync(
    branch: str | None = None,
    identifier: str | None = None,
    timeout: int | None = None,
    max_concurrent_execution: int | None = None,
    retry_on_failure: bool | None = None,
) -> InfrahubClientSync:
    return InfrahubClientSync(
        config=_define_config(
            branch=branch,
            identifier=identifier,
            timeout=timeout,
            max_concurrent_execution=max_concurrent_execution,
            retry_on_failure=retry_on_failure,
        )
    )


def _define_config(
    branch: str | None = None,
    identifier: str | None = None,
    timeout: int | None = None,
    max_concurrent_execution: int | None = None,
    retry_on_failure: bool | None = None,
) -> Config:
    client_config: dict[str, Any] = {
        "address": config.SETTINGS.active.server_address,
        "insert_tracker": True,
        "identifier": identifier,
    }

    if config.SETTINGS.active.api_token:
        client_config["api_token"] = config.SETTINGS.active.api_token

    if timeout:
        client_config["timeout"] = timeout

    if max_concurrent_execution is not None:
        client_config["max_concurrent_execution"] = max_concurrent_execution

    if retry_on_failure is not None:
        client_config["retry_on_failure"] = retry_on_failure

    if branch:
        client_config["default_branch"] = branch

    return Config(**client_config)
