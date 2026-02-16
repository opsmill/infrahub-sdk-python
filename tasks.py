from __future__ import annotations

import json
import operator
import shutil
import sys
from functools import reduce
from pathlib import Path
from shutil import which
from typing import TYPE_CHECKING

from invoke import Context, Exit, task

if TYPE_CHECKING:
    from docs.docs_generation.content_gen_methods.command.typer_command import ATyperCommand

from docs.docs_generation.content_gen_methods.mdx.mdx_reorder import PagePriority

CURRENT_DIRECTORY = Path(__file__).resolve()
DOCUMENTATION_DIRECTORY = CURRENT_DIRECTORY.parent / "docs"

MAIN_DIRECTORY_PATH = Path(__file__).parent

# Priority ordering for generated API documentation pages.
# Keys match the mdxify output filenames (same keys used in generated_files dict).
PAGE_PRIORITIES: dict[str, PagePriority] = {
    "infrahub_sdk-client.mdx": PagePriority(
        classes=["InfrahubClient", "InfrahubClientSync"],
    ),
    "infrahub_sdk-node-node.mdx": PagePriority(
        classes=["InfrahubNode", "InfrahubNodeSync"],
    ),
}


def require_tool(name: str, install_hint: str) -> None:
    """Raise ``Exit`` if *name* is not found on PATH."""
    if which(name) is None:
        raise Exit(f" - {name} is not installed. {install_hint}", code=1)


@task(name="docs-generate")
def docs_generate(context: Context) -> None:
    """Generate all documentation (infrahubctl CLI + Python SDK)."""
    _generate_infrahubctl_documentation(context=context)
    generate_python_sdk(context)


def _generate_infrahubctl_documentation(context: Context) -> None:
    """Generate the documentation for infrahubctl CLI using typer-cli."""
    from docs.docs_generation.content_gen_methods import (
        CommandOutputDocContentGenMethod,
        TyperGroupCommand,
        TyperSingleCommand,
    )
    from docs.docs_generation.pages import DocPage, MDXDocPage
    from infrahub_sdk.ctl.cli import app

    output_dir = DOCUMENTATION_DIRECTORY / "docs" / "infrahubctl"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Delete any existing infrahubctl- files in output dir
    for file in output_dir.glob("infrahubctl-*"):
        file.unlink()

    print(" - Generate infrahubctl CLI documentation")
    commands: list[ATyperCommand] = [
        TyperSingleCommand(name=cmd.name) for cmd in app.registered_commands if not cmd.hidden and cmd.name
    ]
    commands.extend(TyperGroupCommand(name=cmd.name) for cmd in app.registered_groups if not cmd.hidden and cmd.name)

    for typer_cmd in commands:
        # Generating one documentation page for one command
        page = DocPage(
            content_gen_method=CommandOutputDocContentGenMethod(
                context=context,
                working_directory=MAIN_DIRECTORY_PATH,
                command=typer_cmd,
            ),
        )
        output_path = output_dir / f"infrahubctl-{typer_cmd.name}.mdx"
        MDXDocPage(page=page, output_path=output_path).to_mdx()


def _generate_infrahub_sdk_configuration_documentation() -> None:
    """Generate documentation for the Infrahub SDK configuration."""
    from docs.docs_generation.content_gen_methods import Jinja2DocContentGenMethod
    from docs.docs_generation.helpers import build_config_properties
    from docs.docs_generation.pages import DocPage, MDXDocPage
    from infrahub_sdk.template import Jinja2Template

    print(" - Generate Infrahub SDK configuration documentation")
    # Generating one documentation page for the ConfigBase.model_json_schema()
    page = DocPage(
        content_gen_method=Jinja2DocContentGenMethod(
            template=Jinja2Template(
                template=Path("sdk_config.j2"),
                template_directory=DOCUMENTATION_DIRECTORY / "_templates",
            ),
            template_variables={"properties": build_config_properties()},
        ),
    )
    output_path = DOCUMENTATION_DIRECTORY / "docs" / "python-sdk" / "reference" / "config.mdx"
    MDXDocPage(page=page, output_path=output_path).to_mdx()


def _generate_infrahub_sdk_template_documentation() -> None:
    """Generate documentation for the Infrahub SDK template reference."""
    from docs.docs_generation.content_gen_methods import Jinja2DocContentGenMethod
    from docs.docs_generation.pages import DocPage, MDXDocPage
    from infrahub_sdk.template import Jinja2Template
    from infrahub_sdk.template.filters import BUILTIN_FILTERS, NETUTILS_FILTERS

    print(" - Generate Infrahub SDK template documentation")
    # Generating one documentation page for template documentation
    page = DocPage(
        content_gen_method=Jinja2DocContentGenMethod(
            template=Jinja2Template(
                template=Path("sdk_template_reference.j2"),
                template_directory=DOCUMENTATION_DIRECTORY / "_templates",
            ),
            template_variables={"builtin": BUILTIN_FILTERS, "netutils": NETUTILS_FILTERS},
        ),
    )
    output_path = DOCUMENTATION_DIRECTORY / "docs" / "python-sdk" / "reference" / "templating.mdx"
    MDXDocPage(page=page, output_path=output_path).to_mdx()


