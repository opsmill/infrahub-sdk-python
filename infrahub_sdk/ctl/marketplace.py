from __future__ import annotations

import asyncio
import sys
from enum import Enum
from pathlib import Path
from typing import Any, Literal, NamedTuple, NoReturn
from urllib.parse import urlparse

import httpx
import typer
from rich.console import Console
from rich.table import Table

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


class MarketplaceIdentifier(NamedTuple):
    namespace: str
    name: str


def _fail(error_class: _ErrorClass, message: str) -> NoReturn:
    err_console.print(f"[red]{message}")
    raise typer.Exit(error_class.exit_code)


def _status_console(stdout: bool) -> Console:
    return err_console if stdout else console


@app.callback()
def callback() -> None:
    """Browse and download schemas from the Infrahub Marketplace."""


def _parse_identifier(identifier: str) -> MarketplaceIdentifier:
    parts = identifier.split("/")
    if len(parts) != 2 or not all(parts):
        _fail(_ErrorClass.INVALID_INPUT, f"Invalid identifier '{identifier}'. Expected format: namespace/name")
    return MarketplaceIdentifier(namespace=parts[0], name=parts[1])


def _host_from(base_url: str) -> str:
    return urlparse(base_url).netloc or base_url


def _schema_url(base_url: str, namespace: str, name: str, version: str | None = None) -> str:
    if version:
        return f"{base_url}/api/v1/schemas/{namespace}/{name}/versions/{version}/download"
    return f"{base_url}/api/v1/schemas/{namespace}/{name}/download"


def _collection_url(base_url: str, namespace: str, name: str) -> str:
    return f"{base_url}/api/v1/collections/{namespace}/{name}"


def _list_url(base_url: str, item_type: MarketplaceItemType) -> str:
    return f"{base_url}/api/v1/{item_type}s"


async def _fetch_listing(
    client: httpx.AsyncClient,
    base_url: str,
    item_type: MarketplaceItemType,
    *,
    search: str | None,
    limit: int | None,
) -> tuple[list[dict[str, Any]], int]:
    """Fetch marketplace listing items, following cursor pagination.

    When ``limit`` is given, a single page of that size is requested (no cursor
    loop). Otherwise every page is fetched until ``has_next_page`` is false.
    Returns the accumulated items and the reported ``total_count``.
    """
    url = _list_url(base_url, item_type)
    params: dict[str, Any] = {}
    if search:
        params["search"] = search
    if limit is not None:
        params["limit"] = limit

    items: list[dict[str, Any]] = []
    total_count = 0
    while True:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        payload = resp.json()
        items.extend(payload.get("items", []))
        total_count = payload.get("total_count", len(items))
        page_info = payload.get("page_info") or {}
        if limit is not None or not page_info.get("has_next_page"):
            break
        params = {**params, "cursor": page_info.get("end_cursor")}
    return items, total_count


def _print_json(data: Any) -> None:
    console.print_json(data=data)


def _render_list_table(items: list[dict[str, Any]], item_type: MarketplaceItemType, total_count: int) -> None:
    table = Table()
    if item_type == "schema":
        table.add_column("Identifier")
        table.add_column("Name")
        table.add_column("Version")
        table.add_column("Downloads", justify="right")
        table.add_column("Tags")
        for item in items:
            latest = item.get("latest_version") or {}
            tags = ", ".join(tag.get("name", "") for tag in item.get("tags") or [])
            table.add_row(
                f"{item.get('namespace', '')}/{item.get('name', '')}",
                item.get("display_name", ""),
                latest.get("semver", ""),
                str(item.get("download_count", 0)),
                tags,
            )
    else:
        table.add_column("Identifier")
        table.add_column("Name")
        table.add_column("Schemas", justify="right")
        table.add_column("Downloads", justify="right")
        for item in items:
            table.add_row(
                f"{item.get('namespace', '')}/{item.get('name', '')}",
                item.get("display_name", ""),
                str(item.get("schema_count", 0)),
                str(item.get("download_count", 0)),
            )
    console.print(table)
    if len(items) < total_count:
        console.print(f"[dim]Showing {len(items)} of {total_count}.")


