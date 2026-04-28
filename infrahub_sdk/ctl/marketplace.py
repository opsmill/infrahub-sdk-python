from __future__ import annotations

import asyncio
import sys
from enum import Enum
from pathlib import Path
from typing import Any, Literal, NoReturn
from urllib.parse import urlparse

import httpx
import typer
from rich.console import Console

from ..async_typer import AsyncTyper
from ..config import ConfigBase as _SdkConfig
from ..ctl.config import SETTINGS
from ..ctl.parameters import CONFIG_PARAM
from ..ctl.utils import catch_exception

app = AsyncTyper()
console = Console()
err_console = Console(stderr=True)

MarketplaceItemType = Literal["schema", "collection"]


class _ErrorClass(Enum):
    INVALID_INPUT = "invalid-input"
    NOT_FOUND = "not-found"
    NETWORK = "network"

    @property
    def exit_code(self) -> int:
        return 2 if self is _ErrorClass.NETWORK else 1


def _fail(error_class: _ErrorClass, message: str) -> NoReturn:
    err_console.print(f"[red]{message}")
    raise typer.Exit(error_class.exit_code)


def _status_console(stdout: bool) -> Console:
    return err_console if stdout else console


@app.callback()
def callback() -> None:
    """Browse and download schemas from the Infrahub Marketplace."""


def _parse_identifier(identifier: str) -> tuple[str, str]:
    parts = identifier.split("/")
    if len(parts) != 2 or not all(parts):
        _fail(_ErrorClass.INVALID_INPUT, f"Invalid identifier '{identifier}'. Expected format: namespace/name")
    return parts[0], parts[1]


def _host_from(base_url: str) -> str:
    return urlparse(base_url).netloc or base_url


def _schema_url(base_url: str, namespace: str, name: str, version: str | None = None) -> str:
    if version:
        return f"{base_url}/api/v1/schemas/{namespace}/{name}/versions/{version}/download"
    return f"{base_url}/api/v1/schemas/{namespace}/{name}/download"


def _collection_url(base_url: str, namespace: str, name: str) -> str:
    return f"{base_url}/api/v1/collections/{namespace}/{name}/download"


def _is_transport_failure(r: object) -> bool:
    if isinstance(r, Exception):
        return True
    return isinstance(r, httpx.Response) and r.status_code >= 500


