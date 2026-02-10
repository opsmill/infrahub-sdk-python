from __future__ import annotations

from pathlib import Path
from typing import Any

import jinja2

from .base import ADocContentGenMethod


class Jinja2DocContentGenMethod(ADocContentGenMethod):
    """Render a Jinja2 template file with the provided variables.

    The template is loaded with ``trim_blocks=True`` and no auto-escaping.

    Args:
        template_path: Absolute path to the ``.j2`` template file.
        template_variables: Variables passed to the template during rendering.

    Example::

        method = Jinja2DocContentGenMethod(
            template_path=docs_dir / "_templates" / "sdk_config.j2",
            template_variables={"properties": props},
        )
        content = method.apply()
    """

    def __init__(self, template_path: Path, template_variables: dict[str, Any]) -> None:
        self.template_path = template_path
        self.template_variables = template_variables

    def apply(self) -> str:
        template_text = self.template_path.read_text(encoding="utf-8")
        environment = jinja2.Environment(
            trim_blocks=True,
            autoescape=jinja2.select_autoescape(default_for_string=False),
        )
        template = environment.from_string(template_text)
        return template.render(**self.template_variables)
