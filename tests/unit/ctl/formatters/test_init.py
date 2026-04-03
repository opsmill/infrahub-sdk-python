"""Tests for infrahub_sdk.ctl.formatters package init (OutputFormat, detect/get)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from infrahub_sdk.ctl.formatters import (
    CsvFormatter,
    JsonFormatter,
    OutputFormat,
    TableFormatter,
    YamlFormatter,
    detect_output_format,
    get_formatter,
)


class TestOutputFormat:
    def test_enum_values(self) -> None:
        assert OutputFormat.TABLE == "table"
        assert OutputFormat.JSON == "json"
        assert OutputFormat.CSV == "csv"
        assert OutputFormat.YAML == "yaml"


class TestDetectOutputFormat:
    def test_returns_table_when_tty(self) -> None:
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = True
            assert detect_output_format() == OutputFormat.TABLE

    def test_returns_json_when_not_tty(self) -> None:
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = False
            assert detect_output_format() == OutputFormat.JSON


class TestGetFormatter:
    def test_returns_table_formatter(self) -> None:
        assert isinstance(get_formatter(OutputFormat.TABLE), TableFormatter)

    def test_returns_json_formatter(self) -> None:
        assert isinstance(get_formatter(OutputFormat.JSON), JsonFormatter)

    def test_returns_csv_formatter(self) -> None:
        assert isinstance(get_formatter(OutputFormat.CSV), CsvFormatter)

    def test_returns_yaml_formatter(self) -> None:
        assert isinstance(get_formatter(OutputFormat.YAML), YamlFormatter)

    def test_raises_for_invalid_format(self) -> None:
        with pytest.raises(ValueError, match="Unsupported output format"):
            get_formatter("invalid")  # type: ignore[arg-type]
