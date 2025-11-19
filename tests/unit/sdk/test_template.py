from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from rich.syntax import Syntax
from rich.traceback import Frame

from infrahub_sdk.template import Jinja2Template
from infrahub_sdk.template.exceptions import (
    JinjaTemplateError,
    JinjaTemplateNotFoundError,
    JinjaTemplateOperationViolationError,
    JinjaTemplateSyntaxError,
    JinjaTemplateUndefinedError,
)
from infrahub_sdk.template.filters import (
    BUILTIN_FILTERS,
    NETUTILS_FILTERS,
    FilterDefinition,
)
from infrahub_sdk.template.models import UndefinedJinja2Error

CURRENT_DIRECTORY = Path(__file__).parent
TEMPLATE_DIRECTORY = CURRENT_DIRECTORY / "test_data/templates"


@dataclass
class JinjaTestCase:
    name: str
    template: str
    variables: dict[str, Any]
    expected: str
    expected_variables: list[str] = field(default_factory=list)


@dataclass
class JinjaTestCaseFailing:
    name: str
    template: str
    variables: dict[str, Any]
    error: JinjaTemplateError


SUCCESSFUL_STRING_TEST_CASES = [
    JinjaTestCase(
        name="hello-world",
        template="Hello {{ name }}",
        variables={"name": "Infrahub"},
        expected="Hello Infrahub",
        expected_variables=["name"],
    ),
    JinjaTestCase(
        name="hello-if-defined",
        template="Hello {% if name is undefined %}stranger{% else %}{{name}}{% endif %}",
        variables={"name": "OpsMill"},
        expected="Hello OpsMill",
        expected_variables=["name"],
    ),
    JinjaTestCase(
        name="hello-if-undefined",
        template="Hello {% if name is undefined %}stranger{% else %}{{name}}{% endif %}",
        variables={},
        expected="Hello stranger",
        expected_variables=["name"],
    ),
    JinjaTestCase(
        name="netutils-ip-addition",
        template="IP={{ ip_address|ip_addition(200) }}",
        variables={"ip_address": "192.168.12.15"},
        expected="IP=192.168.12.215",
        expected_variables=["ip_address"],
    ),
]


@pytest.mark.parametrize(
    "test_case",
    [pytest.param(tc, id=tc.name) for tc in SUCCESSFUL_STRING_TEST_CASES],
)
async def test_render_string(test_case: JinjaTestCase) -> None:
    jinja = Jinja2Template(template=test_case.template)
    assert test_case.expected == await jinja.render(variables=test_case.variables)
    assert test_case.expected_variables == jinja.get_variables()


SUCCESSFUL_FILE_TEST_CASES = [
    JinjaTestCase(
        name="hello-world",
        template="hello-world.j2",
        variables={"name": "Infrahub"},
        expected="Hello Infrahub",
        expected_variables=["name"],
    ),
    JinjaTestCase(
        name="netutils-convert-address",
        template="ip_report.j2",
        variables={"address": "192.168.18.40/255.255.255.0"},
        expected="IP Address: 192.168.18.40/24",
        expected_variables=["address"],
    ),
]


@pytest.mark.parametrize(
    "test_case",
    [pytest.param(tc, id=tc.name) for tc in SUCCESSFUL_FILE_TEST_CASES],
)
async def test_render_template_from_file(test_case: JinjaTestCase) -> None:
    jinja = Jinja2Template(template=Path(test_case.template), template_directory=TEMPLATE_DIRECTORY)
    assert test_case.expected == await jinja.render(variables=test_case.variables)
    assert test_case.expected_variables == jinja.get_variables()
    assert jinja.get_template()


