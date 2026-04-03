"""Output formatters for the ``infrahub`` end-user CLI.

Provides an ``OutputFormat`` enum for selecting the desired output style and a
``get_formatter`` factory that returns the appropriate ``BaseFormatter``
implementation.
"""

from __future__ import annotations

import sys
from enum import Enum
from typing import TYPE_CHECKING

from infrahub_sdk.ctl.formatters.csv import CsvFormatter
from infrahub_sdk.ctl.formatters.json import JsonFormatter
from infrahub_sdk.ctl.formatters.table import TableFormatter
from infrahub_sdk.ctl.formatters.yaml import YamlFormatter

if TYPE_CHECKING:
    from infrahub_sdk.ctl.formatters.base import BaseFormatter

__all__ = [
    "CsvFormatter",
    "JsonFormatter",
    "OutputFormat",
    "TableFormatter",
    "YamlFormatter",
    "detect_output_format",
    "get_formatter",
]


class OutputFormat(str, Enum):
    """Supported CLI output formats."""

    TABLE = "table"
    JSON = "json"
    CSV = "csv"
    YAML = "yaml"


def detect_output_format() -> OutputFormat:
    """Auto-detect output format based on whether stdout is a TTY.

    Returns:
        ``OutputFormat.TABLE`` when stdout is connected to a terminal,
        ``OutputFormat.JSON`` otherwise (e.g. when piped).
    """
    return OutputFormat.TABLE if sys.stdout.isatty() else OutputFormat.JSON


def get_formatter(output_format: OutputFormat) -> BaseFormatter:
    """Return the appropriate formatter for the given output format.

    Args:
        output_format: The desired output format.

    Returns:
        A ``BaseFormatter`` subclass instance matching *output_format*.

    Raises:
        ValueError: If *output_format* is not a recognised format.
    """
    formatters: dict[OutputFormat, type[BaseFormatter]] = {
        OutputFormat.TABLE: TableFormatter,
        OutputFormat.JSON: JsonFormatter,
        OutputFormat.CSV: CsvFormatter,
        OutputFormat.YAML: YamlFormatter,
    }

    formatter_class = formatters.get(output_format)
    if formatter_class is None:
        msg = f"Unsupported output format: {output_format}"
        raise ValueError(msg)

    return formatter_class()
