from __future__ import annotations

import linecache
from collections.abc import Callable
from functools import cached_property
from pathlib import Path
from typing import Any, NoReturn

import jinja2
from jinja2 import meta, nodes
from jinja2.sandbox import SandboxedEnvironment
from netutils.utils import jinja2_convenience_function
from pydantic import BaseModel
from rich.syntax import Syntax
from rich.traceback import Traceback

from .exceptions import (
    JinjaTemplateError,
    JinjaTemplateNotFoundError,
    JinjaTemplateOperationViolationError,
    JinjaTemplateSyntaxError,
    JinjaTemplateUndefinedError,
)
from .filters import AVAILABLE_FILTERS
from .models import UndefinedJinja2Error

netutils_filters = jinja2_convenience_function()


class Jinja2Template(BaseModel):
    template: str | Path
    template_directory: Path | None = None
    filters: dict[str, Callable] | None = None
    _environment: jinja2.Environment | None = None
    _template_definition: jinja2.Template | None = None

    @cached_property
    def is_string_based(self) -> bool:
        return isinstance(self.template, str)

    @cached_property
    def is_file_based(self) -> bool:
        return isinstance(self.template, Path)

    @cached_property
    def _template(self) -> str:
        return str(self.template)

    @cached_property
    def _user_filters(self) -> list[str]:
        if not self.filters:
            return []
        return list(self.filters)

    @cached_property
    def _available_filters(self) -> list[str]:
        return [filter_definition.name for filter_definition in AVAILABLE_FILTERS] + self._user_filters

    @cached_property
    def _trusted_filters(self) -> list[str]:
        return [
            filter_definition.name for filter_definition in AVAILABLE_FILTERS if filter_definition.trusted
        ] + self._user_filters

    def get_environment(self) -> jinja2.Environment:
        if self._environment:
            return self._environment

        if self.is_string_based:
            return self._get_string_based_environment()

        return self._get_file_based_environment()

    def get_template(self) -> jinja2.Template:
        if self._template_definition:
            return self._template_definition

        try:
            if self.is_string_based:
                template = self._get_string_based_template()
            else:
                template = self._get_file_based_template()
        except jinja2.TemplateSyntaxError as exc:
            self._raise_template_syntax_error(error=exc)
        except jinja2.TemplateNotFound as exc:
            raise JinjaTemplateNotFoundError(message=exc.message, filename=str(exc.name))

        return template

    def get_variables(self) -> list[str]:
        env = self.get_environment()

        template_source = self._template
        if self.is_file_based and env.loader:
            template_source = env.loader.get_source(env, self._template)[0]

        template = env.parse(template_source)

        return sorted(meta.find_undeclared_variables(template))

    def validate_template(self, restricted: bool = True) -> None:
        allowed_list = self._available_filters
        if restricted:
            allowed_list = self._trusted_filters

        env = self.get_environment()
        template_source = self._template
        if self.is_file_based and env.loader:
            template_source = env.loader.get_source(env, self._template)[0]

        template = env.parse(template_source)
        for node in template.find_all(nodes.Filter):
            if node.name not in allowed_list:
                raise JinjaTemplateOperationViolationError(f"The '{node.name}' filter isn't allowed to be used")

        forbidden_operations = ["Call", "Import", "Include"]
        if self.is_string_based and any(node.__class__.__name__ in forbidden_operations for node in template.body):
            raise JinjaTemplateOperationViolationError(
                f"These operations are forbidden for string based templates: {forbidden_operations}"
            )

    async def render(self, variables: dict[str, Any]) -> str:
        template = self.get_template()
        try:
            output = await template.render_async(variables)
        except jinja2.exceptions.TemplateNotFound as exc:
            raise JinjaTemplateNotFoundError(message=exc.message, filename=str(exc.name), base_template=template.name)
        except jinja2.TemplateSyntaxError as exc:
            self._raise_template_syntax_error(error=exc)
        except jinja2.UndefinedError as exc:
            traceback = Traceback(show_locals=False)
            errors = _identify_faulty_jinja_code(traceback=traceback)
            raise JinjaTemplateUndefinedError(message=exc.message, errors=errors)
        except Exception as exc:
            if error_message := getattr(exc, "message", None):
                message = error_message
            else:
                message = str(exc)
            raise JinjaTemplateError(message=message or "Unknown template error")

        return output

    def _get_string_based_environment(self) -> jinja2.Environment:
        env = SandboxedEnvironment(enable_async=True, undefined=jinja2.StrictUndefined)
        self._set_filters(env=env)
        self._environment = env
        return self._environment

    def _get_file_based_environment(self) -> jinja2.Environment:
        template_loader = jinja2.FileSystemLoader(searchpath=str(self.template_directory))
        env = jinja2.Environment(
            loader=template_loader,
            trim_blocks=True,
            lstrip_blocks=True,
            enable_async=True,
        )
        self._set_filters(env=env)
        self._environment = env
        return self._environment

    def _set_filters(self, env: jinja2.Environment) -> None:
        for default_filter in list(env.filters.keys()):
            if default_filter not in self._available_filters:
                del env.filters[default_filter]

        # Add filters from netutils
        env.filters.update(
            {name: jinja_filter for name, jinja_filter in netutils_filters.items() if name in self._available_filters}
        )
        # Add user supplied filters
        env.filters.update(self.filters or {})

    def _get_string_based_template(self) -> jinja2.Template:
        env = self.get_environment()
        self._template_definition = env.from_string(self._template)
        return self._template_definition

    def _get_file_based_template(self) -> jinja2.Template:
        env = self.get_environment()
        self._template_definition = env.get_template(self._template)
        return self._template_definition

    def _raise_template_syntax_error(self, error: jinja2.TemplateSyntaxError) -> NoReturn:
        filename: str | None = None
        if error.filename and self.template_directory:
            filename = error.filename
            if error.filename.startswith(str(self.template_directory)):
                filename = error.filename[len(str(self.template_directory)) :]

        raise JinjaTemplateSyntaxError(message=error.message, filename=filename, lineno=error.lineno)


def _identify_faulty_jinja_code(traceback: Traceback, nbr_context_lines: int = 3) -> list[UndefinedJinja2Error]:
    """This function identifies the faulty Jinja2 code and beautify it to provide meaningful information to the user.

    We use the rich's Traceback to parse the complete stack trace and extract Frames for each exception found in the trace.
    """
    response = []

    # Extract only the Jinja related exception
    for frame in [frame for frame in traceback.trace.stacks[0].frames if not frame.filename.endswith(".py")]:
        code = "".join(linecache.getlines(frame.filename))
        if frame.filename == "<template>":
            lexer_name = "text"
        else:
            lexer_name = Traceback._guess_lexer(frame.filename, code)
        syntax = Syntax(
            code,
            lexer_name,
            line_numbers=True,
            line_range=(
                frame.lineno - nbr_context_lines,
                frame.lineno + nbr_context_lines,
            ),
            highlight_lines={frame.lineno},
            code_width=88,
            theme=traceback.theme,
            dedent=False,
        )
        response.append(UndefinedJinja2Error(frame=frame, syntax=syntax))

    return response
