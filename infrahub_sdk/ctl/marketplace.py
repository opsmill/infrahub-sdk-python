from __future__ import annotations

import asyncio
import sys
from collections import Counter, deque
from enum import Enum
from pathlib import Path
from typing import Any, Literal, NamedTuple, NoReturn
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


def _schema_detail_url(base_url: str, namespace: str, name: str) -> str:
    return f"{base_url}/api/v1/schemas/{namespace}/{name}"


def _is_transport_failure(r: object) -> bool:
    if isinstance(r, Exception):
        return True
    return isinstance(r, httpx.Response) and r.status_code >= 500


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
    filename = f"{name}.yml"

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


async def _read_schema_dependencies(
    client: httpx.AsyncClient,
    base_url: str,
    namespace: str,
    name: str,
    *,
    status: Console,
) -> tuple[list[tuple[str, str]], list[str]]:
    """Read a schema's latest-version dependencies from the marketplace API.

    Returns ``(resolved, unresolved_kinds)`` where ``resolved`` is a list of
    ``(namespace, name)`` for dependencies the marketplace can supply, and ``unresolved_kinds``
    are referenced kinds that are not available (including ones hidden by visibility). A read
    failure is reported as an informational note and treated as "no dependencies" so the rest
    of the resolution continues.
    """
    try:
        resp = await client.get(_schema_detail_url(base_url, namespace, name))
        resp.raise_for_status()
        payload = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        detail = str(exc) or type(exc).__name__
        status.print(f"[yellow]Note: could not read dependencies for {namespace}/{name}: {detail}")
        return [], []

    versions = payload.get("versions") or [] if isinstance(payload, dict) else []
    latest_id = (payload.get("latest_version") or {}).get("id") if isinstance(payload, dict) else None
    deps_source: dict[str, Any] | None = None
    if latest_id:
        deps_source = next((v for v in versions if isinstance(v, dict) and v.get("id") == latest_id), None)
    if deps_source is None and versions and isinstance(versions[0], dict):
        deps_source = versions[0]

    resolved: list[tuple[str, str]] = []
    unresolved: list[str] = []
    for dep in (deps_source or {}).get("dependencies") or []:
        if not isinstance(dep, dict):
            continue
        resolved_schema = dep.get("resolved_schema")
        if dep.get("is_resolved") and isinstance(resolved_schema, dict):
            dep_namespace = resolved_schema.get("namespace")
            dep_name = resolved_schema.get("name")
            if dep_namespace and dep_name:
                resolved.append((dep_namespace, dep_name))
                continue
        referenced_kind = dep.get("referenced_kind")
        if referenced_kind:
            unresolved.append(referenced_kind)
    return resolved, unresolved