async def _run_listing(
    *,
    item_type: MarketplaceItemType,
    search: str | None,
    limit: int | None,
    json_output: bool,
    marketplace_url: str | None,
) -> None:
    sdk_cfg = _SdkConfig()
    resolved_url = (marketplace_url or SETTINGS.active.marketplace_url).rstrip("/")
    async with _make_http_client(sdk_cfg) as client:
        try:
            items, total_count = await _fetch_listing(client, resolved_url, item_type, search=search, limit=limit)
        except httpx.HTTPError as exc:
            error_class = _classify_http_error(exc)
            if error_class is _ErrorClass.NOT_FOUND:
                _fail(error_class, f"Marketplace listing not found on {_host_from(resolved_url)}: {exc}")
            detail = str(exc) or type(exc).__name__
            _fail(_ErrorClass.NETWORK, f"Marketplace request failed: {detail}")
    if json_output:
        _print_json(items)
        return
    _render_list_table(items, item_type, total_count)


def _is_transport_failure(r: object) -> bool:
    if isinstance(r, Exception):
        return True
    return isinstance(r, httpx.Response) and r.status_code >= 500


def _classify_http_error(exc: httpx.HTTPError) -> _ErrorClass:
    """Map an httpx error to an error class for consistent exit-code assignment.

    A response with a 4xx status code is a client/not-found error (exit 1).
    A 5xx response or a transport-level failure with no response is a network
    error (exit 2).
    """
    response = getattr(exc, "response", None)
    if response is not None and response.status_code < 500:
        return _ErrorClass.NOT_FOUND
    return _ErrorClass.NETWORK


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
    needs_separator: bool = False,
) -> None:
    """Download a single schema and write it to disk or stdout.

    When ``prefetched`` is supplied and ``version`` is None, reuses the response
    instead of re-fetching the unversioned download URL.
    ``schema_confirmed_exists`` signals that the schema is known to exist (e.g. from
    the auto-detect probe), so a 404 on a versioned URL is reported as version-not-found
    rather than the generic not-found message.
    ``needs_separator`` inserts a ``---`` document separator before the content in
    stdout mode when it is missing, so multiple schemas streamed back-to-back (e.g.
    from a collection) form a valid multi-document YAML stream.
    """
    if prefetched is not None and version is None:
        resp = prefetched
    else:
        resp = await client.get(_schema_url(base_url, namespace, name, version=version))

    if resp.status_code == 404:
        if version and schema_confirmed_exists:
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
        if needs_separator and not resp.text.lstrip().startswith("---"):
            sys.stdout.write("---\n")
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
    """Fetch every schema in a collection, writing to disk or stdout.

    The collection metadata endpoint lists each member schema along with its latest
    published version. Each member is downloaded individually via :func:`_download_schema`
    so naming, versioning, and error handling stay identical to single-schema downloads.
    On disk, members land in ``output_dir/<collection name>/<schema name>.yml``. If two
    members share a name across namespaces, those members are disambiguated into
    ``output_dir/<collection name>/<namespace>/<schema name>.yml`` instead of silently
    overwriting each other.
    When ``prefetched`` is supplied (from the auto-detect probe), reuses that response
    instead of re-fetching the collection metadata.
    """
    if prefetched:
        resp = prefetched
    else:
        resp = await client.get(_collection_url(base_url, namespace, name))
    if resp.status_code == 404:
        _fail(
            _ErrorClass.NOT_FOUND,
            f"No collection named '{namespace}/{name}' found on {_host_from(base_url)}.",
        )
    resp.raise_for_status()

    try:
        payload = resp.json()
    except ValueError:
        _fail(
            _ErrorClass.NETWORK,
            f"Response from {_collection_url(base_url, namespace, name)} is not valid JSON",
        )

    items = payload.get("items", []) if isinstance(payload, dict) else []
    schemas = [item.get("schema") for item in items if isinstance(item, dict)]
    members: list[dict[str, Any]] = [schema for schema in schemas if isinstance(schema, dict)]
    status = _status_console(stdout)
    target_dir = output_dir / name

    member_names = [schema.get("name") for schema in members if schema.get("namespace") and schema.get("name")]
    duplicated_names = {member_name for member_name in member_names if member_names.count(member_name) > 1}

    downloaded = 0
    for schema in members:
        member_namespace = schema.get("namespace")
        member_name = schema.get("name")
        if not member_namespace or not member_name:
            status.print("[yellow]Warning: skipping a collection member with missing namespace or name.")
            continue
        version = (schema.get("latest_version") or {}).get("semver")
        member_dir = target_dir / member_namespace if member_name in duplicated_names else target_dir
        await _download_schema(
            client=client,
            base_url=base_url,
            namespace=member_namespace,
            name=member_name,
            version=version,
            output_dir=member_dir,
            stdout=stdout,
            schema_confirmed_exists=True,
            needs_separator=downloaded > 0,
        )
        downloaded += 1

    status.print(f"\n[green]Collection {namespace}/{name}: {downloaded} schemas downloaded")


