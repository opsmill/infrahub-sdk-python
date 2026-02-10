from __future__ import annotations

from typing import Any

from infrahub_sdk.template.base import ATemplate


class DummyTemplate(ATemplate):
    """Test double that returns fixed content.

    Args:
        content: The string returned by ``render()``.
        **kwargs: Absorbed so that ``DummyTemplate`` can replace
            ``Jinja2Template`` which receives ``template=`` and
            ``template_directory=`` from production code.
    """

    def __init__(self, content: str) -> None:
        self._content = content

    async def render(self, variables: dict[str, Any]) -> str:
        return self._content
