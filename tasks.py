from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from shutil import which
from typing import Any

from invoke import Context, task

CURRENT_DIRECTORY = Path(__file__).resolve()
DOCUMENTATION_DIRECTORY = CURRENT_DIRECTORY.parent / "docs"

MAIN_DIRECTORY_PATH = Path(__file__).parent


def is_tool_installed(name: str) -> bool:
    """Check whether `name` is on PATH and marked as executable."""
    return which(name) is not None


def _generate(context: Context) -> None:
    """Generate documentation output from code."""
    _generate_infrahubctl_documentation(context=context)
    _generate_infrahub_sdk_configuration_documentation()
    _generate_infrahub_sdk_template_documentation()


def _generate_infrahubctl_documentation(context: Context) -> None:
    """Generate the documentation for infrahubctl CLI using typer-cli."""
    from infrahub_sdk.ctl.cli import app

    output_dir = DOCUMENTATION_DIRECTORY / "docs" / "infrahubctl"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Delete any existing infrahubctl- files in output dir
    for file in output_dir.glob("infrahubctl-*"):
        file.unlink()

    print(" - Generate infrahubctl CLI documentation")
    for cmd in app.registered_commands:
        if cmd.hidden:
            continue
        exec_cmd = f'poetry run typer --func {cmd.name} infrahub_sdk.ctl.cli_commands utils docs --name "infrahubctl {cmd.name}"'
        exec_cmd += f" --output docs/docs/infrahubctl/infrahubctl-{cmd.name}.mdx"
        with context.cd(MAIN_DIRECTORY_PATH):
            context.run(exec_cmd)

    for cmd in app.registered_groups:
        if cmd.hidden:
            continue
        exec_cmd = f"poetry run typer infrahub_sdk.ctl.{cmd.name} utils docs"
        exec_cmd += f' --name "infrahubctl {cmd.name}" --output docs/docs/infrahubctl/infrahubctl-{cmd.name}.mdx'
        with context.cd(MAIN_DIRECTORY_PATH):
            context.run(exec_cmd)


def _generate_infrahub_sdk_configuration_documentation() -> None:
    """Generate documentation for the Infrahub SDK configuration."""
    import jinja2

    from infrahub_sdk.config import ConfigBase

    schema = ConfigBase.model_json_schema()
    env_vars = _get_env_vars()
    definitions = schema.get("$defs", {})

    properties = []
    for name, prop in schema["properties"].items():
        choices: list[dict[str, Any]] = []
        kind = ""
        composed_type = ""

        if "allOf" in prop:
            choices = definitions.get(prop["allOf"][0]["$ref"].split("/")[-1], {}).get("enum", [])
            kind = definitions.get(prop["allOf"][0]["$ref"].split("/")[-1], {}).get("type", "")

        if "anyOf" in prop:
            composed_type = ", ".join(i["type"] for i in prop.get("anyOf", []) if "type" in i and i["type"] != "null")

        properties.append(
            {
                "name": name,
                "description": prop.get("description", ""),
                "type": prop.get("type", kind) or composed_type or "object",
                "choices": choices,
                "default": prop.get("default", ""),
                "env_vars": env_vars.get(name, []),
            }
        )

    print(" - Generate Infrahub SDK configuration documentation")

    template_file = DOCUMENTATION_DIRECTORY / "_templates" / "sdk_config.j2"
    output_file = DOCUMENTATION_DIRECTORY / "docs" / "python-sdk" / "reference" / "config.mdx"

    if not template_file.exists():
        print(f"Unable to find the template file at {template_file}")
        sys.exit(-1)

    template_text = template_file.read_text(encoding="utf-8")

    environment = jinja2.Environment(trim_blocks=True)
    template = environment.from_string(template_text)
    rendered_file = template.render(properties=properties)

    output_file.write_text(rendered_file, encoding="utf-8")
    print(f"Docs saved to: {output_file}")


def _generate_infrahub_sdk_template_documentation() -> None:
    """Generate documentation for the Infrahub SDK template reference."""
    from infrahub_sdk.template import Jinja2Template
    from infrahub_sdk.template.filters import BUILTIN_FILTERS, NETUTILS_FILTERS

    output_file = DOCUMENTATION_DIRECTORY / "docs" / "python-sdk" / "reference" / "templating.mdx"
    jinja2_template = Jinja2Template(
        template=Path("sdk_template_reference.j2"),
        template_directory=DOCUMENTATION_DIRECTORY / "_templates",
    )

    rendered_file = asyncio.run(
        jinja2_template.render(variables={"builtin": BUILTIN_FILTERS, "netutils": NETUTILS_FILTERS})
    )
    output_file.write_text(rendered_file, encoding="utf-8")
    print(f"Docs saved to: {output_file}")


def _get_env_vars() -> dict[str, list[str]]:
    """Retrieve environment variables for Infrahub SDK configuration."""
    from collections import defaultdict

    from pydantic_settings import EnvSettingsSource

    from infrahub_sdk.config import ConfigBase

    env_vars: dict[str, list[str]] = defaultdict(list)
    settings = ConfigBase()
    env_settings = EnvSettingsSource(settings.__class__, env_prefix=settings.model_config.get("env_prefix", ""))

    for field_name, field in settings.model_fields.items():
        for field_key, field_env_name, _ in env_settings._extract_field_info(field, field_name):
            env_vars[field_key].append(field_env_name.upper())

    return env_vars


