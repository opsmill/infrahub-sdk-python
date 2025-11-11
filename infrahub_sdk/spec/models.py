from __future__ import annotations

from pydantic import BaseModel


class InfrahubObjectParameters(BaseModel):
    expand_range: bool = False
