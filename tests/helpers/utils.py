"""Utility functions reused throughout integration tests."""

import os
import re
import shutil
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from infrahub_sdk.repository import GitRepoManager


@contextmanager
def change_directory(new_directory: str) -> Generator[None, None, None]:
    """Helper function used to change directories in a with block."""
    # Save the current working directory
    original_directory = Path.cwd()

    # Change to the new directory
    try:
        os.chdir(new_directory)
        yield  # Yield control back to the with block

    finally:
        # Change back to the original directory
        os.chdir(original_directory)


@contextmanager
def temp_repo_and_cd(source_dir: Path) -> Generator[Path, None, None]:
    temp_dir = tempfile.mkdtemp()
    original_directory = Path.cwd()

    try:
        shutil.copytree(source_dir, temp_dir, dirs_exist_ok=True)
        GitRepoManager(temp_dir)  # assuming this is defined elsewhere
        os.chdir(temp_dir)
        yield Path(temp_dir)
    finally:
        os.chdir(original_directory)
        shutil.rmtree(temp_dir)


def strip_color(text: str) -> str:
    ansi_escape = re.compile(r"\x1B[@-_][0-?]*[ -/]*[@-~]")
    return ansi_escape.sub("", text)
