from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


class InfrahubObjectParameters(BaseModel):
    expand_range: bool = False
    render_jinja2: bool = True


class InfrahubObjectContext(BaseModel):
    location: Path | None = None
    repository_id: str | None = None

    def get_location(self) -> Path:
        if self.location is None:
            raise ValueError("Location is not set")
        return self.location
