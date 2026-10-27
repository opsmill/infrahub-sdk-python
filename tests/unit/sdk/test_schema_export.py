from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk.exceptions import BranchNotFoundError, VersionNotSupportedError
from infrahub_sdk.schema import InfrahubSchemaWrite, SchemaExportMode

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from tests.unit.sdk.conftest import BothClients

client_types = ["standard", "sync"]

EXPORTED_SCHEMA: dict[str, Any] = {
    "version": "1.0",
    "infrahub_version": "1.13.0",
    "generics": [{"name": "Interface", "namespace": "Infra", "attributes": [{"name": "name", "kind": "Text"}]}],
    "nodes": [
        {
            "name": "Device",
            "namespace": "Infra",
            "attributes": [{"name": "hostname", "kind": "Text", "unique": True}],
        }
    ],
}


async def _export(
    clients: BothClients,
    client_type: str,
    branch: str | None = None,
    namespaces: list[str] | None = None,
    mode: SchemaExportMode = "brief",
) -> InfrahubSchemaWrite:
    if client_type == "standard":
        return await clients.standard.schema.export(branch=branch, namespaces=namespaces, mode=mode)
    return clients.sync.schema.export(branch=branch, namespaces=namespaces, mode=mode)


@dataclass
class ExportRequestCase:
    name: str
    url: str
    branch: str | None = None
    namespaces: list[str] | None = None
    mode: SchemaExportMode = "brief"


EXPORT_REQUEST_CASES = [
    ExportRequestCase(name="defaults", url="http://mock/api/schema/export?branch=main&mode=brief"),
    ExportRequestCase(
        name="branch-namespaces-and-mode",
        url="http://mock/api/schema/export?branch=feature&mode=full&namespaces=Infra&namespaces=Dcim",
        branch="feature",
        namespaces=["Infra", "Dcim"],
        mode="full",
    ),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in EXPORT_REQUEST_CASES])
async def test_export_returns_the_document_served_by_infrahub(
    httpx_mock: HTTPXMock, clients: BothClients, client_type: str, case: ExportRequestCase
) -> None:
    httpx_mock.add_response(method="GET", url=case.url, json=EXPORTED_SCHEMA)

    exported = await _export(
        clients=clients, client_type=client_type, branch=case.branch, namespaces=case.namespaces, mode=case.mode
    )

    assert isinstance(exported, InfrahubSchemaWrite)
    assert exported.model_dump(mode="json", exclude_unset=True) == EXPORTED_SCHEMA


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("status_code", [404, 422])
async def test_export_against_a_server_without_the_endpoint(
    httpx_mock: HTTPXMock, clients: BothClients, client_type: str, status_code: int
) -> None:
    httpx_mock.add_response(
        method="GET",
        url="http://mock/api/schema/export?branch=main&mode=brief",
        status_code=status_code,
        json={"data": None, "errors": [{"message": "Unable to find the schema export in the database."}]},
    )

    with pytest.raises(VersionNotSupportedError, match=r"^Schema export requires Infrahub 1\.13\.0 or later\.$"):
        await _export(clients=clients, client_type=client_type)


@pytest.mark.parametrize("client_type", client_types)
async def test_export_of_an_unknown_branch(httpx_mock: HTTPXMock, clients: BothClients, client_type: str) -> None:
    httpx_mock.add_response(
        method="GET", url="http://mock/api/schema/export?branch=missing&mode=brief", status_code=400, json={}
    )

    with pytest.raises(BranchNotFoundError, match=r"The requested branch was not found on the server \[missing\]"):
        await _export(clients=clients, client_type=client_type, branch="missing")
