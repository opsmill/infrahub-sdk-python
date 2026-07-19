"""CLI tests for ``infrahubctl schema format``."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from infrahub_sdk.ctl.schema import app
from tests.helpers.cli import remove_ansi_color

runner = CliRunner()

# Widen the Rich console so long tmp_path locations are not wrapped across
# lines, which would break substring assertions on the output.
WIDE = {"COLUMNS": "300"}


UNFORMATTED = """\
---
version: "1.0"
nodes:
  - namespace: Dcim
    name: Device
    # a design note
    label: Device
    attributes:
      - order_weight: 1000
        kind: Text
        name: name
        unique: true
"""


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_format_writes_in_place(tmp_path: Path) -> None:
    schema = _write(tmp_path / "dcim.yml", UNFORMATTED)

    result = runner.invoke(app, env=WIDE, args=["format", str(schema)])

    assert result.exit_code == 0
    output = remove_ansi_color(result.stdout)
    assert f"Reformatted {schema}" in output
    assert "1 file(s) reformatted" in output

    formatted = schema.read_text(encoding="utf-8")
    # Header re-added, keys reordered (name before kind, order_weight last).
    assert formatted.startswith("---\n# yaml-language-server:")
    name_idx = formatted.index("name: name")
    kind_idx = formatted.index("kind: Text")
    weight_idx = formatted.index("order_weight: 1000")
    assert name_idx < kind_idx < weight_idx


def test_format_is_idempotent(tmp_path: Path) -> None:
    schema = _write(tmp_path / "dcim.yml", UNFORMATTED)

    runner.invoke(app, env=WIDE, args=["format", str(schema)])
    once = schema.read_text(encoding="utf-8")
    runner.invoke(app, env=WIDE, args=["format", str(schema)])
    twice = schema.read_text(encoding="utf-8")

    assert once == twice


def test_format_check_reports_and_exits_nonzero(tmp_path: Path) -> None:
    schema = _write(tmp_path / "dcim.yml", UNFORMATTED)
    before = schema.read_text(encoding="utf-8")

    result = runner.invoke(app, env=WIDE, args=["format", str(schema), "--check"])

    assert result.exit_code == 1
    assert "Would reformat" in remove_ansi_color(result.stdout)
    # --check never writes.
    assert schema.read_text(encoding="utf-8") == before


def test_format_check_clean_file_exits_zero(tmp_path: Path) -> None:
    schema = _write(tmp_path / "dcim.yml", UNFORMATTED)
    runner.invoke(app, env=WIDE, args=["format", str(schema)])  # normalise first

    result = runner.invoke(app, env=WIDE, args=["format", str(schema), "--check"])

    assert result.exit_code == 0
    assert "0 file(s) would be reformatted" in remove_ansi_color(result.stdout)


def test_format_diff_prints_and_does_not_write(tmp_path: Path) -> None:
    schema = _write(tmp_path / "dcim.yml", UNFORMATTED)
    before = schema.read_text(encoding="utf-8")

    result = runner.invoke(app, env=WIDE, args=["format", str(schema), "--diff"])

    assert result.exit_code == 0
    output = remove_ansi_color(result.stdout)
    assert "yaml-language-server" in output  # the added header shows up in the diff
    assert schema.read_text(encoding="utf-8") == before


def test_format_preserves_comments(tmp_path: Path) -> None:
    schema = _write(tmp_path / "dcim.yml", UNFORMATTED)

    runner.invoke(app, env=WIDE, args=["format", str(schema)])

    # The comment survives the reformat.
    assert "# a design note" in schema.read_text(encoding="utf-8")


def test_format_skips_non_schema_yaml(tmp_path: Path) -> None:
    menu = _write(tmp_path / "menu.yml", "apiVersion: infrahub.app/v1\nkind: Menu\nspec:\n  data: []\n")

    result = runner.invoke(app, env=WIDE, args=["format", str(menu)])

    assert result.exit_code == 0
    assert "0 file(s) reformatted, 0 unchanged" in remove_ansi_color(result.stdout)


def test_format_directory_recurses(tmp_path: Path) -> None:
    _write(tmp_path / "a.yml", UNFORMATTED)
    _write(tmp_path / "b.yml", UNFORMATTED)

    result = runner.invoke(app, env=WIDE, args=["format", str(tmp_path)])

    assert result.exit_code == 0
    assert "2 file(s) reformatted" in remove_ansi_color(result.stdout)


def test_format_leaves_restricted_namespace_untouched(tmp_path: Path) -> None:
    content = """\
---
version: "1.0"
nodes:
  - namespace: Core
    name: Special
    attributes:
      - order_weight: 1000
        kind: Text
        name: name
"""
    schema = _write(tmp_path / "core.yml", content)

    runner.invoke(app, env=WIDE, args=["format", str(schema)])
    formatted = schema.read_text(encoding="utf-8")

    # The Core node's attribute keys keep their original (scrambled) order.
    weight_idx = formatted.index("order_weight: 1000")
    name_idx = formatted.index("name: name")
    assert weight_idx < name_idx
