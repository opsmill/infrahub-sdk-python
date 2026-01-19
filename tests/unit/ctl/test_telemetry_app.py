"""Tests for the telemetry CLI commands."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from infrahub_sdk.ctl.telemetry import (
    app,
    generate_export_filename,
    sanitize_filename,
)

runner = CliRunner()

pytestmark = pytest.mark.httpx_mock(can_send_already_matched_responses=True)

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock


class TestSanitizeFilename:
    """Tests for the sanitize_filename helper function."""

    def test_simple_name(self) -> None:
        assert sanitize_filename("acme") == "acme"

    def test_name_with_spaces(self) -> None:
        assert sanitize_filename("Acme Corporation") == "acme_corporation"

    def test_name_with_special_chars(self) -> None:
        assert sanitize_filename("Acme & Co.") == "acme_co"

    def test_name_with_multiple_special_chars(self) -> None:
        assert sanitize_filename("Acme!@#$%Corp") == "acme_corp"

    def test_name_with_dashes(self) -> None:
        assert sanitize_filename("acme-corp") == "acme-corp"

    def test_name_with_leading_trailing_special(self) -> None:
        assert sanitize_filename("__acme__") == "acme"

    def test_name_with_multiple_underscores(self) -> None:
        assert sanitize_filename("acme   corp") == "acme_corp"

    def test_uppercase_converted_to_lowercase(self) -> None:
        assert sanitize_filename("ACME") == "acme"

    def test_mixed_case_and_special(self) -> None:
        assert sanitize_filename("Acme Corp. (US)") == "acme_corp_us"


class TestGenerateExportFilename:
    """Tests for the generate_export_filename helper function."""

    def test_with_customer_name(self) -> None:
        with patch("infrahub_sdk.ctl.telemetry.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
            result = generate_export_filename("Acme Corp")
            assert result == Path("acme_corp-telemetry-export-2026-01-15.json")

    def test_without_customer_name(self) -> None:
        with patch("infrahub_sdk.ctl.telemetry.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
            result = generate_export_filename(None)
            assert result == Path("telemetry-export-2026-01-15.json")

    def test_with_empty_customer_name(self) -> None:
        with patch("infrahub_sdk.ctl.telemetry.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
            result = generate_export_filename("")
            assert result == Path("telemetry-export-2026-01-15.json")


class TestTelemetryExportCommand:
    """Tests for the telemetry export command."""

    def test_export_success(self, httpx_mock: HTTPXMock, tmp_path: Path) -> None:
        export_data = {
            "license": {
                "customer_name": "Acme Corp",
                "product_tier": "medium",
            },
            "snapshots": [
                {"date": "2026-01-01", "data": {}},
                {"date": "2026-01-02", "data": {}},
            ],
        }
        httpx_mock.add_response(
            method="GET",
            url="http://mock/api/telemetry/export?all=true",
            json=export_data,
        )

        output_file = tmp_path / "export.json"
        result = runner.invoke(app=app, args=["export", "--all", "--output", str(output_file)])

        assert result.exit_code == 0
        assert "Export Summary" in result.stdout
        assert "Acme Corp" in result.stdout
        assert "medium" in result.stdout
        assert "2" in result.stdout  # 2 snapshots
        assert output_file.exists()

        written_data = json.loads(output_file.read_text())
        assert written_data == export_data

    def test_export_with_date_range(self, httpx_mock: HTTPXMock, tmp_path: Path) -> None:
        export_data = {
            "license": {"customer_name": "Test Co"},
            "snapshots": [{"date": "2026-01-15", "data": {}}],
        }
        httpx_mock.add_response(
            method="GET",
            url="http://mock/api/telemetry/export?from_date=2026-01-01&to_date=2026-01-31",
            json=export_data,
        )

        output_file = tmp_path / "export.json"
        result = runner.invoke(
            app=app,
            args=["export", "--from", "2026-01-01", "--to", "2026-01-31", "--output", str(output_file)],
        )

        assert result.exit_code == 0
        assert output_file.exists()

    def test_export_auto_generated_filename(
        self, httpx_mock: HTTPXMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        export_data = {
            "license": {"customer_name": "Acme Corp"},
            "snapshots": [],
        }
        httpx_mock.add_response(
            method="GET",
            url="http://mock/api/telemetry/export?all=true",
            json=export_data,
        )

        with patch("infrahub_sdk.ctl.telemetry.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
            result = runner.invoke(app=app, args=["export", "--all"])

        assert result.exit_code == 0
        expected_file = tmp_path / "acme_corp-telemetry-export-2026-01-15.json"
        assert expected_file.exists()

    def test_export_error_response(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            method="GET",
            url="http://mock/api/telemetry/export?all=true",
            status_code=500,
            text="Internal Server Error",
        )

        result = runner.invoke(app=app, args=["export", "--all"])

        assert result.exit_code == 1
        assert "Error" in result.stdout

    def test_export_no_snapshots(self, httpx_mock: HTTPXMock, tmp_path: Path) -> None:
        export_data = {
            "license": {"customer_name": "Empty Corp", "product_tier": "small"},
            "snapshots": [],
        }
        httpx_mock.add_response(
            method="GET",
            url="http://mock/api/telemetry/export?all=true",
            json=export_data,
        )

        output_file = tmp_path / "export.json"
        result = runner.invoke(app=app, args=["export", "--all", "--output", str(output_file)])

        assert result.exit_code == 0
        assert "0" in result.stdout  # 0 snapshots


class TestTelemetryListCommand:
    """Tests for the telemetry list command."""

    def test_list_with_files(self, httpx_mock: HTTPXMock) -> None:
        list_response = {
            "files": [
                {"date": "2026-01-01", "filename": "telemetry-abc-2026-01-01.json", "size": "1.2 KB"},
                {"date": "2026-01-02", "filename": "telemetry-abc-2026-01-02.json", "size": "1.3 KB"},
            ]
        }
        httpx_mock.add_response(
            method="GET",
            url="http://mock/api/telemetry/list",
            json=list_response,
        )

        result = runner.invoke(app=app, args=["list"])

        assert result.exit_code == 0
        assert "Local Telemetry Files" in result.stdout
        assert "2026-01-01" in result.stdout
        assert "2026-01-02" in result.stdout
        assert "1.2 KB" in result.stdout

    def test_list_empty(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            method="GET",
            url="http://mock/api/telemetry/list",
            json={"files": []},
        )

        result = runner.invoke(app=app, args=["list"])

        assert result.exit_code == 0
        assert "No telemetry files found" in result.stdout

    def test_list_error_response(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            method="GET",
            url="http://mock/api/telemetry/list",
            status_code=404,
            text="Not Found",
        )

        result = runner.invoke(app=app, args=["list"])

        assert result.exit_code == 1
        assert "Error" in result.stdout


class TestTelemetryStatusCommand:
    """Tests for the telemetry status command."""

    def test_status_enabled_with_license(self, httpx_mock: HTTPXMock) -> None:
        status_response = {
            "enabled": True,
            "storage_path": "/var/lib/infrahub/telemetry",
            "retention_days": 90,
            "files_count": 15,
            "latest_file": "telemetry-abc-2026-01-15.json",
            "license": {
                "customer_name": "Acme Corp",
                "product_tier": "medium",
                "valid": True,
            },
        }
        httpx_mock.add_response(
            method="GET",
            url="http://mock/api/telemetry/status",
            json=status_response,
        )

        result = runner.invoke(app=app, args=["status"])

        assert result.exit_code == 0
        assert "Telemetry Status" in result.stdout
        assert "Yes" in result.stdout  # enabled
        assert "/var/lib/infrahub/telemetry" in result.stdout
        assert "90" in result.stdout
        assert "15" in result.stdout
        assert "Acme Corp" in result.stdout
        assert "medium" in result.stdout

    def test_status_disabled(self, httpx_mock: HTTPXMock) -> None:
        status_response = {
            "enabled": False,
            "storage_path": "/var/lib/infrahub/telemetry",
            "retention_days": 90,
            "files_count": 0,
        }
        httpx_mock.add_response(
            method="GET",
            url="http://mock/api/telemetry/status",
            json=status_response,
        )

        result = runner.invoke(app=app, args=["status"])

        assert result.exit_code == 0
        assert "No" in result.stdout  # disabled

    def test_status_without_license(self, httpx_mock: HTTPXMock) -> None:
        status_response = {
            "enabled": True,
            "storage_path": "/var/lib/infrahub/telemetry",
            "retention_days": 90,
            "files_count": 5,
        }
        httpx_mock.add_response(
            method="GET",
            url="http://mock/api/telemetry/status",
            json=status_response,
        )

        result = runner.invoke(app=app, args=["status"])

        assert result.exit_code == 0
        assert "License Information" not in result.stdout

    def test_status_with_invalid_license(self, httpx_mock: HTTPXMock) -> None:
        status_response = {
            "enabled": True,
            "storage_path": "/var/lib/infrahub/telemetry",
            "retention_days": 90,
            "files_count": 5,
            "license": {
                "customer_name": "Expired Corp",
                "product_tier": "small",
                "valid": False,
            },
        }
        httpx_mock.add_response(
            method="GET",
            url="http://mock/api/telemetry/status",
            json=status_response,
        )

        result = runner.invoke(app=app, args=["status"])

        assert result.exit_code == 0
        assert "Expired Corp" in result.stdout

    def test_status_error_response(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            method="GET",
            url="http://mock/api/telemetry/status",
            status_code=500,
            text="Internal Server Error",
        )

        result = runner.invoke(app=app, args=["status"])

        assert result.exit_code == 1
        assert "Error" in result.stdout
