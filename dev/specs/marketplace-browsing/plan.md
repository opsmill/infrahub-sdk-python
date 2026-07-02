# Marketplace Browsing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `list`, `search`, and `show` discovery commands to `infrahubctl marketplace` so users can browse the marketplace without knowing an exact identifier.

**Architecture:** All code lives in `infrahub_sdk/ctl/marketplace.py`, added to the existing `AsyncTyper` `app` (already registered in `cli_commands.py`, so no registration change). New commands reuse the module's existing helpers (`_make_http_client`, `_parse_identifier`, `_host_from`, `_is_transport_failure`, `_fail`, `_ErrorClass`, `SETTINGS`, `CONFIG_PARAM`). Responses are handled as raw dicts (no models), rendered with Rich tables, or emitted as JSON via `console.print_json`.

**Tech Stack:** Python 3.10-3.13, Typer/AsyncTyper, httpx (async), Rich, pytest + pytest-httpx.

## Global Constraints

- Python 3.10-3.13; module already has `from __future__ import annotations`.
- No new dependencies.
- Every command: decorate with `@catch_exception(console=console)`, include `_: str = CONFIG_PARAM` as the final parameter, and use Rich (`console`/`err_console`) — never `print()`.
- Type hints on all function signatures.
- Marketplace URL resolution is always `(marketplace_url or SETTINGS.active.marketplace_url).rstrip("/")`.
- Tests: no `@pytest.mark.asyncio` (auto mode); use the `httpx_mock` fixture; no `unittest.mock`; no issue numbers/URLs in test names; assert concrete values.
- Before each commit: `uv run invoke format lint-code`.
- Commit messages: no AI/Claude attribution.

## API reference (verified against the live marketplace)

- List: `GET {base}/api/v1/schemas` or `GET {base}/api/v1/collections`. Params: `search=<term>`, `limit=<n>`, `cursor=<end_cursor>`. Response: `{"items": [...], "page_info": {"has_next_page": bool, "end_cursor": str|null}, "total_count": int}`.
- Detail: `GET {base}/api/v1/schemas/{ns}/{name}` (fields incl. `versions[]`, `tags[]`, `dependencies`), `GET {base}/api/v1/collections/{ns}/{name}` (fields incl. `items[]` with member `schema`, `dependencies`).
- Schema list item fields used: `namespace`, `name`, `display_name`, `download_count`, `tags[].name`, `latest_version.semver`.
- Collection list item fields used: `namespace`, `name`, `display_name`, `download_count`, `schema_count`.
- `dependencies` shape: `{"schemas": [{"namespace","name",...}], "collections": [...], "unresolved_kinds": [...], "hidden_count": int}`.
- Collection detail member: `items[i]["schema"]` has `namespace`, `name`, `display_name`.

---

### Task 1: `list` command (schemas & collections, table, pagination, `--limit`, `--json`, network errors)

Adds the core listing machinery plus the `list` command. `search` (Task 2) reuses `_run_listing`.

**Files:**

- Modify: `infrahub_sdk/ctl/marketplace.py`
- Test: `tests/unit/ctl/test_marketplace_app.py`

**Interfaces:**

- Produces:
  - `_list_url(base_url: str, item_type: MarketplaceItemType) -> str`
  - `_fetch_listing(client: httpx.AsyncClient, base_url: str, item_type: MarketplaceItemType, *, search: str | None, limit: int | None) -> tuple[list[dict[str, Any]], int]`
  - `_render_list_table(items: list[dict[str, Any]], item_type: MarketplaceItemType, total_count: int) -> None`
  - `_print_json(data: Any) -> None`
  - `_run_listing(*, item_type: MarketplaceItemType, search: str | None, limit: int | None, json_output: bool, marketplace_url: str | None) -> None`
  - `list` command (function `list_items`)
- Consumes (existing): `_make_http_client`, `_SdkConfig`, `SETTINGS`, `_fail`, `_ErrorClass`, `MarketplaceItemType`, `console`, `err_console`, `CONFIG_PARAM`, `catch_exception`.

- [ ] **Step 1: Add the Rich Table import**

At the top of `infrahub_sdk/ctl/marketplace.py`, add below `from rich.console import Console`:

```python
from rich.table import Table
```

- [ ] **Step 2: Write the failing test for listing schemas**

Add to `tests/unit/ctl/test_marketplace_app.py`:

