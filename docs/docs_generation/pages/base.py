from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docs.docs_generation.content_gen_methods import ADocContentGenMethod


class DocPage:
    """A documentation page whose content is produced by an injected generation method.

    Args:
        content_gen_method: Strategy that produces the page content as a string.

    Example::

        page = DocPage(content_gen_method=Jinja2DocContentGenMethod(...))
        print(page.content())
    """

    def __init__(self, content_gen_method: ADocContentGenMethod) -> None:
        self.content_gen_method = content_gen_method

    def content(self) -> str:
        return self.content_gen_method.apply()


class MDXDocPage:
    """Decorator which is a documentation page that can be written in an ``.mdx`` file.

    Args:
        page: The documentation page whose content will be rendered.
        output_path: File path where the ``.mdx`` output will be written.

    Example::

        mdx = MDXDocPage(page=my_page, output_path=Path("docs/ref/client.mdx"))
        mdx.to_mdx()
    """

    _CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

    def __init__(self, page: DocPage, output_path: Path) -> None:
        self.page = page
        self.output_path = output_path

    def to_mdx(self) -> None:
        rendered = self.page.content()
        rendered = self._sanitize(rendered)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(rendered, encoding="utf-8")
        print(f"Docs saved to: {self.output_path}")

    @classmethod
    def _sanitize(cls, text: str) -> str:
        """Strip non-printable control characters and collapse multiple blank lines."""
        return re.sub(r"\n{3,}", "\n\n", cls._CONTROL_CHAR_RE.sub("", text))
