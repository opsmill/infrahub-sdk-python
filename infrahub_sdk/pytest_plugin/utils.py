from __future__ import annotations

from pathlib import Path

import yaml

from ..schema.repository import InfrahubRepositoryConfig
from .exceptions import FileNotValidError


def find_repository_config_file(base_path: Path | None = None) -> Path:
    """Find the repository config file, checking for both .yml and .yaml extensions.

    Args:
        base_path: Base directory to search in. If None, uses current directory.

    Returns:
        Path to the config file.

    Raises:
        FileNotFoundError: If neither .infrahub.yml nor .infrahub.yaml exists.
    """
    if base_path is None:
        base_path = Path()

    yml_path = base_path / ".infrahub.yml"
    yaml_path = base_path / ".infrahub.yaml"

    # Prefer .yml if both exist
    if yml_path.exists():
        return yml_path
    if yaml_path.exists():
        return yaml_path
    # For backward compatibility, return .yml path for error messages
    return yml_path


def load_repository_config(repo_config_file: Path) -> InfrahubRepositoryConfig:
    # If the file doesn't exist, try to find it with alternate extension
    if not repo_config_file.exists():
        if repo_config_file.name == ".infrahub.yml":
            alt_path = repo_config_file.parent / ".infrahub.yaml"
            if alt_path.exists():
                repo_config_file = alt_path
        elif repo_config_file.name == ".infrahub.yaml":
            alt_path = repo_config_file.parent / ".infrahub.yml"
            if alt_path.exists():
                repo_config_file = alt_path

    if not repo_config_file.is_file():
        raise FileNotFoundError(repo_config_file)

    try:
        yaml_data = repo_config_file.read_text()
        data = yaml.safe_load(yaml_data)
    except yaml.YAMLError as exc:
        raise FileNotValidError(name=str(repo_config_file)) from exc

    return InfrahubRepositoryConfig(**data)
