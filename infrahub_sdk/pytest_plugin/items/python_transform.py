from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

import ujson
from httpx import HTTPStatusError

from ..exceptions import OutputMatchError, PythonTransformDefinitionError
from ..models import InfrahubTestExpectedResult
from .base import InfrahubItem

if TYPE_CHECKING:
    from pytest import ExceptionInfo

    from ...schema.repository import InfrahubRepositoryConfigElement
    from ...transforms import InfrahubTransform
    from ..models import InfrahubTest


class InfrahubPythonTransformItem(InfrahubItem):
    def __init__(
        self,
        *args: Any,
        resource_name: str,
        resource_config: InfrahubRepositoryConfigElement,
        test: InfrahubTest,
        **kwargs: dict[str, Any],
    ):
        super().__init__(*args, resource_name=resource_name, resource_config=resource_config, test=test, **kwargs)

        self.transform_instance: InfrahubTransform

    def instantiate_transform(self) -> None:
        relative_path = (
            str(self.resource_config.file_path.parent) if self.resource_config.file_path.parent != Path() else None  # type: ignore[attr-defined]
        )
        transform_class = self.resource_config.load_class(  # type: ignore[attr-defined]
            import_root=self.repository_base, relative_path=relative_path
        )
        client = self.session.infrahub_client  # type: ignore[attr-defined]
        # TODO: Look into seeing how a transform class may use the branch, but set as a empty string for the time being to keep current behaviour
        self.transform_instance = transform_class(branch="", client=client)

    def run_transform(self, variables: dict[str, Any]) -> Any:
        self.instantiate_transform()
        return asyncio.run(self.transform_instance.run(data=variables))

    def repr_failure(self, excinfo: ExceptionInfo, style: str | None = None) -> str:
        if isinstance(excinfo.value, HTTPStatusError):
            try:
                response_content = ujson.dumps(excinfo.value.response.json(), indent=4)
            except ujson.JSONDecodeError:
                response_content = excinfo.value.response.text
            return "\n".join(
                [
                    f"Failed {excinfo.value.request.method} on {excinfo.value.request.url}",
                    f"Status code: {excinfo.value.response.status_code}",
                    f"Response: {response_content}",
                ]
            )

        if isinstance(excinfo.value, OutputMatchError):
            return f"{excinfo.value.message}\n{excinfo.value.differences}"

        return super().repr_failure(excinfo, style=style)


class InfrahubPythonTransformSmokeItem(InfrahubPythonTransformItem):
    def runtest(self) -> None:
        self.instantiate_transform()

        for attr in ("query", "transform"):
            if not hasattr(self.transform_instance, attr):
                raise PythonTransformDefinitionError(f"Missing attribute or function {attr}")


class InfrahubPythonTransformUnitProcessItem(InfrahubPythonTransformItem):
    def runtest(self) -> None:
        input_data = self.test.spec.get_input_data()  # type: ignore[union-attr]
        computed = self.run_transform(input_data)
        differences = self.get_result_differences(computed)

        if computed is not None and differences and self.test.expect == InfrahubTestExpectedResult.PASS:
            raise OutputMatchError(name=self.name, message=differences)


class InfrahubPythonTransformIntegrationItem(InfrahubPythonTransformItem):
    def runtest(self) -> None:
        input_data = self.session.infrahub_client.query_gql_query(  # type: ignore[attr-defined]
            self.transform_instance.query,
            variables=self.test.spec.get_variables_data(),  # type: ignore[union-attr]
        )
        computed = self.run_transform(input_data)
        differences = self.get_result_differences(computed)

        if computed is not None and differences and self.test.expect == InfrahubTestExpectedResult.PASS:
            raise OutputMatchError(name=self.name, message=differences)
