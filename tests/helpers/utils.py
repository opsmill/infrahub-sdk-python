"""Utility functions reused throughout integration tests."""

import os
import re
from contextlib import contextmanager
from typing import Generator


@contextmanager
def change_directory(new_directory: str) -> Generator[None, None, None]:
    """Helper function used to change directories in a with block."""
    # Save the current working directory
    original_directory = os.getcwd()

    # Change to the new directory
    try:
        os.chdir(new_directory)
        yield  # Yield control back to the with block

    finally:
        # Change back to the original directory
        os.chdir(original_directory)


def strip_color(text: str) -> str:
    ansi_escape = re.compile(r"\x1B[@-_][0-?]*[ -/]*[@-~]")
    return ansi_escape.sub("", text)
