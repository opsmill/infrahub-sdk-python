from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from infrahub_sdk import InfrahubClient
from infrahub_sdk.checks import InfrahubCheck

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

pytestmark = pytest.mark.httpx_mock(can_send_already_matched_responses=True)


async def test_class_init(tmp_path: Path) -> None:
    class IFCheckNoQuery(InfrahubCheck):
        pass

    class IFCheckWithName(InfrahubCheck):
        name = "my_check"
        query = "my_query"

    class IFCheckNoName(InfrahubCheck):
        query = "my_query"

    with pytest.raises(ValueError) as exc:
        check = IFCheckNoQuery()

    assert "A query must be provided" in str(exc.value)

    check = IFCheckWithName()
    assert check.name == "my_check"
    assert check.root_directory is not None

    check = IFCheckNoName()
    assert check.name == "IFCheckNoName"

    check = IFCheckWithName(root_directory=str(tmp_path))
    assert check.name == "my_check"
    assert check.root_directory == str(tmp_path)


async def test_async_init(client: InfrahubClient) -> None:
    class IFCheck(InfrahubCheck):
        query = "my_query"

    check = await IFCheck.init()
    assert isinstance(check.client, InfrahubClient)


async def test_validate_sync_async(mock_gql_query_my_query: HTTPXMock) -> None:
    class IFCheckAsync(InfrahubCheck):
        query = "my_query"

        async def validate(self, data: dict) -> None:
            self.log_error("Not valid")

    class IFCheckSync(InfrahubCheck):
        query = "my_query"

        def validate(self, data: dict) -> None:
            self.log_error("Not valid")

    check = await IFCheckAsync.init(branch="main")
    await check.run()

    assert check.passed is False

    check = await IFCheckSync.init(branch="main")
    await check.run()

    assert check.passed is False
