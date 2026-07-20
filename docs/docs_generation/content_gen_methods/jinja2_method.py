from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from .base import ADocContentGenMethod

if TYPE_CHECKING:
    from infrahub_sdk.template import Jinja2Template


class Jinja2DocContentGenMethod(ADocContentGenMethod):
    """Render a template using a ``Jinja2Template``.

    The template engine is async; rendering is run synchronously via ``asyncio.run``.

    Args:
        template: A ``Jinja2Template`` instance.
        template_variables: Variables passed to the template during rendering.

    Example::

        template = Jinja2Template(
            template=Path("sdk_template_reference.j2"),
            template_directory=docs_dir / "_templates",
        )
        method = Jinja2DocContentGenMethod(
            template=template,
            template_variables={"builtin": BUILTIN_FILTERS},
        )
        content = method.apply()

    """

    def __init__(self, template: Jinja2Template, template_variables: dict[str, Any]) -> None:
        self.template = template
        self.template_variables = template_variables

    def apply(self) -> str:
        return asyncio.run(self.template.render(variables=self.template_variables))