async def _resolve_dependency_closure(
    client: httpx.AsyncClient,
    base_url: str,
    members: list[dict[str, Any]],
    *,
    status: Console,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Walk schema dependencies transitively, starting from the collection's members.

    Returns ``(schemas, unresolved_kinds)`` where ``schemas`` is the full ordered download set
    (members first, then discovered dependencies, each downloaded at its latest version) and
    ``unresolved_kinds`` is the sorted set of referenced kinds not available in the
    marketplace. A ``seen`` set of ``(namespace, name)`` makes the walk cycle-safe and ensures
    each schema appears once even when reachable through multiple paths.
    """
    seen: set[tuple[str, str]] = set()
    ordered: list[dict[str, Any]] = []
    unresolved: set[str] = set()
    queue: deque[dict[str, Any]] = deque()

    for member in members:
        key = (member["namespace"], member["name"])
        if key in seen:
            continue
        seen.add(key)
        ordered.append(member)
        queue.append(member)

    while queue:
        current = queue.popleft()
        resolved, kinds = await _read_schema_dependencies(
            client, base_url, current["namespace"], current["name"], status=status
        )
        unresolved.update(kinds)
        for dep_namespace, dep_name in resolved:
            key = (dep_namespace, dep_name)
            if key in seen:
                continue
            seen.add(key)
            entry = {"namespace": dep_namespace, "name": dep_name, "version": None}
            ordered.append(entry)
            queue.append(entry)

    return ordered, sorted(unresolved)


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
        member_dir = target_dir / schema["namespace"] if name_counts[member_name] > 1 else target_dir
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


def _collection_dependency_targets(
    payload: Any,
) -> tuple[list[tuple[str, str]], list[dict[str, Any]], list[str]]:
    """Extract a collection's declared dependencies from its detail payload.

    Returns ``(prerequisite_collections, standalone_schemas, unresolved_kinds)``: prerequisite
    collections as ``(namespace, name)`` tuples, standalone schemas as member-shaped dependency
    dicts, and unresolved kinds the marketplace could not resolve to a schema.
    """
    dep = (payload.get("dependencies") or {}) if isinstance(payload, dict) else {}
    collections: list[tuple[str, str]] = [
        (str(entry["namespace"]), str(entry["name"]))
        for entry in dep.get("collections") or []
        if isinstance(entry, dict) and entry.get("namespace") and entry.get("name")
    ]
    schemas: list[dict[str, Any]] = [
        {"namespace": str(entry["namespace"]), "name": str(entry["name"]), "version": None}
        for entry in dep.get("schemas") or []
        if isinstance(entry, dict) and entry.get("namespace") and entry.get("name")
    ]
    unresolved: list[str] = [str(kind) for kind in dep.get("unresolved_kinds") or [] if kind]
    return collections, schemas, unresolved


async def _fetch_collection_payload(
    client: httpx.AsyncClient,
    base_url: str,
    namespace: str,
    name: str,
    *,
    status: Console,
) -> Any | None:
    """Fetch a prerequisite collection's detail, returning None (with a note) on any failure.

    Prerequisite collections are dependencies, so an unreachable one is reported and skipped
    rather than aborting the whole download.
    """
    try:
        resp = await client.get(_collection_url(base_url, namespace, name))
        if resp.status_code == 404:
            status.print(f"[yellow]Note: prerequisite collection {namespace}/{name} not found; skipping.")
            return None
        resp.raise_for_status()
        return resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        detail = str(exc) or type(exc).__name__
        status.print(f"[yellow]Note: could not fetch prerequisite collection {namespace}/{name}: {detail}")
        return None


_CollectionTargets = tuple[list[tuple[str, str]], list[dict[str, Any]], list[str]]
_CollectionRecord = tuple[str, str, list[dict[str, Any]], _CollectionTargets]


async def _walk_collection_graph(
    client: httpx.AsyncClient,
    base_url: str,
    namespace: str,
    name: str,
    payload: Any,
    *,
    status: Console,
) -> list[_CollectionRecord]:
    """Walk the collection dependency graph cycle-safe, one record per collection.

    Each record is ``(namespace, name, members, dependency_targets)``. Prerequisite collections
    from ``dependencies.collections`` are visited transitively; ``seen`` prevents revisiting a
    collection in a cycle.
    """
    seen: set[tuple[str, str]] = {(namespace, name)}
    records: list[_CollectionRecord] = []
    queue: deque[tuple[str, str, Any]] = deque([(namespace, name, payload)])
    while queue:
        current_namespace, current_name, current_payload = queue.popleft()
        if current_payload is None:
            current_payload = await _fetch_collection_payload(
                client, base_url, current_namespace, current_name, status=status
            )
            if current_payload is None:
                continue
        members = _collection_members(current_payload, status)
        targets = _collection_dependency_targets(current_payload)
        records.append((current_namespace, current_name, members, targets))
        for dep_namespace, dep_name in targets[0]:
            if (dep_namespace, dep_name) not in seen:
                seen.add((dep_namespace, dep_name))
                queue.append((dep_namespace, dep_name, None))
    return records


def _report_collection_tree(
    status: Console,
    namespace: str,
    name: str,
    total_written: int,
    requested_member_count: int,
    prerequisites: list[str],
    unresolved: set[str],
) -> None:
    dependency_count = total_written - requested_member_count
    noun = "dependency" if dependency_count == 1 else "dependencies"
    status.print(
        f"\n[green]Collection {namespace}/{name}: {total_written} schemas downloaded "
        f"({dependency_count} {noun} resolved)"
    )
    if prerequisites:
        status.print("[green]Prerequisite collections: " + ", ".join(prerequisites))
    if unresolved:
        status.print(
            "[yellow]Unresolved dependencies (referenced kinds the marketplace could not resolve to a schema): "
            + ", ".join(sorted(unresolved))
        )


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
    - each transitive prerequisite collection -> ``output_dir/<collection name>/``
    - standalone dependency schemas (not part of any prerequisite collection) -> ``output_dir/``

    ``seen_schemas`` ensures each schema is written once even when reachable through several
    collections or paths; standalone schemas are resolved transitively via the per-schema walk.
    """
    status = _status_console(stdout)
    records = await _walk_collection_graph(client, base_url, namespace, name, payload, status=status)

    seen_schemas: set[tuple[str, str]] = set()
    unresolved: set[str] = set()
    standalone_seed: list[dict[str, Any]] = []
    prerequisites: list[str] = []
    total_written = 0
    requested_member_count = 0

    for rec_namespace, rec_name, members, targets in records:
        if (rec_namespace, rec_name) == (namespace, name):
            requested_member_count = len(members)
        else:
            prerequisites.append(f"{rec_namespace}/{rec_name}")
        standalone_seed.extend(targets[1])
        unresolved.update(targets[2])
        # Collection members (requested or prerequisite) download strictly: a curated
        # collection that lists a missing member is an error, not something to skip.
        total_written += await _download_schema_set(
            client,
            base_url,
            members,
            output_dir / rec_name,
            stdout=stdout,
            seen=seen_schemas,
            already_written=total_written,
            soft_fail=False,
            write_ctx=write_ctx,
        )

    # Loose schema dependencies (standalone + transitively discovered) soft-fail: a referenced
    # schema that cannot be retrieved is reported and skipped, not fatal (FR-014).
    standalone, standalone_unresolved = await _resolve_dependency_closure(
        client, base_url, standalone_seed, status=status
    )
    unresolved.update(standalone_unresolved)
    total_written += await _download_schema_set(
        client,
        base_url,
        standalone,
        output_dir,
        stdout=stdout,
        seen=seen_schemas,
        already_written=total_written,
        soft_fail=True,
        write_ctx=write_ctx,
    )

    _report_collection_tree(status, namespace, name, total_written, requested_member_count, prerequisites, unresolved)


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
    """Download a single schema together with its transitive dependencies.

    The requested schema downloads strictly (it is the primary target); its transitively
    resolved dependency schemas soft-fail and are written to the output root alongside it,
    deduplicated and cycle-safe. Referenced kinds the marketplace cannot resolve are reported.
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

    # Resolve the transitive closure from the requested schema; it is already downloaded, so
    # ``seen`` skips it and only its dependencies are written (soft-fail, to the output root).
    seen: set[tuple[str, str]] = {(namespace, name)}
    seed = [{"namespace": namespace, "name": name, "version": version}]
    closure, unresolved = await _resolve_dependency_closure(client, base_url, seed, status=status)
    reserved = {name} if requested_written else None
    total_written += await _download_schema_set(
        client,
        base_url,
        closure,
        output_dir,
        stdout=stdout,
        seen=seen,
        already_written=total_written,
        soft_fail=True,
        reserved_names=reserved,
        write_ctx=write_ctx,
    )

    dependency_count = total_written - (1 if requested_written else 0)
    noun = "dependency" if dependency_count == 1 else "dependencies"
    status.print(
        f"\n[green]Schema {namespace}/{name}: {total_written} schemas downloaded ({dependency_count} {noun} resolved)"
    )
    if unresolved:
        status.print(
            "[yellow]Unresolved dependencies (referenced kinds the marketplace could not resolve to a schema): "
            + ", ".join(sorted(unresolved))
        )


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
    downloaded = await _download_schema_set(client, base_url, members, output_dir / name, stdout=stdout)
    status.print(f"\n[green]Collection {namespace}/{name}: {downloaded} schemas downloaded")


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
