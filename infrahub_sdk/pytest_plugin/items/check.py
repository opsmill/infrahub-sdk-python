from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

import ujson
from httpx import HTTPStatusError

from ..exceptions import CheckDefinitionError, CheckResultError
from ..models import InfrahubTestExpectedResult
from .base import InfrahubItem

if TYPE_CHECKING:
    from pytest import ExceptionInfo

    from ...checks import InfrahubCheck
    from ...schema.repository import InfrahubRepositoryConfigElement
    from ..models import InfrahubTest


class InfrahubCheckItem(InfrahubItem):
    def __init__(
        self,
        *args: Any,
        resource_name: str,
        resource_config: InfrahubRepositoryConfigElement,
        test: InfrahubTest,
        **kwargs: dict[str, Any],
    ):
        super().__init__(*args, resource_name=resource_name, resource_config=resource_config, test=test, **kwargs)

        self.check_instance: InfrahubCheck

    def instantiate_check(self) -> None:
        relative_path = (
            str(self.resource_config.file_path.parent) if self.resource_config.file_path.parent != Path() else None  # type: ignore[attr-defined]
        )

        check_class = self.resource_config.load_class(  # type: ignore[attr-defined]
            import_root=self.repository_base, relative_path=relative_path
        )
        self.check_instance = check_class()

    def run_check(self, variables: dict[str, Any]) -> Any:
        self.instantiate_check()
        return asyncio.run(self.check_instance.run(data=variables))

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

        return super().repr_failure(excinfo, style=style)


class InfrahubCheckSmokeItem(InfrahubCheckItem):
    def runtest(self) -> None:
        self.instantiate_check()

        for attr in ("query", "validate"):
            if not hasattr(self.check_instance, attr):
                raise CheckDefinitionError(f"Missing attribute or function {attr}")


class InfrahubCheckUnitProcessItem(InfrahubCheckItem):
    def runtest(self) -> None:
        input_data = self.test.spec.get_input_data()  # type: ignore[union-attr]
        passed = self.run_check(input_data)

        if not passed and self.test.expect == InfrahubTestExpectedResult.PASS:
            raise CheckResultError(name=self.name)


class InfrahubCheckIntegrationItem(InfrahubCheckItem):
    def runtest(self) -> None:
        input_data = self.session.infrahub_client.query_gql_query(  # type: ignore[attr-defined]
            self.check_instance.query,
            variables=self.test.spec.get_variables_data(),  # type: ignore[union-attr]
        )
        passed = self.run_check(input_data)

        if not passed and self.test.expect == InfrahubTestExpectedResult.PASS:
            raise CheckResultError(name=self.name)
