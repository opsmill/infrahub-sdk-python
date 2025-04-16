from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from typing_extensions import Self
from yaml.parser import ParserError

from .exceptions import FileNotValidError
from .utils import find_files, read_file


class InfrahubFileApiVersion(str, Enum):
    V1 = "infrahub.app/v1"


class InfrahubFileKind(str, Enum):
    MENU = "Menu"
    OBJECT = "Object"


class InfrahubFileData(BaseModel):
    api_version: InfrahubFileApiVersion = Field(InfrahubFileApiVersion.V1, alias="apiVersion")
    kind: InfrahubFileKind
    spec: dict
    metadata: dict = Field(default_factory=dict)


class LocalFile(BaseModel):
    identifier: str | None = None
    location: Path
    multiple_documents: bool = False
    document_position: int | None = None
    content: dict | None = None
    valid: bool = True
    error_message: str | None = None


class YamlFile(LocalFile):
    def load_content(self) -> None:
        try:
            self.content = yaml.safe_load(read_file(self.location))
        except FileNotValidError as exc:
            self.error_message = exc.message
            self.valid = False
            return

        except yaml.YAMLError:
            self.error_message = "Invalid YAML/JSON file"
            self.valid = False
            return

        if not self.content:
            self.error_message = "Empty YAML/JSON file"
            self.valid = False

    def validate_content(self) -> None:
        pass

    @classmethod
    def init(cls, location: Path, multiple_documents: bool, content: dict | None) -> Self:
        if not content:
            return cls._file_is_empty(path=location, has_multiple_document=multiple_documents)

        return cls(location=location, multiple_documents=multiple_documents, content=content)

    @classmethod
    def _file_is_empty(cls, path: Path, has_multiple_document: bool) -> Self:
        return cls(
            location=path, multiple_documents=has_multiple_document, error_message="Invalid YAML/JSON file", valid=False
        )

    @classmethod
    def _file_is_invalid(cls, path: Path, has_multiple_document: bool) -> Self:
        return cls(
            location=path,
            multiple_documents=has_multiple_document,
            error_message="Invalid YAML/JSON file",
            valid=False,
        )

    @classmethod
    def load_file_from_disk(cls, path: Path) -> list[Self]:
        yaml_files: list[Self] = []

        try:
            file_content = read_file(path)

            has_multiple_document = bool(file_content.count("---") > 1)

            if has_multiple_document:
                for content in yaml.safe_load_all(file_content):
                    yaml_files.append(
                        cls.init(location=path, multiple_documents=has_multiple_document, content=content)
                    )

            else:
                yaml_files.append(
                    cls.init(
                        location=path, multiple_documents=has_multiple_document, content=yaml.safe_load(file_content)
                    )
                )

        except FileNotValidError as exc:
            yaml_files.append(
                cls(location=path, multiple_documents=has_multiple_document, error_message=exc.message, valid=False)
            )
        except (yaml.YAMLError, ParserError):
            yaml_files.append(cls._file_is_invalid(path, has_multiple_document))

        if has_multiple_document:
            for idx, file in enumerate(yaml_files):
                file.document_position = idx + 1

        return yaml_files

    @classmethod
    def load_from_disk(cls, paths: list[Path]) -> list[Self]:
        yaml_files: list[Self] = []
        for file_path in paths:
            if file_path.is_file():
                yaml_files.extend(cls.load_file_from_disk(path=file_path))
            elif file_path.is_dir():
                files = find_files(extension=["yaml", "yml", "json"], directory=file_path)
                for item in files:
                    yaml_files.extend(cls.load_file_from_disk(path=item))
            else:
                raise FileNotValidError(name=str(file_path), message=f"{file_path} does not exist!")

        return yaml_files


class InfrahubFile(YamlFile):
    _data: InfrahubFileData | None = None

    @property
    def data(self) -> InfrahubFileData:
        if not self._data:
            raise ValueError("_data hasn't been initialized yet")
        return self._data

    @property
    def version(self) -> InfrahubFileApiVersion:
        return self.data.api_version

    @property
    def kind(self) -> InfrahubFileKind:
        return self.data.kind

    def validate_content(self) -> None:
        if not self.content:
            raise ValueError("Content hasn't been loaded yet")
        self._data = InfrahubFileData(**self.content)


class SchemaFile(YamlFile):
    @property
    def payload(self) -> dict[str, Any]:
        return self.content or {}