FAILING_STRING_TEST_CASES = [
    JinjaTestCaseFailing(
        name="missing-closing-end-if",
        template="Hello {% if name is undefined %}stranger{% else %}{{name}}{% endif",
        variables={},
        error=JinjaTemplateSyntaxError(
            message="unexpected end of template, expected 'end of statement block'.",
            lineno=1,
        ),
    ),
    JinjaTestCaseFailing(
        name="fail-on-line-2",
        template="Hello \n{{ name }",
        variables={},
        error=JinjaTemplateSyntaxError(
            message="unexpected '}'",
            lineno=2,
        ),
    ),
    JinjaTestCaseFailing(
        name="nested-undefined",
        template="Hello {{ person.firstname }}",
        variables={"person": {"lastname": "Rogers"}},
        error=JinjaTemplateUndefinedError(
            message="'dict object' has no attribute 'firstname'",
            errors=[
                UndefinedJinja2Error(
                    frame=Frame(filename="<template>", lineno=1, name="top-level template code"),
                    syntax=Syntax(code="", lexer="text"),
                )
            ],
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    [pytest.param(tc, id=tc.name) for tc in FAILING_STRING_TEST_CASES],
)
async def test_render_string_errors(test_case: JinjaTestCaseFailing) -> None:
    jinja = Jinja2Template(template=test_case.template, template_directory=TEMPLATE_DIRECTORY)
    with pytest.raises(test_case.error.__class__) as exc:
        await jinja.render(variables=test_case.variables)

    _compare_errors(expected=test_case.error, received=exc.value)


FAILING_FILE_TEST_CASES = [
    JinjaTestCaseFailing(
        name="missing-initial-file",
        template="missing.html",
        variables={},
        error=JinjaTemplateNotFoundError(
            message=f"'missing.html' not found in search path: '{TEMPLATE_DIRECTORY}'",
            filename="missing.html",
        ),
    ),
    JinjaTestCaseFailing(
        name="broken-template",
        template="index.html",
        variables={},
        error=JinjaTemplateSyntaxError(
            message="unexpected '}'",
            filename="/index.html",
            lineno=6,
        ),
    ),
    JinjaTestCaseFailing(
        name="secondary-import-broken",
        template="main.j2",
        variables={},
        error=JinjaTemplateSyntaxError(
            message="unexpected '}'",
            filename="/broken_on_line6.j2",
            lineno=6,
        ),
    ),
    JinjaTestCaseFailing(
        name="secondary-import-missing",
        template="imports-missing-file.html",
        variables={},
        error=JinjaTemplateNotFoundError(
            message=f"'i-do-not-exist.html' not found in search path: '{TEMPLATE_DIRECTORY}'",
            filename="i-do-not-exist.html",
            base_template="imports-missing-file.html",
        ),
    ),
    JinjaTestCaseFailing(
        name="invalid-variable-input",
        template="report.html",
        variables={
            "servers": [
                {"name": "server1", "ip": {"primary": "172.18.12.1"}},
                {"name": "server1"},
            ]
        },
        error=JinjaTemplateUndefinedError(
            message="'dict object' has no attribute 'ip'",
            errors=[
                UndefinedJinja2Error(
                    frame=Frame(
                        filename=f"{TEMPLATE_DIRECTORY}/report.html",
                        lineno=5,
                        name="top-level template code",
                    ),
                    syntax=Syntax(
                        code="<html>\n<body>\n<ul>\n{% for server in servers %}\n    <li>{{server.name}}: {{ server.ip.primary }}</li>\n{% endfor %}\n</ul>\n\n</body>\n\n</html>\n",  # noqa: E501
                        lexer="",
                    ),
                )
            ],
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    [pytest.param(tc, id=tc.name) for tc in FAILING_FILE_TEST_CASES],
)
async def test_manage_file_based_errors(test_case: JinjaTestCaseFailing) -> None:
    jinja = Jinja2Template(template=Path(test_case.template), template_directory=TEMPLATE_DIRECTORY)
    with pytest.raises(test_case.error.__class__) as exc:
        await jinja.render(variables=test_case.variables)

    _compare_errors(expected=test_case.error, received=exc.value)


async def test_manage_unhandled_error() -> None:
    jinja = Jinja2Template(
        template="Hello {{ number | divide_by_zero }}",
        filters={"divide_by_zero": _divide_by_zero},
    )
    with pytest.raises(JinjaTemplateError) as exc:
        await jinja.render(variables={"number": 1})

    assert exc.value.message == "division by zero"


async def test_validate_filter() -> None:
    jinja = Jinja2Template(template="{{ network | get_all_host }}")
    jinja.validate(restricted=False)
    with pytest.raises(JinjaTemplateOperationViolationError) as exc:
        jinja.validate(restricted=True)

    assert exc.value.message == "The 'get_all_host' filter isn't allowed to be used"


async def test_validate_operation() -> None:
    jinja = Jinja2Template(template="Hello {% include 'very-forbidden.j2' %}")
    with pytest.raises(JinjaTemplateOperationViolationError) as exc:
        jinja.validate(restricted=True)

    assert (
        exc.value.message == "These operations are forbidden for string based templates: ['Call', 'Import', 'Include']"
    )


@pytest.mark.parametrize(
    "filter_collection",
    [
        pytest.param(BUILTIN_FILTERS, id="builtin-filters"),
        pytest.param(NETUTILS_FILTERS, id="netutils-filters"),
    ],
)
def test_validate_filter_sorting(filter_collection: list[FilterDefinition]) -> None:
    """Test to validate that the filter names are in alphabetical order, for the docs and general sanity."""
    names = [filter_definition.name for filter_definition in filter_collection]
    assert names == sorted(names)


def _divide_by_zero(number: int) -> float:
    return number / 0


def _compare_errors(expected: JinjaTemplateError, received: JinjaTemplateError) -> None:
    if isinstance(expected, JinjaTemplateNotFoundError) and isinstance(received, JinjaTemplateNotFoundError):
        assert expected.message == received.message
        assert expected.filename == received.filename
        assert expected.base_template == received.base_template
    elif isinstance(expected, JinjaTemplateSyntaxError) and isinstance(received, JinjaTemplateSyntaxError):
        assert expected.message == received.message
        assert expected.filename == received.filename
        assert expected.lineno == received.lineno
    elif isinstance(expected, JinjaTemplateUndefinedError) and isinstance(received, JinjaTemplateUndefinedError):
        assert expected.message == received.message
        assert len(expected.errors) == len(received.errors)
        for i in range(len(expected.errors)):
            assert expected.errors[i].frame.name == received.errors[i].frame.name
            assert expected.errors[i].frame.filename == received.errors[i].frame.filename
            assert expected.errors[i].frame.lineno == received.errors[i].frame.lineno
            assert expected.errors[i].syntax.code == received.errors[i].syntax.code
            assert expected.errors[i].syntax.lexer.__class__ == received.errors[i].syntax.lexer.__class__

    else:
        raise Exception("This should never happen")
