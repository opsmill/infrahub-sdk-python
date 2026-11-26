from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk.exceptions import ApiError, VersionNotSupportedError
from infrahub_sdk.schema import (
    SCHEMA_EXPORT_MIN_INFRAHUB_VERSION,
    SchemaExportDocument,
    SchemaExportMode,
    split_by_namespace,
)

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from tests.unit.sdk.conftest import BothClients

client_types = ["standard", "sync"]

EXPORT_RESPONSE: dict[str, Any] = {
    "version": "1.0",
    "infrahub_version": "1.13.0",
    "generics": [
        {
            "name": "Interface",
            "namespace": "Network",
            "human_friendly_id": ["device__name__value", "name__value"],
            "attributes": [{"name": "name", "kind": "Text"}],
            "relationships": [
                {
                    "name": "device",
                    "peer": "NetworkDevice",
                    "cardinality": "one",
                    "optional": False,
                    "kind": "Attribute",
                }
            ],
        },
    ],
    "nodes": [
        {
            "name": "Device",
            "namespace": "Network",
            "attributes": [{"name": "name", "kind": "Text", "unique": True}],
        },
        {"name": "Site", "namespace": "Location", "attributes": [{"name": "name", "kind": "Text"}]},
        {
            "name": "PhysicalInterface",
            "namespace": "Network",
            "inherit_from": ["NetworkInterface"],
            "attributes": [{"name": "speed", "kind": "Number"}],
        },
    ],
}

OLDER_SERVER_RESPONSE: dict[str, Any] = {
    "data": None,
    "errors": [{"message": "Unable to find the schema 'export' in the registry", "extensions": {"code": 422}}],
}


async def _export(
    clients: BothClients,
    client_type: str,
    branch: str,
    namespaces: list[str] | None = None,
    mode: SchemaExportMode = SchemaExportMode.BRIEF,
) -> SchemaExportDocument:
    if client_type == "standard":
        return await clients.standard.schema.export(branch=branch, namespaces=namespaces, mode=mode)
    return clients.sync.schema.export(branch=branch, namespaces=namespaces, mode=mode)


@pytest.mark.parametrize("client_type", client_types)
async def test_export_returns_the_endpoint_document(
    httpx_mock: HTTPXMock, clients: BothClients, client_type: str
) -> None:
    httpx_mock.add_response(
        method="GET", url="http://mock/api/schema/export?branch=main&mode=BRIEF", json=EXPORT_RESPONSE
    )

    document = await _export(clients, client_type, branch="main")

    assert isinstance(document, SchemaExportDocument)
    assert document.model_dump(mode="json", exclude_unset=True) == EXPORT_RESPONSE


@pytest.mark.parametrize("client_type", client_types)
async def test_export_sends_branch_namespaces_and_mode(
    httpx_mock: HTTPXMock, clients: BothClients, client_type: str
) -> None:
    httpx_mock.add_response(
        method="GET",
        url="http://mock/api/schema/export?branch=feature&namespaces=Network&namespaces=Location&mode=FULL",
        json=EXPORT_RESPONSE,
    )

    document = await _export(
        clients, client_type, branch="feature", namespaces=["Network", "Location"], mode=SchemaExportMode.FULL
    )

    assert document.infrahub_version == "1.13.0"


def test_split_by_namespace_keeps_versions_and_input_order() -> None:
    document = SchemaExportDocument.model_validate(EXPORT_RESPONSE)

    documents = split_by_namespace(document)

    assert list(documents) == ["Network", "Location"]
    for namespace_document in documents.values():
        assert isinstance(namespace_document, SchemaExportDocument)
        assert namespace_document.version == "1.0"
        assert namespace_document.infrahub_version == "1.13.0"
    assert [generic.name for generic in documents["Network"].generics] == ["Interface"]
    assert [node.name for node in documents["Network"].nodes] == ["Device", "PhysicalInterface"]
    assert [node.name for node in documents["Location"].nodes] == ["Site"]
    assert documents["Location"].model_dump(mode="json", exclude_unset=True) == {
        "version": "1.0",
        "infrahub_version": "1.13.0",
        "nodes": [EXPORT_RESPONSE["nodes"][1]],
    }


@pytest.mark.parametrize("client_type", client_types)
async def test_export_names_the_release_on_an_older_server(
    httpx_mock: HTTPXMock, clients: BothClients, client_type: str
) -> None:
    httpx_mock.add_response(
        method="GET",
        url="http://mock/api/schema/export?branch=main&mode=BRIEF",
        status_code=422,
        json=OLDER_SERVER_RESPONSE,
    )

    with pytest.raises(VersionNotSupportedError, match=re.escape(f"Infrahub {SCHEMA_EXPORT_MIN_INFRAHUB_VERSION}")):
        await _export(clients, client_type, branch="main")


@dataclass
class ErrorResponseCase:
    name: str
    status_code: int
    message: str


ERROR_RESPONSE_CASES = [
    ErrorResponseCase(
        name="422-other-kind", status_code=422, message="Unable to find the schema 'NetworkDevice' in the registry"
    ),
    ErrorResponseCase(
        name="422-other-message", status_code=422, message="Unable to find the schema export in the database."
    ),
    ErrorResponseCase(name="500", status_code=500, message="Internal server error"),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in ERROR_RESPONSE_CASES])
async def test_export_reports_other_errors_as_returned(
    httpx_mock: HTTPXMock, clients: BothClients, client_type: str, case: ErrorResponseCase
) -> None:
    httpx_mock.add_response(
        method="GET",
        url="http://mock/api/schema/export?branch=main&mode=BRIEF",
        status_code=case.status_code,
        json={"data": None, "errors": [{"message": case.message, "extensions": {"code": case.status_code}}]},
    )

    with pytest.raises(ApiError, match=re.escape(f"HTTP {case.status_code}: {case.message}")) as exc_info:
        await _export(clients, client_type, branch="main")

    assert not isinstance(exc_info.value, VersionNotSupportedError)
    assert SCHEMA_EXPORT_MIN_INFRAHUB_VERSION not in str(exc_info.value)
    assert exc_info.value.http_status == case.status_code
