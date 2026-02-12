from __future__ import annotations

from pathlib import Path

from invoke import Result
from invoke.context import MockContext

from docs.docs_generation.content_gen_methods import (
    MdxCodeDocumentation,
)
from docs.docs_generation.content_gen_methods.mdx.mdx_code_doc import (
    _wrap_doctest_examples,  # noqa: PLC2701
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


class TestWrapDoctestExamples:
    def test_wraps_bare_doctest_in_code_fence(self) -> None:
        """Bare doctest lines (>>>) following prose are wrapped in a ```python fence."""
        # Arrange
        content = "**Examples:**\n\n>>> foo()\n'bar'"

        # Act
        result = _wrap_doctest_examples(content)

        # Assert
        assert result == "**Examples:**\n\n```python\n>>> foo()\n'bar'\n```"

    def test_leaves_existing_fenced_code_blocks_untouched(self) -> None:
        """Content already inside a fenced code block is not double-wrapped."""
        # Arrange
        content = "```python\ndef foo():\n    pass\n```\n"

        # Act
        result = _wrap_doctest_examples(content)

        # Assert
        assert result == content

    def test_wraps_doctest_with_curly_braces(self) -> None:
        """Curly braces in doctest are preserved inside the fence, preventing MDX/JSX interpolation."""
        # Arrange
        content = '>>> data = {"key": "value"}\n>>> func(data)'

        # Act
        result = _wrap_doctest_examples(content)

        # Assert
        assert result.startswith("```python\n")
        assert result.endswith("\n```")
        assert '{"key": "value"}' in result

    def test_closes_doctest_fence_on_blank_line(self) -> None:
        """A blank line between two doctest blocks produces two separate fenced blocks."""
        # Arrange
        content = ">>> first()\n'a'\n\n>>> second()\n'b'"

        # Act
        result = _wrap_doctest_examples(content)

        # Assert
        assert result.count("```python") == 2
        assert result.count("```") == 4  # 2 opening + 2 closing

    def test_content_with_no_doctest_is_unchanged(self) -> None:
        """Plain markdown without any >>> prompt is returned as-is."""
        # Arrange
        content = "# Title\n\nSome text.\n"

        # Act
        result = _wrap_doctest_examples(content)

        # Assert
        assert result == content


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

    def test_generate_applies_wrap_to_content(self) -> None:
        """MdxCodeDocumentation.generate post-processes content through _wrap_doctest_examples."""
        # Arrange
        mock_context = _make_mock_context(
            {"infrahub_sdk.mod": {"mod.mdx": '>>> data = {"a": 1}\nresult'}},
        )
        doc = MdxCodeDocumentation()

        # Act
        results = doc.generate(context=mock_context, modules_to_document=["infrahub_sdk.mod"])

        # Assert
        content = results["mod.mdx"].content
        assert content.startswith("```python\n")
        assert content.endswith("\n```")

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