def _mkdir_or_fail(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _fail(_ErrorClass.INVALID_INPUT, f"Cannot write to '{path}': {exc}")


def _make_http_client(sdk_cfg: _SdkConfig) -> httpx.AsyncClient:
    """Build an httpx client that inherits the SDK's proxy and TLS configuration."""
    proxy_kwargs: dict[str, Any] = {}
    if sdk_cfg.proxy:
        proxy_kwargs["proxy"] = sdk_cfg.proxy
    elif sdk_cfg.proxy_mounts.is_set:
        proxy_kwargs["mounts"] = {
            key: httpx.AsyncHTTPTransport(proxy=val)
            for key, val in sdk_cfg.proxy_mounts.model_dump(by_alias=True).items()
            if val
        }
    return httpx.AsyncClient(follow_redirects=True, verify=sdk_cfg.tls_context, **proxy_kwargs)


async def _detect_item_type(
    client: httpx.AsyncClient,
    base_url: str,
    namespace: str,
    name: str,
    *,
    stdout: bool,
) -> tuple[MarketplaceItemType, httpx.Response]:
    """Probe schema and collection endpoints in parallel. Schema wins on 200-200.

    Returns the resolved type and the winning 200 response so the caller can reuse
    it instead of re-fetching the same URL.
    """
    schema_url = _schema_url(base_url, namespace, name)
    collection_url = _collection_url(base_url, namespace, name)

    schema_resp, collection_resp = await asyncio.gather(
        client.get(schema_url),
        client.get(collection_url),
        return_exceptions=True,
    )

    if isinstance(schema_resp, httpx.Response) and schema_resp.status_code == 200:
        if isinstance(collection_resp, httpx.Response) and collection_resp.status_code == 200:
            _status_console(stdout).print(
                f"[yellow]Note: '{namespace}/{name}' exists as both a schema and a collection. "
                "Resolving as schema. Pass --collection to force the collection path."
            )
        return "schema", schema_resp
    if isinstance(collection_resp, httpx.Response) and collection_resp.status_code == 200:
        return "collection", collection_resp

    if _is_transport_failure(schema_resp) or _is_transport_failure(collection_resp):
        _fail(
            _ErrorClass.NETWORK,
            f"Could not reach marketplace at {base_url}. Check your connection or --marketplace-url.",
        )

    _fail(
        _ErrorClass.NOT_FOUND,
        f"No schema or collection named '{namespace}/{name}' found on {_host_from(base_url)}.",
    )


async def _download_schema(
    client: httpx.AsyncClient,
    base_url: str,
    namespace: str,
    name: str,
    version: str | None,
    output_dir: Path,
    *,
    stdout: bool,
    prefetched: httpx.Response | None = None,
    schema_confirmed_exists: bool = False,
) -> None:
    """Download a single schema and write it to disk or stdout.

    When ``prefetched`` is supplied and ``version`` is None, reuses the response
    instead of re-fetching the unversioned download URL.
    ``schema_confirmed_exists`` signals that the schema is known to exist (e.g. from
    the auto-detect probe), so a 404 on a versioned URL is reported as version-not-found
    rather than the generic not-found message.
    """
    if prefetched is not None and version is None:
        resp = prefetched
    else:
        resp = await client.get(_schema_url(base_url, namespace, name, version=version))

    if resp.status_code == 404:
        if version is not None and schema_confirmed_exists:
            _fail(
                _ErrorClass.NOT_FOUND,
                f"Schema '{namespace}/{name}' has no published version '{version}'. "
                "Run without --version for the latest.",
            )
        _fail(
            _ErrorClass.NOT_FOUND,
            f"No schema named '{namespace}/{name}' found on {_host_from(base_url)}.",
        )
    resp.raise_for_status()

    resolved_version = version or resp.headers.get("x-schema-version", "latest")

    if stdout:
        sys.stdout.write(resp.text)
        if not resp.text.endswith("\n"):
            sys.stdout.write("\n")
        err_console.print(f"[green]Fetched schema {namespace}/{name} v{resolved_version}")
        return

    filename = f"{name}.yml"
    _mkdir_or_fail(output_dir)
    file_path = output_dir / filename
    file_path.write_text(resp.text, encoding="utf-8")

    console.print(f"[green]Downloaded schema {namespace}/{name} v{resolved_version} -> {file_path}")


async def _download_collection(
    client: httpx.AsyncClient,
    base_url: str,
    namespace: str,
    name: str,
    output_dir: Path,
    *,
    stdout: bool,
    prefetched: httpx.Response | None = None,
) -> None:
    """Download all schemas in a collection to disk or stdout.

    When ``prefetched`` is supplied, reuses the response instead of re-fetching
    the collection download URL.
    """
    if prefetched is not None:
        resp = prefetched
    else:
        resp = await client.get(_collection_url(base_url, namespace, name))
    if resp.status_code == 404:
        _fail(
            _ErrorClass.NOT_FOUND,
            f"No collection named '{namespace}/{name}' found on {_host_from(base_url)}.",
        )
    resp.raise_for_status()

    data = resp.json()
    meta = data["collection"]
    schemas = data["schemas"]
    skipped = meta.get("skipped", [])
    status = _status_console(stdout)

    if stdout:
        for index, schema in enumerate(schemas):
            content = schema["content"]
            if index > 0 and not content.lstrip().startswith("---"):
                sys.stdout.write("---\n")
            sys.stdout.write(content)
            if not content.endswith("\n"):
                sys.stdout.write("\n")
            err_console.print(f"[green]Fetched {schema['namespace']}/{schema['name']} v{schema['semver']}")
    else:
        collection_dir = output_dir / name
        _mkdir_or_fail(collection_dir)
        for schema in schemas:
            filename = f"{schema['name']}.yml"
            file_path = collection_dir / filename
            file_path.write_text(schema["content"], encoding="utf-8")
            console.print(
                f"[green]Downloaded {schema['namespace']}/{schema['name']} v{schema['semver']} -> {file_path}"
            )

    for item in skipped:
        status.print(f"[yellow]Skipped {item['namespace']}/{item['name']}: {item['reason']}")

    status.print(
        f"\n[green]Collection {namespace}/{name}: {meta['downloaded_count']}/{meta['schema_count']} schemas downloaded"
    )


@app.command()
@catch_exception(console=console)
async def get(
    identifier: str = typer.Argument(help="Schema or collection identifier in namespace/name format"),
    version: str | None = typer.Option(
        None, "--version", "-v", help="Specific schema version, for example 1.2.0. Default: latest published."
    ),
    collection: bool | None = typer.Option(
        None,
        "--collection",
        "-c",
        help="Force collection download. Default: auto-detect whether the identifier is a schema or collection.",
    ),
    stdout: bool = typer.Option(
        False,
        "--stdout",
        "-s",
        help="Print content to stdout instead of writing to disk. Status messages go to stderr.",
    ),
    output_dir: Path = typer.Option(Path("schemas"), "--output-dir", "-o", help="Directory to save downloaded files."),
    marketplace_url: str | None = typer.Option(
        None,
        "--marketplace-url",
        help="Base URL of the Infrahub Marketplace. Overrides configuration and environment.",
    ),
    _: str = CONFIG_PARAM,
) -> None:
    """Fetch a schema or collection from the Infrahub Marketplace.

    By default, auto-detects whether `namespace/name` is a schema or a collection.
    Pass --collection to force the collection path when an identifier exists as both.
    """
    namespace, name = _parse_identifier(identifier)

    sdk_cfg = _SdkConfig()
    resolved_url = (marketplace_url or SETTINGS.active.marketplace_url).rstrip("/")

    async with _make_http_client(sdk_cfg) as client:
        prefetched: httpx.Response | None = None
        schema_confirmed_exists = False
        if collection is None:
            item_type, prefetched = await _detect_item_type(client, resolved_url, namespace, name, stdout=stdout)
            schema_confirmed_exists = item_type == "schema"
        elif collection:
            item_type = "collection"
        else:
            # Typer exposes only --collection, not --no-collection, so collection=False
            # is unreachable from the CLI. Kept for defensive completeness against the
            # bool | None type.
            item_type = "schema"

        try:
            if item_type == "collection":
                if version:
                    _status_console(stdout).print(
                        "[yellow]Warning: --version is ignored when downloading a collection."
                    )
                await _download_collection(
                    client, resolved_url, namespace, name, output_dir, stdout=stdout, prefetched=prefetched
                )
            else:
                await _download_schema(
                    client,
                    resolved_url,
                    namespace,
                    name,
                    version,
                    output_dir,
                    stdout=stdout,
                    prefetched=prefetched,
                    schema_confirmed_exists=schema_confirmed_exists,
                )
        except httpx.HTTPError as exc:
            _fail(_ErrorClass.NETWORK, f"Marketplace request failed: {exc}")
