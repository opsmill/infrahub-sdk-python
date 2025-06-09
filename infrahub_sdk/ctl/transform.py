from rich.console import Console

from ..schema.repository import InfrahubRepositoryConfig


def list_transforms(config: InfrahubRepositoryConfig) -> None:
    """
    Prints a list of available Python transforms defined in the repository configuration.

    Args:
        config: The loaded repository configuration.
    """
    console = Console()
    console.print(f"Python transforms defined in repository: {len(config.python_transforms)}")

    for transform in config.python_transforms:
        console.print(f"{transform.name} ({transform.file_path}::{transform.class_name})")
