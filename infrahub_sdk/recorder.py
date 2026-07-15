from __future__ import annotations

import enum
from pathlib import Path
from typing import Protocol, runtime_checkable

import httpx
import orjson
from pydantic_settings import BaseSettings, SettingsConfigDict

from .utils import generate_request_filename


class RecorderType(str, enum.Enum):
    NONE = "none"
    JSON = "json"


@runtime_checkable
class Recorder(Protocol):
    def record(self, response: httpx.Response) -> None:
        """Record the response from Infrahub."""


class NoRecorder:
    @staticmethod
    def record(response: httpx.Response) -> None:
        """The NoRecorder just silently returns."""

    @classmethod
    def default(cls) -> NoRecorder:
        return cls()

    def __eq__(self, other: object) -> bool:
        return isinstance(other, NoRecorder)

    def __hash__(self) -> int:
        return hash(self.__class__)


class JSONRecorder(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INFRAHUB_JSON_RECORDER_")
    directory: str = "."
    host: str = ""

    def record(self, response: httpx.Response) -> None:
        self._set_url_host(response)
        filename = generate_request_filename(response.request)
        data = {
            "status_code": response.status_code,
            "method": response.request.method,
            "url": str(response.request.url),
            "headers": dict(response.request.headers),
            "response_content": response.content.decode("utf-8"),
            "request_content": response.request.content.decode("utf-8"),
        }

        serialized = orjson.dumps(data, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS).decode()
        Path(f"{self.directory}/{filename}.json").write_text(serialized, encoding="utf-8")

    def _set_url_host(self, response: httpx.Response) -> None:
        if not self.host:
            return
        original = str(response.request.url)
        if response.request.url.port:
            modified = original.replace(
                f"{response.request.url.scheme}://{response.request.url.host}:",
                f"{response.request.url.scheme}://{self.host}:",
            )
        else:
            modified = original.replace(
                f"{response.request.url.scheme}://{response.request.url.host}/",
                f"{response.request.url.scheme}://{self.host}/",
            )

        response.request.url = httpx.URL(url=modified)