```python
def _listing_json(item_type: str, items: list[dict], *, total: int | None = None, cursor: str | None = None) -> dict:
    """Build a marketplace list/search envelope. ``item_type`` is 'schemas' or 'collections'."""
    return {
        "items": items,
        "page_info": {"has_next_page": cursor is not None, "end_cursor": cursor},
        "total_count": total if total is not None else len(items),
    }


def _schema_item(namespace: str, name: str, *, display: str, semver: str, downloads: int, tags: list[str]) -> dict:
    return {
        "namespace": namespace,
        "name": name,
        "display_name": display,
        "download_count": downloads,
        "tags": [{"name": t} for t in tags],
        "latest_version": {"semver": semver},
    }


def test_list_schemas(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas",
        json=_listing_json(
            "schemas",
            [_schema_item("infrahub", "dcim", display="DCIM", semver="1.2.0", downloads=42, tags=["core"])],
            total=1,
        ),
    )
    result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    assert "infrahub/dcim" in result.output
    assert "DCIM" in result.output
    assert "1.2.0" in result.output
    assert "42" in result.output
    assert "core" in result.output
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest tests/unit/ctl/test_marketplace_app.py::test_list_schemas -v`
Expected: FAIL — `list` command does not exist (Typer exits non-zero / "No such command").

- [ ] **Step 4: Implement the listing helpers and `list` command**

Append to `infrahub_sdk/ctl/marketplace.py` (after `_collection_url`, before `_is_transport_failure` is fine; placement is not critical, but keep helpers above the commands):

```python
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
            detail = str(exc) or type(exc).__name__
            _fail(_ErrorClass.NETWORK, f"Marketplace request failed: {detail}")
    if json_output:
        _print_json(items)
        return
    _render_list_table(items, item_type, total_count)
```

Add the command near the other `@app.command()` definitions (e.g. above `get`):

```python
@app.command(name="list")
@catch_exception(console=console)
async def list_items(
    collections: bool = typer.Option(
        False, "--collections", is_flag=True, help="List collections instead of schemas."
    ),
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
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/unit/ctl/test_marketplace_app.py::test_list_schemas -v`
Expected: PASS

- [ ] **Step 6: Write the remaining Task 1 tests (collections, pagination, --limit)**

Add to the test file:

```python
def _collection_item(namespace: str, name: str, *, display: str, schema_count: int, downloads: int) -> dict:
    return {
        "namespace": namespace,
        "name": name,
        "display_name": display,
        "schema_count": schema_count,
        "download_count": downloads,
    }


def test_list_collections(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections",
        json=_listing_json(
            "collections",
            [_collection_item("infrahub", "security-mgmt", display="Security", schema_count=5, downloads=7)],
            total=1,
        ),
    )
    result = runner.invoke(app, ["list", "--collections"])

    assert result.exit_code == 0
    assert "infrahub/security-mgmt" in result.output
    assert "Security" in result.output
    assert "5" in result.output
    assert "7" in result.output


def test_list_follows_cursor_pagination(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas",
        json=_listing_json(
            "schemas",
            [_schema_item("infrahub", "a", display="A", semver="1.0.0", downloads=1, tags=[])],
            total=2,
            cursor="CURSOR1",
        ),
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas?cursor=CURSOR1",
        json=_listing_json(
            "schemas",
            [_schema_item("infrahub", "b", display="B", semver="1.0.0", downloads=1, tags=[])],
            total=2,
        ),
    )
    result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    assert "infrahub/a" in result.output
    assert "infrahub/b" in result.output


def test_list_limit_requests_single_page_and_shows_footer(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas?limit=1",
        json=_listing_json(
            "schemas",
            [_schema_item("infrahub", "a", display="A", semver="1.0.0", downloads=1, tags=[])],
            total=52,
            cursor="CURSOR1",
        ),
    )
    # No second page mock: if the implementation followed the cursor despite --limit,
    # pytest-httpx would raise "request not expected".
    result = runner.invoke(app, ["list", "--limit", "1"])

    assert result.exit_code == 0
    assert "infrahub/a" in result.output
    assert "Showing 1 of 52" in result.output


def test_list_network_error_exits_2(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas",
        status_code=503,
        json={"detail": "unavailable"},
    )
    result = runner.invoke(app, ["list"])

    assert result.exit_code == 2
    assert "Marketplace request failed" in result.output
```

- [ ] **Step 7: Run the full Task 1 test set**

