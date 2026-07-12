from dataclasses import dataclass
from typing import Any

import pytest
from pydantic import ValidationError

from infrahub_sdk import Priority
from infrahub_sdk.config import Config


def test_combine_authentications() -> None:
    # When both username/password and api_token are explicitly provided, raise an error
    with pytest.raises(ValidationError) as exc:
        Config(api_token="testing", username="test", password="testpassword")

    assert "Cannot use both 'api_token' and 'username'/'password' authentication simultaneously" in str(exc.value)


def test_missing_password() -> None:
    with pytest.raises(ValidationError) as exc:
        Config(username="test")

    assert "Both 'username' and 'password' needs to be set" in str(exc.value)


def test_password_authentication() -> None:
    config = Config(username="test", password="test-password")
    assert config.password_authentication


def test_not_password_authentication() -> None:
    config = Config()
    assert not config.password_authentication


def test_config_address() -> None:
    address = "http://localhost:8000"

    config = Config(address=address + "/")
    assert config.address == address

    config = Config(address=address + "//")
    assert config.address == address

    config = Config(address=address)
    assert config.address == address


def test_password_auth_overrides_env_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that explicit username/password overrides INFRAHUB_API_TOKEN from environment."""
    # Set environment variable for api_token
    monkeypatch.setenv("INFRAHUB_API_TOKEN", "token-from-env")

    # Create configuration with explicit username/password
    config = Config(address="https://sandbox.infrahub.app", username="testuser", password="testpass")

    # Password auth should be active and api_token should be cleared
    assert config.username == "testuser"
    assert config.password == "testpass"
    assert config.api_token is None
    assert config.password_authentication is True


def test_token_auth_overrides_env_password(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that explicit api_token overrides INFRAHUB_USERNAME and INFRAHUB_PASSWORD from environment."""
    # Set environment variables for username/password
    monkeypatch.setenv("INFRAHUB_USERNAME", "user-from-env")
    monkeypatch.setenv("INFRAHUB_PASSWORD", "pass-from-env")

    # Create configuration with explicit api_token
    config = Config(address="https://sandbox.infrahub.app", api_token="explicit-token")

    # Token auth should be active and username/password should be cleared
    assert config.api_token == "explicit-token"
    assert config.username is None
    assert config.password is None
    assert config.password_authentication is False


def test_password_auth_overrides_env_token_when_password_env_var_and_username_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that explicit username/password overrides INFRAHUB_API_TOKEN from environment.

    The username is provided through the Config object and the password is provided through an
    environment variable.
    """
    # Set environment variable for api_token and password
    monkeypatch.setenv("INFRAHUB_API_TOKEN", "token-from-env")
    monkeypatch.setenv("INFRAHUB_PASSWORD", "testpass")

    # Create configuration with explicit username
    config = Config(address="https://sandbox.infrahub.app", username="testuser")

    # Password auth should be active and api_token should be cleared
    assert config.username == "testuser"
    assert config.password == "testpass"
    assert config.api_token is None
    assert config.password_authentication is True


def test_invalid_priority_rejected() -> None:
    """An unknown configured priority fails at config load; no request is ever issued.

    Construction raises before any client/request exists, so 'no request is issued'
    is inherent — the ValidationError is raised while building Config.
    """
    # Passing an invalid string is the behaviour under test; pydantic rejects it at load. The field
    # statically types Priority | None but coerces strings at runtime, so the dynamic input is passed
    # via a dict[str, Any] rather than suppressed with a type-checker ignore.
    kwargs: dict[str, Any] = {"address": "http://localhost:8000", "priority": "lowe"}
    with pytest.raises(ValidationError, match=r"Input should be 'high', 'normal' or 'low'"):
        Config(**kwargs)


@dataclass
class PriorityCase:
    name: str
    value: str | Priority
    expected: Priority


PRIORITY_CASES = [
    PriorityCase(name="high-upper", value="HIGH", expected=Priority.HIGH),
    PriorityCase(name="high-title", value="High", expected=Priority.HIGH),
    PriorityCase(name="high-lower", value="high", expected=Priority.HIGH),
    PriorityCase(name="high-enum", value=Priority.HIGH, expected=Priority.HIGH),
    PriorityCase(name="normal-upper", value="NORMAL", expected=Priority.NORMAL),
    PriorityCase(name="normal-title", value="Normal", expected=Priority.NORMAL),
    PriorityCase(name="normal-lower", value="normal", expected=Priority.NORMAL),
    PriorityCase(name="normal-enum", value=Priority.NORMAL, expected=Priority.NORMAL),
    PriorityCase(name="low-upper", value="LOW", expected=Priority.LOW),
    PriorityCase(name="low-title", value="Low", expected=Priority.LOW),
    PriorityCase(name="low-lower", value="low", expected=Priority.LOW),
    PriorityCase(name="low-enum", value=Priority.LOW, expected=Priority.LOW),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in PRIORITY_CASES])
def test_priority_case_insensitive_acceptance(case: PriorityCase) -> None:
    """Valid priority strings are accepted case-insensitively (and enum members pass through)."""
    # Case-insensitive string coercion is the behaviour under test; the field statically types Priority,
    # so the mixed str/Priority input is passed via a dict[str, Any] rather than suppressed with an ignore.
    kwargs: dict[str, Any] = {"address": "http://localhost:8000", "priority": case.value}
    config = Config(**kwargs)
    assert config.priority is case.expected


@pytest.mark.parametrize(
    ("env_value", "expected"),
    [
        pytest.param("LOW", Priority.LOW, id="low"),
        pytest.param("HIGH", Priority.HIGH, id="high"),
        pytest.param("NORMAL", Priority.NORMAL, id="normal"),
    ],
)
def test_priority_from_env_var(monkeypatch: pytest.MonkeyPatch, env_value: str, expected: Priority) -> None:
    """The INFRAHUB_PRIORITY env var resolves case-insensitively to a Priority member."""
    monkeypatch.setenv("INFRAHUB_PRIORITY", env_value)

    config = Config(address="http://localhost:8000")

    assert config.priority is expected


def test_priority_default_is_none() -> None:
    """With no priority configured, the field defaults to None (no header emitted)."""
    config = Config(address="http://localhost:8000")
    assert config.priority is None
