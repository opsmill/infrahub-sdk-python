import os
from pathlib import Path

import httpx
from invoke import Context, task

# If no version is indicated, we will take the latest
VERSION = os.getenv("INFRAHUB_IMAGE_VER", None)


@task
def start(context: Context) -> None:
    """
    Start the services using docker-compose in detached mode.
    """
    download_compose_file(context, override=False)
    context.run("docker compose up -d")


@task
def destroy(context: Context) -> None:
    """
    Stop and remove containers, networks, and volumes.
    """
    download_compose_file(context, override=False)
    context.run("docker compose down -v")


@task
def stop(context: Context) -> None:
    """
    Stop containers and remove networks.
    """
    download_compose_file(context, override=False)
    context.run("docker compose down")


@task(help={"component": "Optional name of a specific service to restart."})
def restart(context: Context, component: str = "") -> None:
    """
    Restart all services or a specific one using docker-compose.
    """
    download_compose_file(context, override=False)
    if component:
        context.run(f"docker compose restart {component}")
        return

    context.run("docker compose restart")


@task
def load_schema(ctx: Context) -> None:
    """
    Load schemas into InfraHub using infrahubctl.
    """
    ctx.run("infrahubctl schema load schemas")


@task
def test(ctx: Context) -> None:
    """
    Run tests using pytest.
    """
    ctx.run("pytest tests")


@task(help={"override": "Redownload the compose file even if it already exists."})
def download_compose_file(context: Context, override: bool = False) -> Path:  # noqa ARG001
    """
    Download docker-compose.yml from InfraHub if missing or override is True.
    """
    compose_file = Path("./docker-compose.yml")

    if compose_file.exists() and not override:
        return compose_file

    response = httpx.get("https://infrahub.opsmill.io")
    response.raise_for_status()

    with compose_file.open("w") as f:
        f.write(response.content.decode())

    return compose_file
