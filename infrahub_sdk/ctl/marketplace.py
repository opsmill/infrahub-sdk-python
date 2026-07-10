from __future__ import annotations

import asyncio
import sys
from collections import Counter
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

# Per-request page size used when paginating through a full listing (no user
# --limit). Set explicitly so bulk fetches don't inherit the marketplace's
# UI-tuned default page size, which would mean many more round-trips.
_PAGE_SIZE = 100


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


def _dependencies_url(base_url: str, item_type: MarketplaceItemType, namespace: str, name: str) -> str:
    return f"{base_url}/api/v1/{item_type}s/{namespace}/{name}/dependencies"


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
    loop). Otherwise every page is fetched — ``_PAGE_SIZE`` items at a time — until
    ``has_next_page`` is false. Returns the accumulated items and the reported
    ``total_count``.
    """
    url = _list_url(base_url, item_type)
    single_page = limit is not None
    params: dict[str, Any] = {"limit": limit if single_page else _PAGE_SIZE}
    if search:
        params["search"] = search

    items: list[dict[str, Any]] = []
    total_count = 0
    while True:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        payload = _json_or_fail(resp, url)
        if not isinstance(payload, dict):
            _fail(_ErrorClass.NETWORK, f"Response from {_host_from(url)} is not a valid marketplace listing.")
        items.extend(payload.get("items", []))
        total_count = payload.get("total_count", len(items))
        page_info = payload.get("page_info") or {}
        cursor = page_info.get("end_cursor")
        # Stop when a single page was requested, when the server reports no more
        # pages, or when it claims a next page but gives no cursor to follow
        # (guards against an infinite loop re-requesting the same page).
        if single_page or not page_info.get("has_next_page") or not cursor:
            break
        params = {**params, "cursor": cursor}
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
            _fail_http_error(exc, f"Marketplace request to {_host_from(resolved_url)} failed: {exc}")
    if json_output:
        _print_json(items)
        return
    _render_list_table(items, item_type, total_count)


def _is_transport_failure(r: object) -> bool:
    if isinstance(r, Exception):
        return True
    return isinstance(r, httpx.Response) and r.status_code >= 500


def _safe_segment(segment: str) -> str:
    """Reject a path component (from user input or the marketplace API) that could escape output.

    Namespaces, schema names, and collection names all become directory or file components on
    disk, so a value containing a path separator, ``.``/``..``, an absolute-path root, or a NUL
    is refused rather than allowed to traverse outside the output directory.
    """
    if not segment or segment in {".", ".."} or "/" in segment or "\\" in segment or "\x00" in segment:
        _fail(_ErrorClass.INVALID_INPUT, f"Refusing unsafe path component from marketplace: {segment!r}")
    return segment


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


def _fail_http_error(exc: httpx.HTTPError, not_found_message: str) -> NoReturn:
    """Fail with the right exit code for an httpx error: 4xx → exit 1, 5xx/transport → exit 2."""
    if _classify_http_error(exc) is _ErrorClass.NOT_FOUND:
        _fail(_ErrorClass.NOT_FOUND, not_found_message)
    detail = str(exc) or type(exc).__name__
    _fail(_ErrorClass.NETWORK, f"Marketplace request failed: {detail}")


def _json_or_fail(resp: httpx.Response, source_url: str) -> Any:
    """Parse a JSON response body, failing with a network-class error on invalid JSON.

    A 200 with a malformed body is a broken response, not user error, so it is
    reported cleanly (exit 2) rather than leaking a raw ``JSONDecodeError`` and
    traceback — which would also corrupt ``--json`` output.
    """
    try:
        return resp.json()
    except ValueError:
        _fail(_ErrorClass.NETWORK, f"Response from {_host_from(source_url)} is not valid JSON.")


def _mkdir_or_fail(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _fail(_ErrorClass.INVALID_INPUT, f"Cannot write to '{path}': {exc}")


class _WriteContext(NamedTuple):
    """Controls overwriting when a schema already exists in the output tree.

    ``preexisting`` maps a schema filename (``<name>.yml``) to the path where it was found in
    the output directory *before* this command ran, so a schema being written now that already
    exists elsewhere (e.g. a dependency at the root vs. a copy under a collection directory) is
    reconciled to a single file instead of duplicated. Only files present before the run are
    considered, so schemas written during this same run never trigger a prompt.
    """

    assume_yes: bool
    preexisting: dict[str, Path]


def _snapshot_existing_schemas(output_root: Path) -> dict[str, Path]:
    """Map ``<name>.yml`` -> existing path for every schema already under ``output_root``."""
    existing: dict[str, Path] = {}
    if output_root.exists():
        for path in sorted(output_root.rglob("*.yml")):
            if path.is_file():
                existing.setdefault(path.name, path)
    return existing


def _print_unresolved(status: Console, unresolved: set[str] | list[str]) -> None:
    """Report referenced kinds the marketplace could not resolve to a schema, if any."""
    if unresolved:
        status.print(
            "[yellow]Unresolved dependencies (referenced kinds the marketplace could not resolve to a schema): "
            + ", ".join(sorted(unresolved))
        )


def _confirm_overwrite(prompt: str, *, assume_yes: bool) -> bool:
    """Return whether to overwrite an existing schema file.

    ``--yes`` overwrites unconditionally; an interactive terminal is prompted; a
    non-interactive run without ``--yes`` declines (keep the existing file) so scripts and CI
    never block or clobber.
    """
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        return False
    return typer.confirm(prompt, default=False)


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


async def _probe_item_type(
    client: httpx.AsyncClient,
    base_url: str,
    namespace: str,
    name: str,
    *,
    schema_url: str,
    collection_url: str,
    collision_console: Console,
) -> tuple[MarketplaceItemType, httpx.Response]:
    """Probe the given schema and collection URLs in parallel. Schema wins on 200-200.

    Returns the resolved type and the winning 200 response so the caller can reuse
    it instead of re-fetching the same URL. On a 200-200 collision the note is
    printed to ``collision_console`` (stderr, so it never pollutes stdout/--json).
    Fails with a network error on transport failure and not-found when neither
    endpoint returns 200.
    """
    schema_resp, collection_resp = await asyncio.gather(
        client.get(schema_url),
        client.get(collection_url),
        return_exceptions=True,
    )

    if isinstance(schema_resp, httpx.Response) and schema_resp.status_code == 200:
        if isinstance(collection_resp, httpx.Response) and collection_resp.status_code == 200:
            collision_console.print(
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


async def _detect_item_type(
    client: httpx.AsyncClient,
    base_url: str,
    namespace: str,
    name: str,
    *,
    stdout: bool,
) -> tuple[MarketplaceItemType, httpx.Response]:
    """Auto-detect whether ``namespace/name`` is a schema or collection via the download endpoints.

    Returns the resolved type and the winning 200 response so the caller can reuse
    it instead of re-fetching the same URL.
    """
    return await _probe_item_type(
        client,
        base_url,
        namespace,
        name,
        schema_url=_schema_url(base_url, namespace, name),
        collection_url=_collection_url(base_url, namespace, name),
        collision_console=_status_console(stdout),
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
    soft_fail: bool = False,
    write_ctx: _WriteContext | None = None,
) -> bool:
    """Download a single schema and write it to disk or stdout.

    Returns ``True`` when the schema was written/streamed and ``False`` when it was skipped
    (only possible with ``soft_fail``).

    When ``prefetched`` is supplied and ``version`` is None, reuses the response
    instead of re-fetching the unversioned download URL.
    ``schema_confirmed_exists`` signals that the schema is known to exist (e.g. from
    the auto-detect probe), so a 404 on a versioned URL is reported as version-not-found
    rather than the generic not-found message.
    ``needs_separator`` inserts a ``---`` document separator before the content in
    stdout mode when it is missing, so multiple schemas streamed back-to-back (e.g.
    from a collection) form a valid multi-document YAML stream.
    ``soft_fail`` downgrades a 404 to an informational note and a ``False`` return instead of
    aborting — used for resolved dependencies so one missing dependency does not fail the
    whole download. ``write_ctx`` reconciles against schemas already present on disk: an
    already-present schema is overwritten (``--yes``/prompt) or kept, decided before fetching
    so a kept schema costs no download.
    """
    filename = f"{_safe_segment(name)}.yml"

    # Reconcile with a pre-existing copy before fetching (disk mode only).
    existing_path = write_ctx.preexisting.get(filename) if write_ctx is not None and not stdout else None
    if existing_path is not None and not _confirm_overwrite(
        f"{namespace}/{name} already exists at {existing_path}. Overwrite?",
        assume_yes=write_ctx.assume_yes if write_ctx else False,
    ):
        _status_console(stdout).print(
            f"[yellow]Kept existing {existing_path}; skipped {namespace}/{name} (pass --yes to overwrite)."
        )
        return False

    if prefetched is not None and version is None:
        resp = prefetched
    else:
        resp = await client.get(_schema_url(base_url, namespace, name, version=version))

    if resp.status_code == 404:
        if soft_fail:
            _status_console(stdout).print(
                f"[yellow]Note: dependency {namespace}/{name} could not be downloaded (not found); skipping."
            )
            return False
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
        return True

    if existing_path is not None:
        existing_path.write_text(resp.text, encoding="utf-8")
        console.print(f"[green]Updated schema {namespace}/{name} v{resolved_version} -> {existing_path}")
        return True

    _mkdir_or_fail(output_dir)
    file_path = output_dir / filename
    file_path.write_text(resp.text, encoding="utf-8")

    console.print(f"[green]Downloaded schema {namespace}/{name} v{resolved_version} -> {file_path}")
    return True


def _collection_members(payload: Any, status: Console) -> list[dict[str, Any]]:
    """Extract downloadable members from a collection metadata payload.

    Returns a list of ``{"namespace", "name", "version"}`` dicts. Members missing a namespace
    or name are skipped with a warning rather than aborting the download.
    """
    items = payload.get("items", []) if isinstance(payload, dict) else []
    schemas = [item.get("schema") for item in items if isinstance(item, dict)]
    members: list[dict[str, Any]] = []
    for schema in schemas:
        if not isinstance(schema, dict):
            continue
        member_namespace = schema.get("namespace")
        member_name = schema.get("name")
        if not member_namespace or not member_name:
            status.print("[yellow]Warning: skipping a collection member with missing namespace or name.")
            continue
        version = (schema.get("latest_version") or {}).get("semver")
        members.append({"namespace": member_namespace, "name": member_name, "version": version})
    return members


class _ResolvedDependencies(NamedTuple):
    """A schema's or collection's fully resolved dependency closure, grouped by source.

    ``collection_groups`` are prerequisite collections as ``(namespace, name, member_schemas)``;
    each group's schemas land under ``output_dir/<name>/``. ``standalone`` are dependency schemas
    that belong to no collection and land in the output root. ``unresolved`` are referenced kinds
    the marketplace could not resolve to a schema; ``hidden_count`` counts dependencies omitted
    because they are not visible to the caller.
    """

    collection_groups: list[tuple[str, str, list[dict[str, Any]]]]
    standalone: list[dict[str, Any]]
    unresolved: list[str]
    hidden_count: int


def _dependency_schemas(entries: Any) -> list[dict[str, Any]]:
    """Build member-shaped ``{namespace, name, version}`` dicts from dependency schema entries."""
    return [
        {"namespace": str(entry["namespace"]), "name": str(entry["name"]), "version": None}
        for entry in entries or []
        if isinstance(entry, dict) and entry.get("namespace") and entry.get("name")
    ]


def _parse_dependencies(payload: Any) -> _ResolvedDependencies:
    """Parse the marketplace ``/dependencies`` response into a grouped download plan."""
    data = payload if isinstance(payload, dict) else {}
    groups: list[tuple[str, str, list[dict[str, Any]]]] = []
    for collection in data.get("collections") or []:
        if not isinstance(collection, dict) or not collection.get("name"):
            continue
        groups.append(
            (
                str(collection.get("namespace") or ""),
                str(collection["name"]),
                _dependency_schemas(collection.get("schemas")),
            )
        )
    hidden = data.get("hidden_count") or 0
    return _ResolvedDependencies(
        collection_groups=groups,
        standalone=_dependency_schemas(data.get("schemas")),
        unresolved=[str(kind) for kind in data.get("unresolved_kinds") or [] if kind],
        hidden_count=hidden if isinstance(hidden, int) else 0,
    )


async def _fetch_dependencies(
    client: httpx.AsyncClient,
    base_url: str,
    item_type: MarketplaceItemType,
    namespace: str,
    name: str,
    *,
    version: str | None = None,
    status: Console,
) -> _ResolvedDependencies | None:
    """Fetch a schema's or collection's resolved dependency closure from the marketplace.

    The marketplace resolves the full transitive closure server-side (``GET .../dependencies``)
    and returns it grouped by source: prerequisite collections with their members, plus
    standalone schemas. When ``version`` is given (schemas only), dependencies are resolved for
    that version. A read failure is reported as an informational note and treated as "no
    dependencies" so the requested item still downloads.
    """
    url = _dependencies_url(base_url, item_type, namespace, name)
    params = {"version": version} if version else None
    try:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        payload = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        detail = str(exc) or type(exc).__name__
        status.print(f"[yellow]Note: could not resolve dependencies for {namespace}/{name}: {detail}")
        return None
    return _parse_dependencies(payload)


async def _download_schema_set(
    client: httpx.AsyncClient,
    base_url: str,
    schemas: list[dict[str, Any]],
    target_dir: Path,
    *,
    stdout: bool,
    seen: set[tuple[str, str]] | None = None,
    already_written: int = 0,
    soft_fail: bool = False,
    reserved_names: set[str] | None = None,
    write_ctx: _WriteContext | None = None,
) -> int:
    """Download a resolved set of schemas into ``target_dir``, returning the count written.

    Schemas sharing a name across namespaces are disambiguated into per-namespace
    subdirectories so they do not overwrite each other. ``soft_fail`` downgrades a missing
    schema to a note instead of aborting — used for loose schema dependencies so one missing
    dependency does not fail the whole download (collection members download strictly).
    ``seen`` deduplicates ``(namespace, name)`` across multiple calls so a schema already
    downloaded (e.g. as a member of another collection) is skipped. ``already_written`` is the
    running total written by prior calls, used so the ``---`` stdout separator is inserted
    before every document except the very first across the whole download. ``reserved_names``
    are names already written into ``target_dir`` by a prior call (e.g. the requested schema),
    so a pending schema sharing one is disambiguated into a namespace subdirectory rather than
    overwriting it.
    """
    if seen is None:
        seen = set()
    pending = []
    for schema in schemas:
        key = (schema["namespace"], schema["name"])
        if key in seen:
            continue
        seen.add(key)
        pending.append(schema)

    name_counts = Counter(schema["name"] for schema in pending)
    for reserved in reserved_names or ():
        name_counts[reserved] += 1

    written_here = 0
    for schema in pending:
        member_name = schema["name"]
        member_dir = target_dir / _safe_segment(schema["namespace"]) if name_counts[member_name] > 1 else target_dir
        written = await _download_schema(
            client=client,
            base_url=base_url,
            namespace=schema["namespace"],
            name=member_name,
            version=schema.get("version"),
            output_dir=member_dir,
            stdout=stdout,
            schema_confirmed_exists=True,
            needs_separator=already_written + written_here > 0,
            soft_fail=soft_fail,
            write_ctx=write_ctx,
        )
        if written:
            written_here += 1
    return written_here


def _print_hidden(status: Console, hidden_count: int) -> None:
    """Report dependencies the marketplace omitted because they are not visible to the caller."""
    if hidden_count:
        noun = "dependency" if hidden_count == 1 else "dependencies"
        status.print(f"[yellow]{hidden_count} {noun} hidden due to visibility and not downloaded.")


def _report_collection_tree(
    status: Console,
    namespace: str,
    name: str,
    total_written: int,
    requested_member_count: int,
    prerequisites: list[str],
    unresolved: set[str],
    hidden_count: int,
) -> None:
    dependency_count = total_written - requested_member_count
    noun = "dependency" if dependency_count == 1 else "dependencies"
    status.print(
        f"\n[green]Collection {namespace}/{name}: {total_written} schemas downloaded "
        f"({dependency_count} {noun} resolved)"
    )
    if prerequisites:
        status.print("[green]Prerequisite collections: " + ", ".join(prerequisites))
    _print_unresolved(status, unresolved)
    _print_hidden(status, hidden_count)


async def _download_collection_tree(
    client: httpx.AsyncClient,
    base_url: str,
    namespace: str,
    name: str,
    payload: Any,
    output_dir: Path,
    *,
    stdout: bool,
    write_ctx: _WriteContext | None = None,
) -> None:
    """Download a collection together with its dependencies, grouped by source collection.

    Layout:

    - requested collection members -> ``output_dir/<requested name>/``
    - each prerequisite collection -> ``output_dir/<collection name>/``
    - standalone dependency schemas (not part of any prerequisite collection) -> ``output_dir/``

    The marketplace resolves the full transitive closure (``GET .../dependencies``); ``seen``
    ensures each schema is written once even when it appears in several groups.
    """
    status = _status_console(stdout)
    seen: set[tuple[str, str]] = set()

    # Requested collection members download strictly (a curated collection that lists a missing
    # member is an error, not something to skip), into the collection's own directory.
    members = _collection_members(payload, status)
    requested_member_count = len(members)
    total_written = await _download_schema_set(
        client,
        base_url,
        members,
        output_dir / _safe_segment(name),
        stdout=stdout,
        seen=seen,
        soft_fail=False,
        write_ctx=write_ctx,
    )

    prerequisites: list[str] = []
    unresolved: set[str] = set()
    hidden_count = 0
    deps = await _fetch_dependencies(client, base_url, "collection", namespace, name, status=status)
    if deps is not None:
        unresolved.update(deps.unresolved)
        hidden_count = deps.hidden_count
        # Prerequisite collection members also download strictly, each into its own directory.
        for dep_namespace, dep_name, dep_members in deps.collection_groups:
            prerequisites.append(f"{dep_namespace}/{dep_name}" if dep_namespace else dep_name)
            total_written += await _download_schema_set(
                client,
                base_url,
                dep_members,
                output_dir / _safe_segment(dep_name),
                stdout=stdout,
                seen=seen,
                already_written=total_written,
                soft_fail=False,
                write_ctx=write_ctx,
            )
        # Standalone dependency schemas soft-fail so one missing dependency does not abort.
        total_written += await _download_schema_set(
            client,
            base_url,
            deps.standalone,
            output_dir,
            stdout=stdout,
            seen=seen,
            already_written=total_written,
            soft_fail=True,
            write_ctx=write_ctx,
        )

    _report_collection_tree(
        status, namespace, name, total_written, requested_member_count, prerequisites, unresolved, hidden_count
    )


async def _download_schema_tree(
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
    write_ctx: _WriteContext | None = None,
) -> None:
    """Download a single schema together with its resolved dependencies.

    The requested schema downloads strictly (the primary target) to the output root. Its
    dependencies — resolved server-side (``GET .../dependencies``) — soft-fail and are grouped by
    the collection they belong to (``output_dir/<collection>/``); dependencies in no collection
    go to the output root. When ``version`` is set, dependencies are resolved for that version.
    """
    status = _status_console(stdout)
    requested_written = await _download_schema(
        client=client,
        base_url=base_url,
        namespace=namespace,
        name=name,
        version=version,
        output_dir=output_dir,
        stdout=stdout,
        prefetched=prefetched,
        schema_confirmed_exists=schema_confirmed_exists,
        write_ctx=write_ctx,
    )
    total_written = 1 if requested_written else 0
    seen: set[tuple[str, str]] = {(namespace, name)}

    unresolved: set[str] = set()
    hidden_count = 0
    deps = await _fetch_dependencies(client, base_url, "schema", namespace, name, version=version, status=status)
    if deps is not None:
        unresolved.update(deps.unresolved)
        hidden_count = deps.hidden_count
        # Dependencies that belong to a collection are grouped under its directory.
        for _dep_namespace, dep_name, dep_members in deps.collection_groups:
            total_written += await _download_schema_set(
                client,
                base_url,
                dep_members,
                output_dir / _safe_segment(dep_name),
                stdout=stdout,
                seen=seen,
                already_written=total_written,
                soft_fail=True,
                write_ctx=write_ctx,
            )
        # Standalone dependencies go to the root; reserve the requested name so a same-named
        # dependency is disambiguated into a namespace subdir rather than overwriting it.
        total_written += await _download_schema_set(
            client,
            base_url,
            deps.standalone,
            output_dir,
            stdout=stdout,
            seen=seen,
            already_written=total_written,
            soft_fail=True,
            reserved_names={name} if requested_written else None,
            write_ctx=write_ctx,
        )

    dependency_count = total_written - (1 if requested_written else 0)
    noun = "dependency" if dependency_count == 1 else "dependencies"
    status.print(
        f"\n[green]Schema {namespace}/{name}: {total_written} schemas downloaded ({dependency_count} {noun} resolved)"
    )
    _print_unresolved(status, unresolved)
    _print_hidden(status, hidden_count)


async def _download_collection(
    client: httpx.AsyncClient,
    base_url: str,
    namespace: str,
    name: str,
    output_dir: Path,
    *,
    stdout: bool,
    prefetched: httpx.Response | None = None,
    with_dependencies: bool = False,
    write_ctx: _WriteContext | None = None,
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

    status = _status_console(stdout)

    if with_dependencies:
        await _download_collection_tree(
            client, base_url, namespace, name, payload, output_dir, stdout=stdout, write_ctx=write_ctx
        )
        return

    members = _collection_members(payload, status)
    downloaded = await _download_schema_set(client, base_url, members, output_dir / _safe_segment(name), stdout=stdout)
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
        return "collection", _json_or_fail(resp, base_url)

    item_type, resp = await _probe_item_type(
        client,
        base_url,
        namespace,
        name,
        schema_url=_detail_url(base_url, "schema", namespace, name),
        collection_url=_detail_url(base_url, "collection", namespace, name),
        collision_console=err_console,
    )
    return item_type, _json_or_fail(resp, base_url)


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
            _fail_http_error(exc, f"Marketplace request for '{parsed.namespace}/{parsed.name}' failed: {exc}")
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
    dependencies: bool = typer.Option(
        False,
        "--dependencies",
        help="Also download the schemas this schema or collection depends on.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Overwrite schemas that already exist in the output directory without prompting.",
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

    # When resolving dependencies to disk, reconcile against schemas already present so a
    # dependency is not duplicated across directories; overwriting is gated by --yes/prompt.
    write_ctx: _WriteContext | None = None
    if dependencies and not stdout:
        write_ctx = _WriteContext(assume_yes=yes, preexisting=_snapshot_existing_schemas(output_dir))

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
                    with_dependencies=dependencies,
                    write_ctx=write_ctx,
                )
            elif dependencies:
                await _download_schema_tree(
                    client=client,
                    base_url=resolved_url,
                    namespace=namespace,
                    name=name,
                    version=version,
                    output_dir=output_dir,
                    stdout=stdout,
                    prefetched=prefetched,
                    schema_confirmed_exists=schema_confirmed_exists,
                    write_ctx=write_ctx,
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