def _detail_url(base_url: str, item_type: MarketplaceItemType, namespace: str, name: str) -> str:
    return f"{base_url}/api/v1/{item_type}s/{namespace}/{name}"


async def _fetch_detail(
    client: httpx.AsyncClient,
    base_url: str,
    namespace: str,
    name: str,
    *,
    force_collection: bool,
) -> tuple[MarketplaceItemType, dict[str, Any]]:
    """Fetch full detail for a schema or collection.

    With ``force_collection`` the collection detail endpoint is used directly.
    Otherwise both detail endpoints are probed in parallel; a schema wins a
    200/200 collision (consistent with ``get``'s auto-detection).
    """
    if force_collection:
        resp = await client.get(_detail_url(base_url, "collection", namespace, name))
        if resp.status_code == 404:
            _fail(_ErrorClass.NOT_FOUND, f"No collection named '{namespace}/{name}' found on {_host_from(base_url)}.")
        resp.raise_for_status()
        return "collection", resp.json()

    schema_resp, collection_resp = await asyncio.gather(
        client.get(_detail_url(base_url, "schema", namespace, name)),
        client.get(_detail_url(base_url, "collection", namespace, name)),
        return_exceptions=True,
    )
    if isinstance(schema_resp, httpx.Response) and schema_resp.status_code == 200:
        if isinstance(collection_resp, httpx.Response) and collection_resp.status_code == 200:
            err_console.print(
                f"[yellow]Note: '{namespace}/{name}' exists as both a schema and a collection. "
                "Resolving as schema. Pass --collection to force the collection path."
            )
        return "schema", schema_resp.json()
    if isinstance(collection_resp, httpx.Response) and collection_resp.status_code == 200:
        return "collection", collection_resp.json()

    if _is_transport_failure(schema_resp) or _is_transport_failure(collection_resp):
        _fail(
            _ErrorClass.NETWORK,
            f"Could not reach marketplace at {base_url}. Check your connection or --marketplace-url.",
        )
    _fail(
        _ErrorClass.NOT_FOUND,
        f"No schema or collection named '{namespace}/{name}' found on {_host_from(base_url)}.",
    )


def _render_detail(detail: dict[str, Any], item_type: MarketplaceItemType) -> None:
    namespace = detail.get("namespace", "")
    name = detail.get("name", "")
    console.print(f"[bold]{namespace}/{name}[/] — {detail.get('display_name', '')}")
    if detail.get("description"):
        console.print(detail["description"])
    console.print(f"Downloads: {detail.get('download_count', 0)}")

    if item_type == "schema":
        tags = ", ".join(tag.get("name", "") for tag in detail.get("tags") or [])
        if tags:
            console.print(f"Tags: {tags}")
        versions = detail.get("versions") or []
        if versions:
            table = Table(title="Versions")
            table.add_column("Version")
            table.add_column("Status")
            table.add_column("Released")
            table.add_column("Changelog")
            for version in versions:
                table.add_row(
                    version.get("semver", ""),
                    version.get("status", ""),
                    (version.get("created_at") or "")[:10],
                    version.get("changelog") or "",
                )
            console.print(table)
    else:
        members = detail.get("items") or []
        console.print(f"Schemas: {len(members)}")
        if members:
            table = Table(title="Members")
            table.add_column("Identifier")
            table.add_column("Name")
            for member in members:
                schema = member.get("schema") or {}
                table.add_row(
                    f"{schema.get('namespace', '')}/{schema.get('name', '')}",
                    schema.get("display_name", ""),
                )
            console.print(table)

    deps = (detail.get("dependencies") or {}).get("schemas") or []
    if deps:
        dep_list = ", ".join(f"{dep.get('namespace', '')}/{dep.get('name', '')}" for dep in deps)
        console.print(f"Dependencies: {dep_list}")