Run: `uv run pytest tests/unit/ctl/test_marketplace_app.py -k "list_" -v`
Expected: all PASS

- [ ] **Step 8: Format, lint, commit**

```bash
uv run invoke format lint-code
git add infrahub_sdk/ctl/marketplace.py tests/unit/ctl/test_marketplace_app.py
git commit -m "feat(ctl): add marketplace list command"
```

---

### Task 2: `search` command

Thin command over `_run_listing` with the `search=` term.

**Files:**

- Modify: `infrahub_sdk/ctl/marketplace.py`
- Test: `tests/unit/ctl/test_marketplace_app.py`

**Interfaces:**

- Consumes: `_run_listing` (Task 1), `_listing_json`/`_schema_item` test helpers (Task 1).
- Produces: `search` command (function `search`).

- [ ] **Step 1: Write the failing test for search**

```python
def test_search_passes_term_and_renders(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas?search=vlan",
        json=_listing_json(
            "schemas",
            [_schema_item("infrahub", "vlan", display="VLAN", semver="1.0.0", downloads=3, tags=[])],
            total=1,
        ),
    )
    result = runner.invoke(app, ["search", "vlan"])

    assert result.exit_code == 0
    assert "infrahub/vlan" in result.output


def test_search_empty_results(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas?search=nomatch",
        json=_listing_json("schemas", [], total=0),
    )
    result = runner.invoke(app, ["search", "nomatch"])

    assert result.exit_code == 0
    # An empty catalog is not an error; the table renders with no data rows.
    assert "Identifier" in result.output
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/ctl/test_marketplace_app.py -k "search" -v`
Expected: FAIL — `search` command does not exist.

- [ ] **Step 3: Implement the `search` command**

Add near the other commands in `marketplace.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/ctl/test_marketplace_app.py -k "search" -v`
Expected: PASS

- [ ] **Step 5: Write the `--json` test (covers list & search JSON path)**

```python
import json as _json


def test_list_json_output_is_parseable(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas",
        json=_listing_json(
            "schemas",
            [_schema_item("infrahub", "dcim", display="DCIM", semver="1.2.0", downloads=42, tags=["core"])],
            total=1,
        ),
    )
    result = runner.invoke(app, ["list", "--json"])

    assert result.exit_code == 0
    parsed = _json.loads(result.output)
    assert parsed[0]["name"] == "dcim"
    assert parsed[0]["latest_version"]["semver"] == "1.2.0"
```

- [ ] **Step 6: Run the JSON test**

Run: `uv run pytest tests/unit/ctl/test_marketplace_app.py::test_list_json_output_is_parseable -v`
Expected: PASS (no code change needed — `--json` was implemented in Task 1)

- [ ] **Step 7: Format, lint, commit**

```bash
uv run invoke format lint-code
git add infrahub_sdk/ctl/marketplace.py tests/unit/ctl/test_marketplace_app.py
git commit -m "feat(ctl): add marketplace search command"
```

---

### Task 3: `show` command — schema (auto-detect, versions, tags, dependencies, `--json`)

**Files:**

- Modify: `infrahub_sdk/ctl/marketplace.py`
- Test: `tests/unit/ctl/test_marketplace_app.py`

**Interfaces:**

- Produces:
  - `_detail_url(base_url: str, item_type: MarketplaceItemType, namespace: str, name: str) -> str`
  - `_fetch_detail(client: httpx.AsyncClient, base_url: str, namespace: str, name: str, *, force_collection: bool) -> tuple[MarketplaceItemType, dict[str, Any]]`
  - `_render_detail(detail: dict[str, Any], item_type: MarketplaceItemType) -> None`
  - `show` command (function `show`)
- Consumes (existing): `_parse_identifier`, `asyncio`, `_is_transport_failure`, `_host_from`, `_fail`, `_ErrorClass`, `_print_json`, `console`, plus the `--collection` flag convention from `get`.

- [ ] **Step 1: Write the failing test for `show` on a schema**

