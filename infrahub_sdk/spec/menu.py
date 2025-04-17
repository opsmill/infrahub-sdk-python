from __future__ import annotations

from ..yaml import InfrahubFile, InfrahubFileKind
from .object import InfrahubObjectFileData, ObjectFile


class InfrahubMenuFileData(InfrahubObjectFileData):
    kind: str = "CoreMenuItem"

    @classmethod
    def enrich_node(cls, data: dict, context: dict) -> dict:
        if "kind" in data and "path" not in data:
            data["path"] = "/objects/" + data["kind"]

        if "list_index" in context and "order_weight" not in data:
            data["order_weight"] = (context["list_index"] + 1) * 1000

        return data


class MenuFile(ObjectFile):
    _spec: InfrahubMenuFileData | None = None

    @property
    def spec(self) -> InfrahubMenuFileData:
        if not self._spec:
            self._spec = InfrahubMenuFileData(**self.data.spec)
        return self._spec

    def validate_content(self) -> None:
        InfrahubFile.validate_content(self)
        if self.kind != InfrahubFileKind.MENU:
            raise ValueError("File is not an Infrahub Menu file")
        self._spec = InfrahubMenuFileData(**self.data.spec)
