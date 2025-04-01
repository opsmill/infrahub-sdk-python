from rich.console import Console

from ..schema.repository import InfrahubRepositoryConfig
from ..template.exceptions import (
    JinjaTemplateError,
    JinjaTemplateNotFoundError,
    JinjaTemplateSyntaxError,
    JinjaTemplateUndefinedError,
)


def list_jinja2_transforms(config: InfrahubRepositoryConfig) -> None:
    console = Console()
    console.print(f"Jinja2 transforms defined in repository: {len(config.jinja2_transforms)}")

    for transform in config.jinja2_transforms:
        console.print(f"{transform.name} ({transform.template_path})")


def print_template_errors(error: JinjaTemplateError, console: Console) -> None:
    if isinstance(error, JinjaTemplateNotFoundError):
        console.print("[red]An error occurred while rendering the jinja template")
        console.print("")
        if error.base_template:
            console.print(f"Base template: [yellow]{error.base_template}")
        console.print(f"Missing template: [yellow]{error.filename}")
        return

    if isinstance(error, JinjaTemplateUndefinedError):
        console.print("[red]An error occurred while rendering the jinja template")
        for current_error in error.errors:
            console.print(f"[yellow]{current_error.frame.filename} on line {current_error.frame.lineno}\n")
            console.print(current_error.syntax)
        console.print("")
        console.print(error.message)
        return

    if isinstance(error, JinjaTemplateSyntaxError):
        console.print("[red]A syntax error was encountered within the template")
        console.print("")
        if error.filename:
            console.print(f"Filename: [yellow]{error.filename}")
        console.print(f"Line number: [yellow]{error.lineno}")
        console.print()
        console.print(error.message)
        return

    console.print("[red]An error occurred while rendering the jinja template")
    console.print("")
    console.print(f"[yellow]{error.message}")
