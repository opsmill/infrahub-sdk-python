from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import ujson
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .utils import generate_request_filename

if TYPE_CHECKING:
    from .types import HTTPMethod


class JSONPlayback(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INFRAHUB_PLAYBACK_")
    directory: str = Field(default=".", description="Directory to read recorded files from")

    async def async_request(
        self,
        url: str,
        method: HTTPMethod,
        headers: dict[str, Any],
        timeout: int,
        payload: dict | None = None,
    ) -> httpx.Response:
        return self._read_request(url=url, method=method, headers=headers, payload=payload, timeout=timeout)

    def sync_request(
        self,
        url: str,
        method: HTTPMethod,
        headers: dict[str, Any],
        timeout: int,
        payload: dict | None = None,
    ) -> httpx.Response:
        return self._read_request(url=url, method=method, headers=headers, payload=payload, timeout=timeout)

    def _read_request(
        self,
        url: str,
        method: HTTPMethod,
        headers: dict[str, Any],
        timeout: int,  # noqa: ARG002
        payload: dict | None = None,
    ) -> httpx.Response:
        content: bytes | None = None
        if payload:
            content = str(json.dumps(payload)).encode("UTF-8")
        request = httpx.Request(method=method.value, url=url, headers=headers, content=content)

        filename = generate_request_filename(request)
        with Path(f"{self.directory}/{filename}.json").open(encoding="utf-8") as fobj:
            data = ujson.load(fobj)

        response = httpx.Response(status_code=data["status_code"], content=data["response_content"], request=request)
        return response
