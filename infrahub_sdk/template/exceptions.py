from __future__ import annotations

from typing import TYPE_CHECKING

from infrahub_sdk.exceptions import Error

if TYPE_CHECKING:
    from .models import UndefinedJinja2Error


class JinjaTemplateError(Error):
    def __init__(self, message: str) -> None:
        self.message = message


class JinjaTemplateNotFoundError(JinjaTemplateError):
    def __init__(self, message: str | None, filename: str, base_template: str | None = None) -> None:
        self.message = message or "Template Not Found"
        self.filename = filename
        self.base_template = base_template


class JinjaTemplateSyntaxError(JinjaTemplateError):
    def __init__(self, message: str | None, lineno: int, filename: str | None = None) -> None:
        self.message = message or "Syntax Error"
        self.filename = filename
        self.lineno = lineno


class JinjaTemplateUndefinedError(JinjaTemplateError):
    def __init__(self, message: str | None, errors: list[UndefinedJinja2Error]) -> None:
        self.message = message or "Undefined Error"
        self.errors = errors


class JinjaTemplateOperationViolationError(JinjaTemplateError):
    def __init__(self, message: str | None = None) -> None:
        self.message = message or "Forbidden code found in the template"
