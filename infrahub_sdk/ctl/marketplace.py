from __future__ import annotations

import asyncio
from contextlib import suppress
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import httpx
import typer
from rich.console import Console

from ..async_typer import AsyncTyper
from ..ctl import config
from ..ctl.parameters import CONFIG_PARAM
from ..ctl.utils import catch_exception

app = AsyncTyper()
console = Console()

MarketplaceItemType = Literal["schema", "collection"]
ErrorClass = Literal["invalid-input", "not-found", "network"]

_ERROR_EXIT_CODES: dict[ErrorClass, int] = {
    "invalid-input": 1,
    "not-found": 1,
    "network": 2,
}


def _fail(error_class: ErrorClass, message: str) -> typer.Exit:
    """Print an error line and return a typer.Exit with the mapped code. Intended to be raised by the caller."""
    console.print(f"[red]{message}")
    return typer.Exit(_ERROR_EXIT_CODES[error_class])


@app.callback()
def callback() -> None:
    """Browse and download schemas from the Infrahub Marketplace."""


def _parse_identifier(identifier: str) -> tuple[str, str]:
    """Validate and split a 'namespace/name' identifier."""
    parts = identifier.split("/")
    if len(parts) != 2 or not all(parts):
        raise _fail("invalid-input", f"Invalid identifier '{identifier}'. Expected format: namespace/name")
    return parts[0], parts[1]


def _host_from(base_url: str) -> str:
    return urlparse(base_url).netloc or base_url


def _mkdir_or_fail(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise _fail("invalid-input", f"Cannot write to '{path}': {exc}") from exc


async def _detect_item_type(
    client: httpx.AsyncClient,
    base_url: str,
    namespace: str,
    name: str,
) -> tuple[MarketplaceItemType, httpx.Response]:
    """Probe schema and collection endpoints in parallel. Schema wins on 200-200.

    Returns the resolved type and the winning 200 response so the caller can reuse
    it instead of re-fetching the same URL.
    """
    schema_url = f"{base_url}/api/v1/schemas/{namespace}/{name}/download"
    collection_url = f"{base_url}/api/v1/collections/{namespace}/{name}/download"

    schema_resp, collection_resp = await asyncio.gather(
        client.get(schema_url),
        client.get(collection_url),
        return_exceptions=True,
    )

    schema_ok = isinstance(schema_resp, httpx.Response) and schema_resp.status_code == 200
    collection_ok = isinstance(collection_resp, httpx.Response) and collection_resp.status_code == 200

    if schema_ok:
        if collection_ok:
            console.print(
                f"[yellow]Note: '{namespace}/{name}' exists as both a schema and a collection. "
                "Resolving as schema. Pass --collection to force the collection path."
            )
        return "schema", schema_resp  # type: ignore[return-value]
    if collection_ok:
        return "collection", collection_resp  # type: ignore[return-value]

    def is_transport_failure(r: object) -> bool:
        if isinstance(r, Exception):
            return True
        return isinstance(r, httpx.Response) and r.status_code >= 500

    if is_transport_failure(schema_resp) and is_transport_failure(collection_resp):
        raise _fail(
            "network",
            f"Could not reach marketplace at {base_url}. Check your connection or --marketplace-url.",
        )

    raise _fail(
        "not-found",
        f"No schema or collection named '{namespace}/{name}' found on {_host_from(base_url)}.",
    )


async def _download_schema(
    client: httpx.AsyncClient,
    base_url: str,
    namespace: str,
    name: str,
    version: str | None,
    output_dir: Path,
    prefetched: httpx.Response | None = None,
) -> None:
    """Download a single schema and write it to disk.

    When ``prefetched`` is supplied and ``version`` is None, reuses the response
    instead of re-fetching the unversioned download URL.
    """
    if prefetched is not None and version is None:
        resp = prefetched
    else:
        if version:
            url = f"{base_url}/api/v1/schemas/{namespace}/{name}/versions/{version}/download"
        else:
            url = f"{base_url}/api/v1/schemas/{namespace}/{name}/download"
        resp = await client.get(url)

    if resp.status_code == 404:
        if version is not None and prefetched is not None:
            raise _fail(
                "not-found",
                f"Schema '{namespace}/{name}' has no published version '{version}'. "
                "Run without --version for the latest.",
            )
        detail = "not found"
        with suppress(Exception):
            detail = resp.json().get("detail", detail)
        raise _fail("not-found", f"Error: {detail}")
    resp.raise_for_status()

    resolved_version = version or resp.headers.get("x-schema-version", "latest")
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
    prefetched: httpx.Response | None = None,
) -> None:
    """Download all schemas in a collection to disk.

    When ``prefetched`` is supplied, reuses the response instead of re-fetching
    the collection download URL.
    """
    if prefetched is not None:
        resp = prefetched
    else:
        url = f"{base_url}/api/v1/collections/{namespace}/{name}/download"
        resp = await client.get(url)
    if resp.status_code == 404:
        detail = "not found"
        with suppress(Exception):
            detail = resp.json().get("detail", detail)
        raise _fail("not-found", f"Error: {detail}")
    resp.raise_for_status()

    data = resp.json()
    meta = data["collection"]
    schemas = data["schemas"]
    skipped = meta.get("skipped", [])

    collection_dir = output_dir / name
    _mkdir_or_fail(collection_dir)

    for schema in schemas:
        filename = f"{schema['name']}.yml"
        file_path = collection_dir / filename
        file_path.write_text(schema["content"], encoding="utf-8")
        console.print(f"[green]Downloaded {schema['namespace']}/{schema['name']} v{schema['semver']} -> {file_path}")

    for item in skipped:
        console.print(f"[yellow]Skipped {item['namespace']}/{item['name']}: {item['reason']}")

    console.print(
        f"\n[green]Collection {namespace}/{name}: {meta['downloaded_count']}/{meta['schema_count']} schemas downloaded"
    )


@app.command()
@catch_exception(console=console)
async def download(
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
    output_dir: Path = typer.Option(Path("schemas"), "--output-dir", "-o", help="Directory to save downloaded files."),
    marketplace_url: str | None = typer.Option(
        None,
        "--marketplace-url",
        help="Base URL of the Infrahub Marketplace. Overrides configuration and environment.",
    ),
    _: str = CONFIG_PARAM,
) -> None:
    """Download a schema or collection from the Infrahub Marketplace.

    By default, auto-detects whether `namespace/name` is a schema or a collection.
    Pass --collection to force the collection path when an identifier exists as both.
    """
    namespace, name = _parse_identifier(identifier)

    resolved_url = marketplace_url or config.SETTINGS.active.marketplace_url
    base_url = resolved_url.rstrip("/")

    async with httpx.AsyncClient(follow_redirects=True) as client:
        prefetched: httpx.Response | None = None
        if collection is None:
            item_type, prefetched = await _detect_item_type(client, base_url, namespace, name)
        elif collection:
            item_type = "collection"
        else:
            item_type = "schema"

        if item_type == "collection":
            if version:
                console.print("[yellow]Warning: --version is ignored when downloading a collection.")
            await _download_collection(client, base_url, namespace, name, output_dir, prefetched=prefetched)
        else:
            await _download_schema(client, base_url, namespace, name, version, output_dir, prefetched=prefetched)
