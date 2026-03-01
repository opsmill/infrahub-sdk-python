from __future__ import annotations

from pathlib import Path

import httpx
import typer
from rich.console import Console

from ..async_typer import AsyncTyper
from ..ctl import config
from ..ctl.parameters import CONFIG_PARAM
from ..ctl.utils import catch_exception

app = AsyncTyper()
console = Console()


@app.callback()
def callback() -> None:
    """Browse and download schemas from the Infrahub Marketplace."""


def _parse_identifier(identifier: str) -> tuple[str, str]:
    """Validate and split a 'namespace/name' identifier."""
    parts = identifier.split("/")
    if len(parts) != 2 or not all(parts):
        console.print(f"[red]Invalid identifier '{identifier}'. Expected format: namespace/name")
        raise typer.Exit(1)
    return parts[0], parts[1]


async def _download_schema(
    client: httpx.AsyncClient,
    base_url: str,
    namespace: str,
    name: str,
    version: str | None,
    output_dir: Path,
) -> Path:
    """Download a single schema and write it to disk. Returns the written file path."""
    if version:
        url = f"{base_url}/api/v1/schemas/{namespace}/{name}/versions/{version}/download"
    else:
        url = f"{base_url}/api/v1/schemas/{namespace}/{name}/download"

    resp = await client.get(url)
    if resp.status_code == 404:
        detail = "not found"
        try:
            detail = resp.json().get("detail", detail)
        except Exception:
            pass
        console.print(f"[red]Error: {detail}")
        raise typer.Exit(1)
    resp.raise_for_status()

    resolved_version = version or resp.headers.get("x-schema-version", "latest")
    filename = f"{name}.yml"
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / filename
    file_path.write_text(resp.text, encoding="utf-8")

    console.print(f"[green]Downloaded {namespace}/{name} v{resolved_version} -> {file_path}")
    return file_path


async def _download_collection(
    client: httpx.AsyncClient,
    base_url: str,
    namespace: str,
    name: str,
    output_dir: Path,
) -> list[Path]:
    """Download all schemas in a collection. Returns list of written file paths."""
    url = f"{base_url}/api/v1/collections/{namespace}/{name}/download"
    resp = await client.get(url)
    if resp.status_code == 404:
        detail = "not found"
        try:
            detail = resp.json().get("detail", detail)
        except Exception:
            pass
        console.print(f"[red]Error: {detail}")
        raise typer.Exit(1)
    resp.raise_for_status()

    data = resp.json()
    meta = data["collection"]
    schemas = data["schemas"]
    skipped = meta.get("skipped", [])

    collection_dir = output_dir / name
    collection_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    for schema in schemas:
        filename = f"{schema['name']}.yml"
        file_path = collection_dir / filename
        file_path.write_text(schema["content"], encoding="utf-8")
        paths.append(file_path)
        console.print(f"[green]Downloaded {schema['namespace']}/{schema['name']} v{schema['semver']} -> {file_path}")

    for item in skipped:
        console.print(f"[yellow]Skipped {item['namespace']}/{item['name']}: {item['reason']}")

    console.print(
        f"\n[green]Collection {namespace}/{name}: "
        f"{meta['downloaded_count']}/{meta['schema_count']} schemas downloaded"
    )
    return paths


@app.command()
@catch_exception(console=console)
async def download(
    identifier: str = typer.Argument(
        help="Schema or collection identifier in namespace/name format"
    ),
    version: str | None = typer.Option(
        None, "--version", "-v", help="Specific schema version (semver). Default: latest published."
    ),
    collection: bool = typer.Option(
        False, "--collection", "-c", help="Download all schemas in a collection instead of a single schema."
    ),
    load: bool = typer.Option(
        False, "--load", "-l", help="After downloading, load the schema(s) into Infrahub."
    ),
    output_dir: Path = typer.Option(
        Path("schemas"), "--output-dir", "-o", help="Directory to save downloaded files."
    ),
    marketplace_url: str | None = typer.Option(
        None,
        "--marketplace-url",
        help="Base URL of the Infrahub Marketplace. Overrides config/env.",
    ),
    _: str = CONFIG_PARAM,
) -> None:
    """Download a schema or collection from the Infrahub Marketplace."""
    namespace, name = _parse_identifier(identifier)

    resolved_url = marketplace_url or config.SETTINGS.active.marketplace_url
    base_url = resolved_url.rstrip("/")

    async with httpx.AsyncClient(follow_redirects=True) as client:
        if collection:
            if version:
                console.print("[yellow]Warning: --version is ignored when downloading a collection.")
            paths = await _download_collection(client, base_url, namespace, name, output_dir)
        else:
            path = await _download_schema(client, base_url, namespace, name, version, output_dir)
            paths = [path]

    if load:
        console.print("\n[bold]Loading schema(s) into Infrahub...")
        from ..ctl.client import initialize_client

        infrahub_client = initialize_client()
        schemas_data = []
        for file_path in paths:
            import yaml

            content = yaml.safe_load(file_path.read_text(encoding="utf-8"))
            schemas_data.append(content)

        response = await infrahub_client.schema.load(schemas=schemas_data)
        if response.errors:
            console.print("[red]Schema load failed:")
            for err in response.errors if isinstance(response.errors, list) else [response.errors]:
                console.print(f"[red]  {err}")
            raise typer.Exit(1)

        if response.schema_updated:
            console.print("[green]Schema(s) loaded into Infrahub successfully.")
        else:
            console.print("[green]Schema in Infrahub was already up to date.")
