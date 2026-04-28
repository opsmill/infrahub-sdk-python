from __future__ import annotations

from .constants import HFID_STR_SEPARATOR


def parse_human_friendly_id(hfid: str | list[str]) -> tuple[str | None, list[str]]:
    """Parse a human-friendly ID into a kind and an identifier.

    Accepts the HFID either as a separator-joined string (``"Kind__part1__part2"``) or
    as a list of components. When a string is provided, the first component is treated as
    the node kind only when more than one component is present.

    Args:
        hfid (str | list[str]): The HFID to parse, either as a separator-joined string or as a list of components.

    Returns:
        tuple[str | None, list[str]]: A tuple of ``(kind, identifier_components)``. ``kind`` is
        ``None`` when no kind prefix is present (single-component string or list input).

    Raises:
        ValueError: If ``hfid`` is neither a string nor a list.

    """
    if isinstance(hfid, str):
        hfid_parts = hfid.split(HFID_STR_SEPARATOR)
        if len(hfid_parts) == 1:
            return None, hfid_parts
        return hfid_parts[0], hfid_parts[1:]
    if isinstance(hfid, list):
        return None, hfid
    raise ValueError(f"Invalid human friendly ID: {hfid}")
