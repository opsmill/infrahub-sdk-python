from __future__ import annotations

from pathlib import Path

from invoke import Result
from invoke.context import MockContext

from docs.docs_generation.content_gen_methods import (
    MdxCodeDocumentation,
)


def _make_mock_context(
    module_files: dict[str, dict[str, str]],
    calls: list[str] | None = None,
) -> MockContext:
    """Build a ``MockContext`` whose ``run()`` writes files based on requested modules.

    Args:
        module_files: Mapping of module name to its output files
            (e.g. ``{"infrahub_sdk.node": {"node.mdx": "# Node"}}``).
            Only files belonging to modules present in the ``mdxify`` command
            are written to the output directory.
        calls: If provided, each executed command string is appended to this
            list so the caller can verify how many times ``run()`` was invoked.
    """
    ctx = MockContext(run=Result())

    def fake_run(cmd: str, **kwargs: object) -> Result:
        if calls is not None:
            calls.append(cmd)
        prefix, output_dir_str = cmd.split("--output-dir ")
        output_dir = Path(output_dir_str.strip())
        requested_modules = prefix.replace("mdxify ", "").split()
        for module in requested_modules:
            for filename, content in module_files.get(module, {}).items():
                (output_dir / filename).write_text(content, encoding="utf-8")
        return Result()

    ctx.run.side_effect = fake_run
    return ctx


def _generate_one(raw_content: str) -> str:
    """Run a single piece of raw content through ``generate()`` and return the processed result."""
    mock_context = _make_mock_context({"mod": {"mod.mdx": raw_content}})
    doc = MdxCodeDocumentation()
    return doc.generate(context=mock_context, modules_to_document=["mod"])["mod.mdx"].content


class TestDoctestWrapping:
    def test_wraps_bare_doctest_in_code_fence(self) -> None:
        """Bare doctest lines (>>>) following prose are wrapped in a ```python fence."""
        # Arrange
        raw = "**Examples:**\n\n>>> foo()\n'bar'"

        # Act
        result = _generate_one(raw)

        # Assert
        assert result == "**Examples:**\n\n```python\n>>> foo()\n'bar'\n```"

    def test_leaves_existing_fenced_code_blocks_untouched(self) -> None:
        """Content already inside a fenced code block is not double-wrapped."""
        # Arrange
        raw = "```python\ndef foo():\n    pass\n```\n"

        # Act
        result = _generate_one(raw)

        # Assert
        assert result == raw

    def test_wraps_doctest_with_curly_braces(self) -> None:
        """Curly braces in doctest are preserved inside the fence, preventing MDX/JSX interpolation."""
        # Arrange
        raw = '>>> data = {"key": "value"}\n>>> func(data)'

        # Act
        result = _generate_one(raw)

        # Assert
        assert result.startswith("```python\n")
        assert result.endswith("\n```")
        assert '{"key": "value"}' in result

    def test_closes_doctest_fence_on_blank_line(self) -> None:
        """A blank line between two doctest blocks produces two separate fenced blocks."""
        # Arrange
        raw = ">>> first()\n'a'\n\n>>> second()\n'b'"

        # Act
        result = _generate_one(raw)

        # Assert
        assert result.count("```python") == 2
        assert result.count("```") == 4  # 2 opening + 2 closing

    def test_content_with_no_doctest_is_unchanged(self) -> None:
        """Plain Markdown without any >>> prompt is returned as-is."""
        # Arrange
        raw = "# Title\n\nSome text.\n"

        # Act
        result = _generate_one(raw)

        # Assert
        assert result == raw


