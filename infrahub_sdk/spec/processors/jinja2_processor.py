import json
from pathlib import Path
from typing import Any, Literal

from ...jinja2 import is_jinja2_template
from ...template import Jinja2Template
from ..models import InfrahubObjectContext
from .data_processor import DataProcessor


def load_content(location: str, directory: str | None = None, format: Literal["txt", "json"] = "txt") -> str:

    breakpoint()

    if directory:
        location_path = Path(directory) / Path(location)
    else:
        location_path = Path(location)

    if not location_path.exists():
        raise FileNotFoundError(f"File not found: {location}")

    if format == "txt":
        return location_path.read_text()
    if format == "json":
        return json.loads(location_path.read_text())

    raise ValueError(f"Invalid format: {format}")


class Jinja2DataProcessor(DataProcessor):
    """Process data with Jinja2 templates"""

    @classmethod
    async def _expand_data_with_jinja2(cls, item: str, context: InfrahubObjectContext) -> str:
        file_location = context.get_location().parent.absolute()
        tpl = Jinja2Template(template=item, template_directory=file_location, filters={"load_content": load_content})
        return await tpl.render(variables={"this": {"location": file_location}})

    @classmethod
    async def process_data(cls, data: list[dict[str, Any]], context: InfrahubObjectContext) -> list[dict[str, Any]]:
        for item in data:
            for key, value in item.items():
                if isinstance(value, str) and is_jinja2_template(value):
                    item[key] = await cls._expand_data_with_jinja2(item=value, context=context)

        return data
