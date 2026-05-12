from __future__ import annotations

import re
from dataclasses import dataclass, field

from .mdx_section import ASection, MdxSection


@dataclass
class CollapsedOverloadSection(ASection):
    """Collapses a group of overloaded method sections into one primary entry
    followed by a collapsible ``<details>`` block with the remaining overloads.

    The *primary* overload is the one with the most parameters (excluding
    ``self``).  On ties, the first in source order wins.

    Example::

        >>> section = CollapsedOverloadSection.from_overloads(overload_sections)
        >>> section.heading  # delegates to primary
        '#### `get`'
    """

    primary: MdxSection
    others: list[MdxSection] = field(default_factory=list)

    @property
    def heading(self) -> str:
        """Return the heading of the primary overload."""
        return self.primary.heading

    @property
    def content(self) -> list[str]:
        """Return primary content followed by a ``<details>`` block for the other overloads."""
        if not self.others:
            return self.primary.content

        result = list(self.primary.content)
        inner = [line for other in self.others for line in other.lines]
        count = len(self.others)
        noun = "overload" if count == 1 else "overloads"
        result.extend(_HtmlDetailsBlock(f"Show {count} other {noun}", inner).lines())
        return result

    @classmethod
    def from_overloads(cls, sections: list[MdxSection]) -> CollapsedOverloadSection:
        """Create from a list of overloaded :class:`MdxSection` objects.

        Selects the overload with the most parameters as *primary*.
        On ties, the first in source order wins.

        Raises:
            ValueError: If ``sections`` is empty.

        """
        if not sections:
            raise ValueError("Cannot create CollapsedOverloadSection from an empty list")

        primary = max(sections, key=lambda s: MethodSignature(s).param_count())
        others = [s for s in sections if s is not primary]
        return cls(primary=primary, others=others)


# --- Private collaborators ---


@dataclass(frozen=True)
class _HtmlDetailsBlock:
    """A collapsible HTML ``<details>`` block."""

    summary: str
    inner_lines: list[str]

    def lines(self) -> list[str]:
        """Return the full block as a list of MDX lines."""
        return ["", "<details>", f"<summary>{self.summary}</summary>", "", *self.inner_lines, "", "</details>"]


_CODE_FENCE_PATTERN = re.compile(r"^```python\s*$")
_CODE_FENCE_END = re.compile(r"^```\s*$")


def _extract_text(section: MdxSection) -> str:
    """Extract the signature from the first code fence in *section*."""
    in_fence = False
    sig_lines: list[str] = []
    for line in section.content:
        if not in_fence and _CODE_FENCE_PATTERN.match(line):
            in_fence = True
            continue
        if in_fence:
            if _CODE_FENCE_END.match(line):
                break
            sig_lines.append(line)
    return " ".join(sig_lines).strip()


def _split_params(text: str) -> list[str]:
    """Split *text* on commas that are not inside brackets."""
    depth = 0
    tokens: list[str] = []
    current: list[str] = []
    for char in text:
        if char in {"[", "(", "{"}:
            depth += 1
            current.append(char)
        elif char in {"]", ")", "}"}:
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            tokens.append("".join(current))
            current = []
        else:
            current.append(char)
    if current:
        tokens.append("".join(current))
    return tokens


class MethodSignature:
    """A Python method signature extracted from an MDX code fence.

    Parses the raw signature text and counts comma-separated parameters
    at the top level, respecting bracket nesting for generic types
    like ``dict[str, int]``.
    """

    def __init__(self, section: MdxSection) -> None:
        self._text = _extract_text(section)

    def param_count(self) -> int:
        """Return the number of parameters excluding ``self``."""
        params_text = self._extract_params_text()
        if not params_text.strip():
            return 0
        tokens = _split_params(params_text)
        return len([t for t in tokens if t.strip() and t.strip() != "self"])

    def return_type(self) -> str:
        """Return the return-type annotation (e.g. ``"None"``), or ``""`` if absent."""
        _, sep, ret = self._text.rpartition(")")
        if not sep:
            return ""
        _, arrow, after_arrow = ret.partition("->")
        return after_arrow.strip() if arrow else ""

    def _extract_params_text(self) -> str:
        """Extract the text between the first ``(`` and its last ``)``."""
        _, sep, after_open = self._text.partition("(")
        if not sep:
            return ""
        params, _, _ = after_open.rpartition(")")
        return params
