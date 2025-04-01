from __future__ import annotations

import asyncio
import difflib
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jinja2
import ujson
from httpx import HTTPStatusError

from ...template import Jinja2Template
from ...template.exceptions import JinjaTemplateError
from ..exceptions import OutputMatchError
from ..models import InfrahubInputOutputTest, InfrahubTestExpectedResult
from .base import InfrahubItem

if TYPE_CHECKING:
    from pytest import ExceptionInfo


class InfrahubJinja2Item(InfrahubItem):
    def _get_jinja2(self) -> Jinja2Template:
        return Jinja2Template(
            template=Path(self.resource_config.template_path),  # type: ignore[attr-defined]
            template_directory=Path(self.session.infrahub_config_path.parent),  # type: ignore[attr-defined]
        )

    def get_jinja2_environment(self) -> jinja2.Environment:
        jinja2_template = self._get_jinja2()
        return jinja2_template.get_environment()

    def get_jinja2_template(self) -> jinja2.Template:
        jinja2_template = self._get_jinja2()
        return jinja2_template.get_template()

    def render_jinja2_template(self, variables: dict[str, Any]) -> str | None:
        jinja2_template = self._get_jinja2()

        try:
            return asyncio.run(jinja2_template.render(variables=variables))
        except JinjaTemplateError as exc:
            if self.test.expect == InfrahubTestExpectedResult.PASS:
                raise exc
            return None

    def get_result_differences(self, computed: Any) -> str | None:
        if not isinstance(self.test.spec, InfrahubInputOutputTest) or not self.test.spec.output or computed is None:
            return None

        differences = difflib.unified_diff(
            self.test.spec.get_output_data().splitlines(),
            computed.splitlines(),
            fromfile="expected",
            tofile="rendered",
            lineterm="",
        )
        return "\n".join(differences)

    def repr_failure(self, excinfo: ExceptionInfo, style: str | None = None) -> str:
        if isinstance(excinfo.value, HTTPStatusError):
            try:
                response_content = ujson.dumps(excinfo.value.response.json(), indent=4, sort_keys=True)
            except ujson.JSONDecodeError:
                response_content = excinfo.value.response.text
            return "\n".join(
                [
                    f"Failed {excinfo.value.request.method} on {excinfo.value.request.url}",
                    f"Status code: {excinfo.value.response.status_code}",
                    f"Response: {response_content}",
                ]
            )

        if isinstance(excinfo.value, jinja2.TemplateSyntaxError):
            return "\n".join(["Syntax error detected in the template", excinfo.value.message or ""])

        if isinstance(excinfo.value, OutputMatchError):
            return f"{excinfo.value.message}\n{excinfo.value.differences}"

        return super().repr_failure(excinfo, style=style)


class InfrahubJinja2TransformSmokeItem(InfrahubJinja2Item):
    def runtest(self) -> None:
        file_path: Path = self.session.infrahub_config_path.parent / self.resource_config.template_path  # type: ignore[attr-defined]
        self.get_jinja2_environment().parse(file_path.read_text(), filename=file_path.name)


class InfrahubJinja2TransformUnitRenderItem(InfrahubJinja2Item):
    def runtest(self) -> None:
        computed = self.render_jinja2_template(self.test.spec.get_input_data())  # type: ignore[union-attr]
        differences = self.get_result_differences(computed)

        if computed is not None and differences and self.test.expect == InfrahubTestExpectedResult.PASS:
            raise OutputMatchError(name=self.name, differences=differences)

    def repr_failure(self, excinfo: ExceptionInfo, style: str | None = None) -> str:
        if isinstance(excinfo.value, (JinjaTemplateError)):
            return str(excinfo.value.message)

        return super().repr_failure(excinfo, style=style)


class InfrahubJinja2TransformIntegrationItem(InfrahubJinja2Item):
    def runtest(self) -> None:
        graphql_result = self.session.infrahub_client.query_gql_query(  # type: ignore[attr-defined]
            self.resource_config.query,  # type: ignore[attr-defined]
            variables=self.test.spec.get_variables_data(),  # type: ignore[union-attr]
        )
        computed = self.render_jinja2_template(graphql_result)
        differences = self.get_result_differences(computed)

        if computed is not None and differences and self.test.expect == InfrahubTestExpectedResult.PASS:
            raise OutputMatchError(name=self.name, differences=differences)