def get_modules_to_document() -> list[str]:
    """Return the list of Python module paths to document with mdxify.

    Auto-discovers packages under ``infrahub_sdk/`` and validates that every
    discovered package is explicitly categorised as either *to document* or
    *to ignore*.  Individual ``.py`` modules can be added via
    ``extra_modules_to_document``.
    """
    # Packages (sub-folders of infrahub_sdk/) to document.
    # Passed to mdxify as "infrahub_sdk.<name>".
    packages_to_document = [
        "node",
    ]

    # Packages explicitly ignored for API doc generation.
    packages_to_ignore = [
        "ctl",
        "graphql",
        "protocols_generator",
        "pytest_plugin",
        "schema",
        "spec",
        "task",
        "template",
        "testing",
        "transfer",
    ]

    # Extra modules (individual .py files, not packages) to document.
    extra_modules_to_document = [
        "infrahub_sdk.client",
    ]

    # Auto-discover all packages under infrahub_sdk/
    sdk_dir = Path(__file__).parent / "infrahub_sdk"
    discovered_packages = {d.name for d in sdk_dir.iterdir() if d.is_dir() and (d / "__init__.py").exists()}

    # Validate that every discovered package is categorized and vice versa
    declared = set(packages_to_document) | set(packages_to_ignore)
    uncategorized = discovered_packages - declared
    unknown = declared - discovered_packages

    if uncategorized:
        raise ValueError(
            f"Uncategorized packages under infrahub_sdk/: {sorted(uncategorized)}. "
            "Add them to packages_to_document or packages_to_ignore in tasks.py"
        )

    if unknown:
        raise ValueError(f"Declared packages that no longer exist: {sorted(unknown)}")

    return [f"infrahub_sdk.{pkg}" for pkg in packages_to_document] + extra_modules_to_document


@task(name="generate-sdk-api-docs")
def _generate_sdk_api_docs(context: Context) -> None:
    """Generate API documentation for the Python SDK."""
    from docs.docs_generation.content_gen_methods import FilePrintingDocContentGenMethod, MdxCodeDocumentation
    from docs.docs_generation.pages import DocPage, MDXDocPage

    print(" - Generate Python SDK API documentation")
    require_tool("mdxify", "Install it with: uv sync --all-groups --all-extras")

    modules_to_document = get_modules_to_document()

    output_dir = DOCUMENTATION_DIRECTORY / "docs" / "python-sdk" / "sdk_ref"

    if (output_dir / "infrahub_sdk").exists():
        shutil.rmtree(output_dir / "infrahub_sdk")

    documentation = MdxCodeDocumentation(page_priorities=PAGE_PRIORITIES)
    generated_files = documentation.generate(context=context, modules_to_document=modules_to_document)

    for file_key, mdxified_file in generated_files.items():
        page = DocPage(content_gen_method=FilePrintingDocContentGenMethod(file=mdxified_file))
        target_path = output_dir / reduce(operator.truediv, (Path(part) for part in file_key.split("-")))
        MDXDocPage(page=page, output_path=target_path).to_mdx()

    with context.cd(DOCUMENTATION_DIRECTORY):
        context.run(f"npx --no-install markdownlint-cli2 {output_dir}/ --fix --config .markdownlint.yaml", pty=True)


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
def lint_ty(context: Context) -> None:
    """Run ty type checker against all Python files."""
    print(" - Check code with ty")
    exec_cmd = "uv run ty check ."
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
    print(" - Check documentation with markdownlint-cli2")
    exec_cmd = "npx --no-install markdownlint-cli2 **/*.{md,mdx} !node_modules/** --config .markdownlint.yaml"
    with context.cd(DOCUMENTATION_DIRECTORY):
        context.run(exec_cmd)


@task
def lint_vale(context: Context) -> None:
    """Run vale to check all documentation files."""
    print(" - Check documentation style with vale")
    require_tool("vale", "Install it from: https://vale.sh/docs/install")

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
    lint_ty(context)
    lint_mypy(context)
    lint_docs(context)


@task(name="docs-validate")
def docs_validate(context: Context) -> None:
    """Validate that the generated documentation matches the committed version.

    Regenerates all documentation and checks for modified, deleted, or new
    untracked files under docs/. Exits with a non-zero code and a descriptive
    message when the working tree diverges from what is committed.
    """
    docs_generate(context)
    with context.cd(DOCUMENTATION_DIRECTORY):
        diff_result = context.run("git diff --name-only docs", hide=True)
        changed_files = diff_result.stdout.strip() if diff_result else ""
        untracked_result = context.run("git ls-files --others --exclude-standard docs", hide=True)
        untracked_files = untracked_result.stdout.strip() if untracked_result else ""

        if changed_files or untracked_files:
            message = "Generated documentation is out of sync with the committed version.\n"
            message += "Run 'uv run invoke docs-generate' and commit the result.\n\n"
            if changed_files:
                message += f"Modified or deleted files:\n{changed_files}\n\n"
            if untracked_files:
                message += f"New untracked files:\n{untracked_files}\n"
            raise Exit(message, code=1)


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
def generate_python_sdk(context: Context) -> None:
    """Generate documentation for the Python SDK."""
    _generate_infrahub_sdk_configuration_documentation()
    _generate_infrahub_sdk_template_documentation()
    _generate_sdk_api_docs(context)


@task
def generate_repository_jsonschema(context: Context) -> None:
    """Generate JSON schema file for repository configuration. https://github.com/opsmill/infrahub-jsonschema"""
    from infrahub_sdk.schema.repository import InfrahubRepositoryConfig

    repository_jsonschema = MAIN_DIRECTORY_PATH / "generated" / "repository-config" / "develop.json"

    with context.cd(MAIN_DIRECTORY_PATH):
        schema = json.dumps(InfrahubRepositoryConfig.model_json_schema(), indent=4)
        repository_jsonschema.parent.mkdir(parents=True, exist_ok=True)
        repository_jsonschema.write_text(schema)
        print(f"Wrote to {repository_jsonschema}")
