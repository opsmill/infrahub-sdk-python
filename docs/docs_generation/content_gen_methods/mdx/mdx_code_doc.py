from __future__ import annotations

import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from invoke import Context


def _wrap_doctest_examples(content: str) -> str:
    """Wrap bare ``>>>`` doctest blocks in fenced code blocks for MDX compatibility.

    mdxify does not fence doctest examples, so curly braces and brackets
    in those lines cause MDX/acorn parse errors.
    """
    lines = content.split("\n")
    result: list[str] = []
    in_fence = False
    in_doctest = False

    for line in lines:
        if line.startswith("```"):
            if in_doctest:
                result.append("```")
                in_doctest = False
            in_fence = not in_fence
            result.append(line)
            continue

        if in_fence:
            result.append(line)
            continue

        if line.startswith(">>>"):
            if not in_doctest:
                result.append("```python")
                in_doctest = True
            result.append(line)
        elif in_doctest:
            if not line.strip() or line.startswith("#"):
                result.append("```")
                in_doctest = False
                result.append(line)
            else:
                result.append(line)
        else:
            result.append(line)

    if in_doctest:
        result.append("```")

    return "\n".join(result)


def _source_path_from_mdx_name(mdx_filename: str) -> Path:
    """Derive the Python source file path from an mdxify output filename.

    mdxify names output files using ``-`` as a path separator, e.g.
    ``infrahub_sdk-node-node.mdx`` comes from ``infrahub_sdk/node/node.py``.
    """
    stem = Path(mdx_filename).stem
    return Path(stem.replace("-", "/")).with_suffix(".py")


@dataclass
class MdxFile:
    """Content of a single ``.mdx`` file produced by mdxify."""

    name: str
    content: str
    source_path: Path


class ACodeDocumentation(ABC):
    """Abstract base for code documentation generators."""

    @abstractmethod
    def generate(self, context: Context, modules_to_document: list[str]) -> dict[str, MdxFile]: ...


class MdxCodeDocumentation(ACodeDocumentation):
    """Run mdxify once and cache the resulting files.

    Args:
        file_filters: Substrings to exclude from output filenames.
            Defaults to ``["__init__"]``.

    Example::

        doc = MdxCodeDocumentation()
        files = doc.generate(context=ctx, modules_to_document=["infrahub_sdk.node"])
    """

    def __init__(
        self,
        file_filters: list[str] | None = None,
    ) -> None:
        self.file_filters = file_filters or ["__init__"]
        self._cache: dict[frozenset[str], dict[str, MdxFile]] = {}

    def generate(self, context: Context, modules_to_document: list[str]) -> dict[str, MdxFile]:
        """Return mdxify results, re-running the tool when *modules_to_document* changes."""
        key = frozenset(modules_to_document)
        if key not in self._cache:
            self._cache[key] = self._execute_mdxify(context, modules_to_document)
        return self._cache[key]

    def _execute_mdxify(self, context: Context, modules_to_document: list[str]) -> dict[str, MdxFile]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            exec_cmd = f"mdxify {' '.join(modules_to_document)} --output-dir {tmp_dir}"
            context.run(exec_cmd, pty=True)

            results: dict[str, MdxFile] = {}
            for mdx_file in Path(tmp_dir).glob("*.mdx"):
                if any(f.lower() in mdx_file.name for f in self.file_filters):
                    continue
                content = _wrap_doctest_examples(mdx_file.read_text(encoding="utf-8"))
                results[mdx_file.name] = MdxFile(
                    name=mdx_file.name,
                    content=content,
                    source_path=_source_path_from_mdx_name(mdx_file.name),
                )

            return results
