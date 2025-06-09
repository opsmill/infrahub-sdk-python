"""Config Class."""

from __future__ import annotations

from pathlib import Path

import toml
import typer
from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CONFIG_FILE = "infrahubctl.toml"
ENVVAR_CONFIG_FILE = "INFRAHUBCTL_CONFIG"
INFRAHUB_REPO_CONFIG_FILE = ".infrahub.yml"


class Settings(BaseSettings):
    """Main Settings Class for the project."""

    model_config = SettingsConfigDict(env_prefix="INFRAHUB_", populate_by_name=True, extra="allow")
    server_address: str = Field(default="http://localhost:8000", validation_alias="infrahub_address")
    api_token: str | None = Field(default=None)
    default_branch: str = Field(default="main")

    @field_validator("server_address")
    @classmethod
    def cleanup_server_address(cls, v: str) -> str:
        """Removes trailing slashes from the server_address."""
        return v.rstrip("/")


class ConfiguredSettings:
    """
    Manages the loading and access of Infrahub CLI settings.

    This class ensures that settings are loaded (e.g., from a TOML file or environment variables)
    before they are accessed, providing a single point of truth for configuration.
    """
    def __init__(self) -> None:
        """Initializes ConfiguredSettings with no settings loaded yet."""
        self._settings: Settings | None = None

    @property
    def active(self) -> Settings:
        """
        Provides the currently active Settings instance.

        Raises:
            typer.Abort: If settings have not been loaded before access.

        Returns:
            The loaded Settings object.
        """
        if self._settings:
            return self._settings

        print("Configuration not properly loaded")
        raise typer.Abort()

    def load(self, config_file: str | Path = "infrahubctl.toml", config_data: dict | None = None) -> None:
        """
        Loads configuration settings.

        The method attempts to load settings from `config_data` if provided.
        If not, it tries to load from the specified `config_file`.
        If neither is successful or available, it falls back to default Pydantic settings
        (which can include environment variables).

        Once settings are successfully loaded, subsequent calls to `load` will do nothing.

        Args:
            config_file: Path to the TOML configuration file.
                         Defaults to "infrahubctl.toml".
            config_data: A dictionary containing configuration settings.
                         If provided, this takes precedence over `config_file`.
        """

        if self._settings:
            return

        if config_data:
            self._settings = Settings(**config_data)
            return

        if not isinstance(config_file, Path):
            config_file = Path(config_file)

        if config_file.is_file():
            config_string = config_file.read_text(encoding="utf-8")
            config_tmp = toml.loads(config_string)

            self._settings = Settings(**config_tmp)
            return

        self._settings = Settings()

    def load_and_exit(self, config_file: str | Path = "infrahubctl.toml", config_data: dict | None = None) -> None:
        """Calls load, but wraps it in a try except block.

        This is done to handle a ValidationErorr which is raised when settings are specified but invalid.
        In such cases, a message is printed to the screen indicating the settings which don't pass validation.

        Args:
            config_file_name (str, optional): [description]. Defaults to "pyprojectctl.toml".
            config_data (dict, optional): [description]. Defaults to None.
        """

        try:
            self.load(config_file=config_file, config_data=config_data)
        except ValidationError as exc:
            print(f"Configuration not valid, found {len(exc.errors())} error(s)")
            for error in exc.errors():
                loc_str = [str(item) for item in error["loc"]]
                print(f"  {'/'.join(loc_str)} | {error['msg']} ({error['type']})")
            raise typer.Abort()


SETTINGS = ConfiguredSettings()