@task
def format(context: Context) -> None:
    """Run RUFF to format all Python files."""

    exec_cmds = ["ruff format .", "ruff check . --fix"]
    with context.cd(MAIN_DIRECTORY_PATH):
        for cmd in exec_cmds:
            context.run(cmd)


@task
def lint_yaml(context: Context) -> None:
    """Run Linter to check all Python files."""
    print(" - Check code with yamllint")
    exec_cmd = "yamllint ."
    with context.cd(MAIN_DIRECTORY_PATH):
        context.run(exec_cmd)


@task
def lint_mypy(context: Context) -> None:
    """Run Linter to check all Python files."""
    print(" - Check code with mypy")
    exec_cmd = "mypy --show-error-codes infrahub_sdk"
    with context.cd(MAIN_DIRECTORY_PATH):
        context.run(exec_cmd)


@task
def lint_ruff(context: Context) -> None:
    """Run Linter to check all Python files."""
    print(" - Check code with ruff")
    exec_cmd = "ruff check ."
    with context.cd(MAIN_DIRECTORY_PATH):
        context.run(exec_cmd)


@task
def lint_markdownlint(context: Context) -> None:
    """Run markdownlint to check all markdown files."""
    if not is_tool_installed("markdownlint-cli2"):
        print(" - markdownlint-cli2 is not installed, skipping documentation linting")
        return

    print(" - Check documentation with markdownlint-cli2")
    exec_cmd = "markdownlint-cli2 **/*.{md,mdx} --config .markdownlint.yaml"
    with context.cd(MAIN_DIRECTORY_PATH):
        context.run(exec_cmd)


@task
def lint_vale(context: Context) -> None:
    """Run vale to check all documentation files."""
    if not is_tool_installed("vale"):
        print(" - vale is not installed, skipping documentation style linting")
        return

    print(" - Check documentation style with vale")
    exec_cmd = r'vale $(find ./docs -type f \( -name "*.mdx" -o -name "*.md" \) -not -path "*/node_modules/*")'
    with context.cd(MAIN_DIRECTORY_PATH):
        context.run(exec_cmd)


@task
def lint_docs(context: Context) -> None:
    """Run all documentation linters."""
    lint_markdownlint(context)
    lint_vale(context)


@task(name="lint")
def lint_all(context: Context) -> None:
    """Run all linters."""
    lint_yaml(context)
    lint_ruff(context)
    lint_mypy(context)
    lint_docs(context)


@task(name="docs-validate")
def docs_validate(context: Context) -> None:
    """Validate that the generated documentation is committed to Git."""
    _generate(context=context)
    exec_cmd = "git diff --exit-code docs"
    with context.cd(MAIN_DIRECTORY_PATH):
        context.run(exec_cmd)


@task(name="docs")
def docs_build(context: Context) -> None:
    """Build documentation website."""
    exec_cmd = "npm run build"

    with context.cd(DOCUMENTATION_DIRECTORY):
        output = context.run(exec_cmd)

    if output and output.exited != 0:
        sys.exit(-1)


@task(name="generate-infrahubctl")
def generate_infrahubctl(context: Context) -> None:
    """Generate documentation for the infrahubctl cli."""
    _generate_infrahubctl_documentation(context=context)


@task(name="generate-sdk")
def generate_python_sdk(context: Context) -> None:  # noqa: ARG001
    """Generate documentation for the Python SDK."""
    _generate_infrahub_sdk_configuration_documentation()
    _generate_infrahub_sdk_template_documentation()


@task(name="generate-sdk-api-docs")
def generate_sdk_api_docs(context: Context, output: str | None = None) -> None:
    """Generate API documentation for the Python SDK."""

    # This is the list of code modules to generate documentation for.
    MODULES_LIST = [
        "infrahub_sdk.client",
        "infrahub_sdk.node.node",
    ]

    import operator
    import shutil
    import tempfile
    from functools import reduce

    output_dir = Path(output) if output else DOCUMENTATION_DIRECTORY / "docs" / "python-sdk" / "sdk_ref"

    if not is_tool_installed("mdxify"):
        print(" - mdxify is not installed, skipping documentation generation")
        return

    # Create a temporary directory to store the generated documentation
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Generate the API documentation using mdxify and get flat file structure
        exec_cmd = f"mdxify {' '.join(MODULES_LIST)} --output-dir {tmp_dir}"
        context.run(exec_cmd, pty=True)

        # Remove current obsolete documentation file structure
        if (output_dir / "infrahub_sdk").exists():
            shutil.rmtree(output_dir / "infrahub_sdk")

        # Get all .mdx files in the generated doc folder and apply filters
        filters = ["__init__"]
        filtered_files = [
            file
            for file in list(Path(tmp_dir).glob("*.mdx"))
            if all(filter.lower() not in file.name for filter in filters)
        ]

        # Reorganize the generated relevant files into the desired structure
        for mdx_file in filtered_files:
            target_path = output_dir / reduce(operator.truediv, (Path(part) for part in mdx_file.name.split("-")))

            # Create the future parent directory if it doesn't exist
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # Move the file to the new location
            shutil.move(mdx_file, target_path)

        # Fix possible linting issues in the generated documentation
        if not is_tool_installed("markdownlint-cli2"):
            print(" - markdownlint-cli2 is not installed, skipping documentation linting")
            return

        exec_cmd = f"markdownlint-cli2 {output_dir}/ --fix --config .markdownlint.yaml"
        context.run(exec_cmd, pty=True)
