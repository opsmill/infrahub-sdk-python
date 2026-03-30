from __future__ import annotations

import linecache
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

import jinja2
from jinja2 import meta, nodes
from jinja2.sandbox import SandboxedEnvironment
from netutils.utils import jinja2_convenience_function
from rich.syntax import Syntax
from rich.traceback import Traceback

from .exceptions import (
    JinjaTemplateError,
    JinjaTemplateNotFoundError,
    JinjaTemplateOperationViolationError,
    JinjaTemplateSyntaxError,
    JinjaTemplateUndefinedError,
)
from .filters import AVAILABLE_FILTERS, ExecutionContext
from .infrahub_filters import InfrahubFilters, from_json, from_yaml
from .models import UndefinedJinja2Error

if TYPE_CHECKING:
    from infrahub_sdk.client import InfrahubClient

netutils_filters = jinja2_convenience_function()


class Jinja2Template:
    def __init__(
        self,
        template: str | Path,
        template_directory: Path | None = None,
        filters: dict[str, Callable] | None = None,
        client: InfrahubClient | None = None,
    ) -> None:
        self.is_string_based = isinstance(template, str)
        self.is_file_based = isinstance(template, Path)
        self._template = str(template)
        self._template_directory = template_directory
        self._environment: jinja2.Environment | None = None

        self._available_filters = [filter_definition.name for filter_definition in AVAILABLE_FILTERS]

        self._filters = filters or {}
        self._user_filter_names: set[str] = set(self._filters.keys())
        for user_filter in self._filters:
            self._available_filters.append(user_filter)

        self._register_client_filters(client=client)
        self._register_filter("from_json", from_json)
        self._register_filter("from_yaml", from_yaml)

        self._template_definition: jinja2.Template | None = None

    def set_client(self, client: InfrahubClient) -> None:
        """Set or replace the InfrahubClient used by client-dependent filters."""
        self._infrahub_filters.client = client
        if self._environment:
            for name in InfrahubFilters.get_filter_names():
                self._environment.filters[name] = self._filters[name]

    def _register_filter(self, name: str, func: Callable) -> None:
        self._filters[name] = func
        if name not in self._available_filters:
            self._available_filters.append(name)

    def _register_client_filters(self, client: InfrahubClient | None) -> None:
        self._infrahub_filters = InfrahubFilters(client=client)
        for name in InfrahubFilters.get_filter_names():
            self._register_filter(name, getattr(self._infrahub_filters, name))

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
            template = self._get_string_based_template() if self.is_string_based else self._get_file_based_template()
        except jinja2.TemplateSyntaxError as exc:
            self._raise_template_syntax_error(error=exc)
        except jinja2.TemplateNotFound as exc:
            raise JinjaTemplateNotFoundError(message=exc.message, filename=str(exc.name)) from exc

        return template

    def get_variables(self) -> list[str]:
        env = self.get_environment()

        template_source = self._template
        if self.is_file_based and env.loader:
            template_source = env.loader.get_source(env, self._template)[0]

        try:
            template = env.parse(template_source)
        except jinja2.TemplateSyntaxError as exc:
            self._raise_template_syntax_error(error=exc)

        return sorted(meta.find_undeclared_variables(template))

    def validate(self, restricted: bool = True, context: ExecutionContext | None = None) -> None:
        effective_context = (
            context if context is not None else ExecutionContext.CORE if restricted else ExecutionContext.LOCAL
        )

        allowed_list = [fd.name for fd in AVAILABLE_FILTERS if fd.allowed_contexts & effective_context]
        # User-supplied filters are always allowed (but not SDK-injected ones)
        for user_filter in self._user_filter_names:
            if user_filter not in allowed_list:
                allowed_list.append(user_filter)

        env = self.get_environment()
        template_source = self._template
        if self.is_file_based and env.loader:
            template_source = env.loader.get_source(env, self._template)[0]

        try:
            template = env.parse(template_source)
        except jinja2.TemplateSyntaxError as exc:
            self._raise_template_syntax_error(error=exc)

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
            raise JinjaTemplateNotFoundError(
                message=exc.message, filename=str(exc.name), base_template=template.name
            ) from exc
        except jinja2.TemplateSyntaxError as exc:
            self._raise_template_syntax_error(error=exc)
        except jinja2.UndefinedError as exc:
            traceback = Traceback(show_locals=False)
            errors = _identify_faulty_jinja_code(traceback=traceback)
            raise JinjaTemplateUndefinedError(message=exc.message, errors=errors) from exc
        except Exception as exc:
            message = error_message if (error_message := getattr(exc, "message", None)) else str(exc)
            raise JinjaTemplateError(message=message or "Unknown template error") from exc

        return output

    def _get_string_based_environment(self) -> jinja2.Environment:
        env = SandboxedEnvironment(enable_async=True, undefined=jinja2.StrictUndefined)
        self._set_filters(env=env)
        self._environment = env
        return self._environment

    def _get_file_based_environment(self) -> jinja2.Environment:
        template_loader = jinja2.FileSystemLoader(searchpath=str(self._template_directory))
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
        env.filters.update(self._filters)

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
        if error.filename and self._template_directory:
            filename = error.filename
            if error.filename.startswith(str(self._template_directory)):
                filename = error.filename[len(str(self._template_directory)) :]

        raise JinjaTemplateSyntaxError(message=error.message, filename=filename, lineno=error.lineno)


def _identify_faulty_jinja_code(traceback: Traceback, nbr_context_lines: int = 3) -> list[UndefinedJinja2Error]:
    """This function identifies the faulty Jinja2 code and beautify it to provide meaningful information to the user.

    We use the rich's Traceback to parse the complete stack trace and extract Frames for each exception found in the trace.
    """
    response = []

    # Extract only the Jinja related exception
    for frame in [frame for frame in traceback.trace.stacks[0].frames if not frame.filename.endswith(".py")]:
        code = "".join(linecache.getlines(frame.filename))
        lexer_name = "text" if frame.filename == "<template>" else Traceback._guess_lexer(frame.filename, code)
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