@app.command()
@catch_exception(console=console)
async def show(
    identifier: str = typer.Argument(help="Schema or collection identifier in namespace/name format"),
    collection: bool = typer.Option(
        False,
        "--collection",
        "-c",
        is_flag=True,
        help="Force collection lookup. Default: auto-detect whether the identifier is a schema or collection.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON to stdout instead of a table."),
    marketplace_url: str | None = typer.Option(
        None, "--marketplace-url", help="Base URL of the Infrahub Marketplace. Overrides configuration and environment."
    ),
    _: str = CONFIG_PARAM,
) -> None:
    """Show full details of a schema or collection from the Infrahub Marketplace."""
    parsed = _parse_identifier(identifier)
    sdk_cfg = _SdkConfig()
    resolved_url = (marketplace_url or SETTINGS.active.marketplace_url).rstrip("/")
    async with _make_http_client(sdk_cfg) as client:
        try:
            item_type, detail = await _fetch_detail(
                client, resolved_url, parsed.namespace, parsed.name, force_collection=collection
            )
        except httpx.HTTPError as exc:
            error_class = _classify_http_error(exc)
            if error_class is _ErrorClass.NOT_FOUND:
                _fail(error_class, f"Marketplace listing not found on {_host_from(resolved_url)}: {exc}")
            message = str(exc) or type(exc).__name__
            _fail(_ErrorClass.NETWORK, f"Marketplace request failed: {message}")
    if json_output:
        _print_json(detail)
        return
    _render_detail(detail, item_type)


@app.command(name="list")
@catch_exception(console=console)
async def list_items(
    collections: bool = typer.Option(False, "--collections", is_flag=True, help="List collections instead of schemas."),
    limit: int | None = typer.Option(None, "--limit", "-l", help="Maximum number of results to display."),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON to stdout instead of a table."),
    marketplace_url: str | None = typer.Option(
        None, "--marketplace-url", help="Base URL of the Infrahub Marketplace. Overrides configuration and environment."
    ),
    _: str = CONFIG_PARAM,
) -> None:
    """List schemas (default) or collections available on the Infrahub Marketplace."""
    await _run_listing(
        item_type="collection" if collections else "schema",
        search=None,
        limit=limit,
        json_output=json_output,
        marketplace_url=marketplace_url,
    )


@app.command()
@catch_exception(console=console)
async def search(
    term: str = typer.Argument(help="Search term matched against name, display name, and description."),
    collections: bool = typer.Option(
        False, "--collections", is_flag=True, help="Search collections instead of schemas."
    ),
    limit: int | None = typer.Option(None, "--limit", "-l", help="Maximum number of results to display."),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON to stdout instead of a table."),
    marketplace_url: str | None = typer.Option(
        None, "--marketplace-url", help="Base URL of the Infrahub Marketplace. Overrides configuration and environment."
    ),
    _: str = CONFIG_PARAM,
) -> None:
    """Search the Infrahub Marketplace for schemas (default) or collections."""
    await _run_listing(
        item_type="collection" if collections else "schema",
        search=term,
        limit=limit,
        json_output=json_output,
        marketplace_url=marketplace_url,
    )


@app.command()
@catch_exception(console=console)
async def get(
    identifier: str = typer.Argument(help="Schema or collection identifier in namespace/name format"),
    version: str | None = typer.Option(
        None, "--version", "-v", help="Specific schema version, for example 1.2.0. Default: latest published."
    ),
    collection: bool = typer.Option(
        False,
        "--collection",
        "-c",
        is_flag=True,
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
    parsed = _parse_identifier(identifier)
    namespace = parsed.namespace
    name = parsed.name

    sdk_cfg = _SdkConfig()
    resolved_url = (marketplace_url or SETTINGS.active.marketplace_url).rstrip("/")

    async with _make_http_client(sdk_cfg) as client:
        prefetched: httpx.Response | None = None
        schema_confirmed_exists = False
        if collection:
            item_type: MarketplaceItemType = "collection"
        else:
            item_type, prefetched = await _detect_item_type(
                client=client, base_url=resolved_url, namespace=namespace, name=name, stdout=stdout
            )
            schema_confirmed_exists = item_type == "schema"

        try:
            if item_type == "collection":
                if version:
                    _status_console(stdout).print(
                        "[yellow]Warning: --version is ignored when downloading a collection."
                    )
                await _download_collection(
                    client=client,
                    base_url=resolved_url,
                    namespace=namespace,
                    name=name,
                    output_dir=output_dir,
                    stdout=stdout,
                    prefetched=prefetched,
                )
            else:
                await _download_schema(
                    client=client,
                    base_url=resolved_url,
                    namespace=namespace,
                    name=name,
                    version=version,
                    output_dir=output_dir,
                    stdout=stdout,
                    prefetched=prefetched,
                    schema_confirmed_exists=schema_confirmed_exists,
                )
        except httpx.HTTPError as exc:
            detail = str(exc) or type(exc).__name__
            _fail(_ErrorClass.NETWORK, f"Marketplace request failed: {detail}")
