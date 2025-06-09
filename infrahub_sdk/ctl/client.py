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
    """
    Initializes and returns an asynchronous InfrahubClient.

    Uses global CLI configuration settings and allows overriding specific parameters.

    Args:
        branch: Optional default branch for the client.
        identifier: Optional identifier for tracking client operations.
        timeout: Optional request timeout in seconds.
        max_concurrent_execution: Optional limit for concurrent operations in batch mode.
        retry_on_failure: Optional flag to enable/disable retries on failure.

    Returns:
        An initialized InfrahubClient instance.
    """
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
    """
    Initializes and returns a synchronous InfrahubClientSync.

    Uses global CLI configuration settings and allows overriding specific parameters.

    Args:
        branch: Optional default branch for the client.
        identifier: Optional identifier for tracking client operations.
        timeout: Optional request timeout in seconds.
        max_concurrent_execution: Optional limit for concurrent operations in batch mode.
        retry_on_failure: Optional flag to enable/disable retries on failure.

    Returns:
        An initialized InfrahubClientSync instance.
    """
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
    """
    Internal helper to construct a Config object for client initialization.

    Prioritizes explicitly passed arguments, then falls back to global CLI settings.

    Args:
        branch: Default branch.
        identifier: Tracker identifier.
        timeout: Request timeout.
        max_concurrent_execution: Max concurrent tasks for batch operations.
        retry_on_failure: Whether to retry on failure.

    Returns:
        A Config object.
    """
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