```python
def _schema_detail() -> dict:
    return {
        "namespace": "infrahub",
        "name": "vlan",
        "display_name": "VLAN",
        "description": "VLAN schema.",
        "download_count": 105,
        "tags": [{"name": "experimental"}],
        "versions": [
            {"semver": "1.0.0", "status": "published", "created_at": "2026-04-20T23:54:19+00:00", "changelog": "Initial"},
        ],
        "dependencies": {"schemas": [{"namespace": "infrahub", "name": "dcim"}], "collections": []},
    }


def test_show_schema_autodetect(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/infrahub/vlan",
        json=_schema_detail(),
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/infrahub/vlan",
        status_code=404,
        json={"detail": "Collection not found"},
    )
    result = runner.invoke(app, ["show", "infrahub/vlan"])

    assert result.exit_code == 0
    assert "infrahub/vlan" in result.output
    assert "VLAN" in result.output
    assert "1.0.0" in result.output
    assert "published" in result.output
    assert "experimental" in result.output
    assert "infrahub/dcim" in result.output  # dependency
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/ctl/test_marketplace_app.py::test_show_schema_autodetect -v`
Expected: FAIL — `show` command does not exist.

- [ ] **Step 3: Implement `_detail_url`, `_fetch_detail`, `_render_detail`, and `show`**

Add the helpers near the other helpers in `marketplace.py`:

```python
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
            console.print(
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
```

Add the command:

```python
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
            message = str(exc) or type(exc).__name__
            _fail(_ErrorClass.NETWORK, f"Marketplace request failed: {message}")
    if json_output:
        _print_json(detail)
        return
    _render_detail(detail, item_type)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/unit/ctl/test_marketplace_app.py::test_show_schema_autodetect -v`
Expected: PASS

- [ ] **Step 5: Write the schema `--json` and network-error tests**

```python
def test_show_schema_json(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/infrahub/vlan",
        json=_schema_detail(),
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/infrahub/vlan",
        status_code=404,
        json={"detail": "Collection not found"},
    )
    result = runner.invoke(app, ["show", "infrahub/vlan", "--json"])

    assert result.exit_code == 0
    parsed = _json.loads(result.output)
    assert parsed["name"] == "vlan"
    assert parsed["versions"][0]["semver"] == "1.0.0"


def test_show_network_error_exits_2(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))
    result = runner.invoke(app, ["show", "infrahub/vlan"])

    assert result.exit_code == 2
    assert "Could not reach marketplace" in result.output
```

- [ ] **Step 6: Run the schema `show` tests**

Run: `uv run pytest tests/unit/ctl/test_marketplace_app.py -k "show_schema or show_network" -v`
Expected: PASS

- [ ] **Step 7: Format, lint, commit**

```bash
uv run invoke format lint-code
git add infrahub_sdk/ctl/marketplace.py tests/unit/ctl/test_marketplace_app.py
git commit -m "feat(ctl): add marketplace show command for schemas"
```

---

### Task 4: `show` collection (members, `--collection` force, not-found)

**Files:**

- Modify: `tests/unit/ctl/test_marketplace_app.py` (behaviour already implemented in Task 3; this task proves the collection path and not-found handling)

**Interfaces:**

- Consumes: `show` command, `_fetch_detail`, `_render_detail` (Task 3).

- [ ] **Step 1: Write the collection `show` tests**

```python
def _collection_detail() -> dict:
    return {
        "namespace": "infrahub",
        "name": "security-mgmt",
        "display_name": "Security & Management",
        "description": "Security and device management.",
        "download_count": 2,
        "items": [
            {"schema": {"namespace": "infrahub", "name": "security", "display_name": "Security"}},
            {"schema": {"namespace": "infrahub", "name": "qos", "display_name": "QoS"}},
        ],
        "dependencies": {"schemas": [{"namespace": "infrahub", "name": "location"}], "collections": []},
    }


def test_show_collection_force_flag(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/infrahub/security-mgmt",
        json=_collection_detail(),
    )
    # No schema-detail mock: --collection must not probe the schema endpoint.
    result = runner.invoke(app, ["show", "infrahub/security-mgmt", "--collection"])

    assert result.exit_code == 0
    assert "infrahub/security-mgmt" in result.output
    assert "infrahub/security" in result.output
    assert "infrahub/qos" in result.output
    assert "Schemas: 2" in result.output
    assert "infrahub/location" in result.output  # dependency


def test_show_collection_autodetect(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/infrahub/security-mgmt",
        status_code=404,
        json={"detail": "Schema not found"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/infrahub/security-mgmt",
        json=_collection_detail(),
    )
    result = runner.invoke(app, ["show", "infrahub/security-mgmt"])

    assert result.exit_code == 0
    assert "infrahub/qos" in result.output


def test_show_not_found(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/infrahub/nope",
        status_code=404,
        json={"detail": "Schema not found"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/infrahub/nope",
        status_code=404,
        json={"detail": "Collection not found"},
    )
    result = runner.invoke(app, ["show", "infrahub/nope"])

    assert result.exit_code == 1
    assert "No schema or collection named 'infrahub/nope'" in result.output


def test_show_invalid_identifier() -> None:
    result = runner.invoke(app, ["show", "no-slash"])

    assert result.exit_code == 1
    assert "Invalid identifier" in result.output
```

