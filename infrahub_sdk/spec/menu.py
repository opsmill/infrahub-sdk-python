from __future__ import annotations

from pydantic import ValidationError as PydanticValidationError

from ..exceptions import ValidationError
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
            try:
                self._spec = InfrahubMenuFileData.model_validate(self.data.spec)
            except PydanticValidationError as exc:
                raise self._content_error(exc) from exc
        return self._spec

    def validate_content(self) -> None:
        InfrahubFile.validate_content(self)
        if self.kind != InfrahubFileKind.MENU:
            raise ValidationError(identifier=str(self.location), message="File is not an Infrahub Menu file")
        try:
            self._spec = InfrahubMenuFileData.model_validate(self.data.spec)
        except PydanticValidationError as exc:
            raise self._content_error(exc) from exc
