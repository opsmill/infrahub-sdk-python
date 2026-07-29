"""CLI tests for ``infrahubctl schema format``."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from typer.testing import CliRunner

from infrahub_sdk.ctl import schema as schema_module
from infrahub_sdk.ctl.schema import app
from infrahub_sdk.ctl.schema_format import FormatError
from tests.helpers.cli import remove_ansi_color

if TYPE_CHECKING:
    import pytest

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
    # Colour is applied via Rich styling, not literal markup tags.
    assert "[green]" not in output
    assert "[red]" not in output
    assert schema.read_text(encoding="utf-8") == before


def test_format_preserves_comments(tmp_path: Path) -> None:
    schema = _write(tmp_path / "dcim.yml", UNFORMATTED)

    result = runner.invoke(app, env=WIDE, args=["format", str(schema)])

    assert result.exit_code == 0
    # The comment survives the reformat.
    assert "# a design note" in schema.read_text(encoding="utf-8")


def test_format_skips_multi_document_file(tmp_path: Path) -> None:
    multi = _write(
        tmp_path / "multi.yml",
        '---\nversion: "1.0"\nnodes: []\n---\nversion: "1.0"\ngenerics: []\n',
    )

    result = runner.invoke(app, env=WIDE, args=["format", str(multi)])

    assert result.exit_code == 0
    output = remove_ansi_color(result.stdout)
    assert "multi-document files are not supported" in output
    # Left untouched.
    assert multi.read_text(encoding="utf-8").count("---") == 2


def test_format_reports_invalid_file(tmp_path: Path) -> None:
    bad = _write(tmp_path / "bad.yml", 'version: "1.0"\nnodes: [unclosed\n')

    result = runner.invoke(app, env=WIDE, args=["format", str(bad)])

    assert result.exit_code == 1


def test_format_duplicate_key_is_per_file_error(tmp_path: Path) -> None:
    # A duplicate key (which `schema load`/PyYAML tolerate) must be reported as
    # a per-file error without aborting the run: other files still format.
    _write(
        tmp_path / "a_dup.yml",
        '---\nversion: "1.0"\nnodes:\n  - namespace: Dcim\n    name: Device\n    label: A\n    label: B\n',
    )
    good = _write(tmp_path / "b_good.yml", UNFORMATTED)

    result = runner.invoke(app, env=WIDE, args=["format", str(tmp_path)])

    assert result.exit_code == 1
    output = remove_ansi_color(result.stdout)
    assert "could not parse as YAML" in output
    # The valid file was still processed despite the earlier bad one.
    assert good.read_text(encoding="utf-8").startswith("---\n# yaml-language-server:")


def test_format_reports_format_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    schema = _write(tmp_path / "dcim.yml", UNFORMATTED)

    def _raise(*_args: object, **_kwargs: object) -> str:
        raise FormatError("would change content")

    monkeypatch.setattr(schema_module, "format_schema_text", _raise)

    result = runner.invoke(app, env=WIDE, args=["format", str(schema)])

    assert result.exit_code == 1
    assert "would change content" in remove_ansi_color(result.stdout)


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


def test_format_opt_in_flags(tmp_path: Path) -> None:
    content = """\
---
version: "1.0"
nodes:
  - namespace: Dcim
    name: Device
    relationships:
      - name: b_rel
        peer: DcimB
        optional: true
        cardinality: many
        order_weight: 2000
      - name: a_rel
        peer: DcimA
        kind: Attribute
        cardinality: one
"""
    schema = _write(tmp_path / "dcim.yml", content)

    result = runner.invoke(
        app,
        env=WIDE,
        args=["format", str(schema), "--strip-defaults", "--sort-by-order-weight", "--backfill-order-weight"],
    )

    assert result.exit_code == 0
    out = schema.read_text(encoding="utf-8")
    rels = yaml.safe_load(out)["nodes"][0]["relationships"]
    # backfill filled a_rel (was missing) with 1000, so it sorts before b_rel (2000).
    assert [r["name"] for r in rels] == ["a_rel", "b_rel"]
    # strip-defaults removed the redundant optional:true / cardinality:many on b_rel.
    assert "optional" not in rels[1]
    assert "cardinality" not in rels[1]


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