- [ ] **Step 2: Run the collection `show` tests**

Run: `uv run pytest tests/unit/ctl/test_marketplace_app.py -k "show_collection or show_not_found or show_invalid" -v`
Expected: PASS (no source change — Task 3 implemented this)

- [ ] **Step 3: Run the entire marketplace test module**

Run: `uv run pytest tests/unit/ctl/test_marketplace_app.py -v`
Expected: all PASS (new browsing tests plus the pre-existing `get` tests)

- [ ] **Step 4: Format, lint, commit**

```bash
uv run invoke format lint-code
git add tests/unit/ctl/test_marketplace_app.py
git commit -m "test(ctl): cover marketplace show for collections and errors"
```

---

### Task 5: Docs regeneration and changelog

**Files:**

- Modify (generated): `docs/docs/infrahubctl/infrahubctl-marketplace.mdx`
- Create: `changelog/<issue>.added.md`

- [ ] **Step 1: Regenerate CLI docs**

Run: `uv run invoke docs-generate`

- [ ] **Step 2: Verify docs are in sync**

Run: `uv run invoke docs-validate`
Expected: passes (no diff between generated and committed docs). If it reports a diff, the generation step in Step 1 did not run or was not saved — re-run Step 1.

- [ ] **Step 3: Confirm the new commands appear in the generated doc**

Run: `git diff --stat docs/docs/infrahubctl/infrahubctl-marketplace.mdx`
Expected: the file shows additions documenting `list`, `search`, and `show`.

- [ ] **Step 4: Add a changelog newsfragment**

Determine the issue number from the tracking issue for this feature. If none exists, ask the user for the issue number before creating the file. Create `changelog/<issue>.added.md` with:

```markdown
Added `infrahubctl marketplace list`, `search`, and `show` commands for browsing schemas and collections on the Infrahub Marketplace.
```

- [ ] **Step 5: Lint docs and commit**

```bash
uv run invoke lint-docs
git add docs/docs/infrahubctl/infrahubctl-marketplace.mdx changelog/
git commit -m "docs(marketplace): document list, search, and show commands"
```

---

## Self-Review

**Spec coverage:**

- `list` (schemas + `--collections`) → Task 1. ✓
- `search <term>` → Task 2. ✓
- `show <ns/name>` (schema + collection, auto-detect, `--collection`) → Tasks 3, 4. ✓
- Pagination "fetch all, `--limit` to cap" + footer → Task 1 (`_fetch_listing`, `_render_list_table`). ✓
- Rich table default + `--json` → Tasks 1 (`_render_list_table`, `_print_json`), 3 (`_render_detail`). ✓
- API mapping (list/detail endpoints, `search`/`limit`/`cursor` params) → Task 1 & 3 helpers. ✓
- Error taxonomy (INVALID_INPUT/NOT_FOUND exit 1, NETWORK exit 2) → Tasks 1 (`_run_listing`), 3/4 (`_fetch_detail`, `show`). ✓
- Reuse of existing helpers, raw dicts, no new deps, CLI-only → honoured throughout; no models introduced. ✓
- Docs regen + changelog → Task 5. ✓

**Placeholder scan:** The only intentional placeholder is `changelog/<issue>.added.md` (issue number), with an explicit instruction to obtain it in Task 5 Step 4. No other TBD/TODO.

**Type consistency:** `MarketplaceItemType` ("schema"/"collection") is used consistently by `_list_url`, `_detail_url`, `_fetch_listing`, `_render_list_table`, `_fetch_detail`, `_render_detail`, `_run_listing`. `_fetch_listing` returns `tuple[list[dict], int]` consumed by `_run_listing`. `_fetch_detail` returns `tuple[MarketplaceItemType, dict]` consumed by `show`. Test helper names (`_listing_json`, `_schema_item`, `_collection_item`, `_schema_detail`, `_collection_detail`) are defined before first use (Task 1/3) and reused later.
