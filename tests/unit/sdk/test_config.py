import pytest
from pydantic import ValidationError

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
    """Test that explicit username/password overrides INFRAHUB_API_TOKEN from environment"""
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
    """Test that explicit api_token overrides INFRAHUB_USERNAME and INFRAHUB_PASSWORD from environment"""
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
