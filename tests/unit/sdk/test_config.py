import pytest
from pydantic import ValidationError

from infrahub_sdk.config import Config


def test_combine_authentications() -> None:
    # When both username/password and api_token are provided,
    # password authentication takes precedence and api_token is cleared
    config = Config(api_token="testing", username="test", password="testpassword")
    assert config.username == "test"
    assert config.password == "testpassword"
    assert config.api_token is None
    assert config.password_authentication is True


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


def test_password_auth_overrides_env_token(monkeypatch) -> None:
    """Test that explicit username/password overrides INFRAHUB_API_TOKEN from environment"""
    # Set environment variable for api_token
    monkeypatch.setenv("INFRAHUB_API_TOKEN", "token-from-env")

    # Create config with explicit username/password
    config = Config(address="https://sandbox.infrahub.app", username="testuser", password="testpass")

    # Password auth should be active and api_token should be cleared
    assert config.username == "testuser"
    assert config.password == "testpass"
    assert config.api_token is None
    assert config.password_authentication is True
