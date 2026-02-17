from __future__ import annotations

import re
from dataclasses import dataclass, field

from .mdx_section import ASection, MdxSection


@dataclass
class SignatureParameterCount:
    """Number of parameters in a Python method signature, excluding ``self``.

    Parses the raw signature text (as rendered in MDX code fences) and
    counts comma-separated parameters at the top level, respecting
    bracket nesting for generic types like ``dict[str, int]``.

    Example::

        >>> SignatureParameterCount("get(self, kind: str, id: int)").value()
        2
    """

    signature: str

    def value(self) -> int:
        """Return the number of parameters excluding ``self``."""
        params_text = self._extract_params_text()
        if not params_text.strip():
            return 0
        tokens = self._split_top_level(params_text)
        return len([t for t in tokens if t.strip() and t.strip() != "self"])

    def _extract_params_text(self) -> str:
        """Extract the text between the first ``(`` and its matching ``)``."""
        start = self.signature.find("(")
        if start == -1:
            return ""
        depth = 0
        for i in range(start, len(self.signature)):
            char = self.signature[i]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return self.signature[start + 1 : i]
        return self.signature[start + 1 :]

    def _split_top_level(self, text: str) -> list[str]:
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


_CODE_FENCE_PATTERN = re.compile(r"^```python\s*$")
_CODE_FENCE_END = re.compile(r"^```\s*$")


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
        return self.primary.heading

    @property
    def content(self) -> list[str]:
        if not self.others:
            return self.primary.content

        result = list(self.primary.content)

        count = len(self.others)
        noun = "overload" if count == 1 else "overloads"
        result.extend(("", "<details>", f"<summary>Show {count} other {noun}</summary>", ""))

        for other in self.others:
            result.extend(other.lines)

        result.extend(("", "</details>"))
        return result

    @classmethod
    def from_overloads(cls, sections: list[MdxSection]) -> CollapsedOverloadSection:
        """Create from a list of overloaded :class:`MdxSection` objects.

        Selects the overload with the most parameters as *primary*.
        On ties, the first in source order wins.
        """
        if not sections:
            raise ValueError("Cannot create CollapsedOverloadSection from an empty list")

        best_index = 0
        best_count = -1
        for i, section in enumerate(sections):
            sig = _extract_signature(section)
            count = SignatureParameterCount(sig).value() if sig else 0
            if count > best_count:
                best_count = count
                best_index = i

        primary = sections[best_index]
        others = [s for i, s in enumerate(sections) if i != best_index]
        return cls(primary=primary, others=others)


def _extract_signature(section: MdxSection) -> str:
    """Extract the Python signature from the first code fence in *section*."""
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