class TestMdxCodeDocumentation:
    def test_generate_default_filter_returns_filtered_files(self) -> None:
        """Files matching the default filter (``__init__``) are excluded."""
        # Arrange
        mock_context = _make_mock_context(
            {
                "infrahub_sdk.node": {
                    "infrahub_sdk-node-node.mdx": "# Node",
                    "infrahub_sdk-node-__init__.mdx": "# Init (should be filtered)",
                },
                "infrahub_sdk.client": {
                    "infrahub_sdk-client.mdx": "# Client",
                },
            }
        )
        doc = MdxCodeDocumentation()

        # Act
        results = doc.generate(
            context=mock_context,
            modules_to_document=["infrahub_sdk.node", "infrahub_sdk.client"],
        )

        # Assert
        assert "infrahub_sdk-node-node.mdx" in results
        assert "infrahub_sdk-client.mdx" in results
        assert "infrahub_sdk-node-__init__.mdx" not in results

    def test_generate_runs_mdxify_only_once(self) -> None:
        """Second call returns the same result without re-running mdxify."""
        # Arrange
        calls: list[str] = []
        mock_context = _make_mock_context(
            {"infrahub_sdk.client": {"infrahub_sdk-client.mdx": "# Client"}},
            calls=calls,
        )
        doc = MdxCodeDocumentation()

        # Act
        result1 = doc.generate(
            context=mock_context,
            modules_to_document=["infrahub_sdk.client"],
        )
        result2 = doc.generate(
            context=mock_context,
            modules_to_document=["infrahub_sdk.client"],
        )

        # Assert
        assert result1 is result2
        assert len(calls) == 1

    def test_generate_with_custom_filters(self) -> None:
        """Custom file_filters exclude files whose names contain the filter substring."""
        # Arrange
        mock_context = _make_mock_context(
            {
                "infrahub_sdk.node": {
                    "infrahub_sdk-node-_private.mdx": "# Private",
                    "infrahub_sdk-node-public.mdx": "# Public",
                },
            }
        )
        doc = MdxCodeDocumentation(file_filters=["_private"])

        # Act
        results = doc.generate(
            context=mock_context,
            modules_to_document=["infrahub_sdk.node"],
        )

        # Assert
        assert "infrahub_sdk-node-public.mdx" in results
        assert "infrahub_sdk-node-_private.mdx" not in results

    def test_generate_empty_output(self) -> None:
        """When mdxify produces no files for the requested module, an empty dict is returned."""
        # Arrange
        mock_context = _make_mock_context({})
        doc = MdxCodeDocumentation()

        # Act
        results = doc.generate(
            context=mock_context,
            modules_to_document=["infrahub_sdk.empty"],
        )

        # Assert
        assert results == {}

    def test_generate_only_includes_requested_modules(self) -> None:
        """Only files belonging to requested modules are returned."""
        # Arrange
        mock_context = _make_mock_context(
            {
                "infrahub_sdk.node": {
                    "infrahub_sdk-node-node.mdx": "# Node",
                },
                "infrahub_sdk.client": {
                    "infrahub_sdk-client.mdx": "# Client",
                },
            }
        )
        doc = MdxCodeDocumentation()

        # Act
        results = doc.generate(
            context=mock_context,
            modules_to_document=["infrahub_sdk.node"],
        )

        # Assert
        assert "infrahub_sdk-node-node.mdx" in results
        assert "infrahub_sdk-client.mdx" not in results

    def test_generate_reruns_for_different_modules(self) -> None:
        """Calling generate with different modules re-runs mdxify."""
        # Arrange
        calls: list[str] = []
        mock_context = _make_mock_context(
            {
                "infrahub_sdk.node": {"infrahub_sdk-node-node.mdx": "# Node"},
                "infrahub_sdk.client": {"infrahub_sdk-client.mdx": "# Client"},
            },
            calls=calls,
        )
        doc = MdxCodeDocumentation()

        # Act
        result_node = doc.generate(context=mock_context, modules_to_document=["infrahub_sdk.node"])
        result_client = doc.generate(context=mock_context, modules_to_document=["infrahub_sdk.client"])

        # Assert
        assert len(calls) == 2
        assert "infrahub_sdk-node-node.mdx" in result_node
        assert "infrahub_sdk-client.mdx" in result_client


class TestSourcePathDerivation:
    def test_nested_module(self) -> None:
        """Deeply nested mdxify filename resolves to the correct Python source path."""
        # Arrange
        mock_context = _make_mock_context(
            {"infrahub_sdk.node": {"infrahub_sdk-node-node.mdx": "# Node"}},
        )
        doc = MdxCodeDocumentation()

        # Act
        results = doc.generate(context=mock_context, modules_to_document=["infrahub_sdk.node"])

        # Assert
        mdx = results["infrahub_sdk-node-node.mdx"]
        assert mdx.name == "infrahub_sdk-node-node.mdx"
        assert mdx.source_path == Path("infrahub_sdk/node/node.py")

    def test_top_level_module(self) -> None:
        """Single-dash mdxify filename resolves to a top-level module source path."""
        # Arrange
        mock_context = _make_mock_context(
            {"infrahub_sdk.client": {"infrahub_sdk-client.mdx": "# Client"}},
        )
        doc = MdxCodeDocumentation()

        # Act
        results = doc.generate(context=mock_context, modules_to_document=["infrahub_sdk.client"])

        # Assert
        assert results["infrahub_sdk-client.mdx"].source_path == Path("infrahub_sdk/client.py")

    def test_single_name(self) -> None:
        """Filename without dashes resolves to a single .py file."""
        # Arrange
        mock_context = _make_mock_context({"mod": {"mod.mdx": "# Mod"}})
        doc = MdxCodeDocumentation()

        # Act
        results = doc.generate(context=mock_context, modules_to_document=["mod"])

        # Assert
        assert results["mod.mdx"].source_path == Path("mod.py")
