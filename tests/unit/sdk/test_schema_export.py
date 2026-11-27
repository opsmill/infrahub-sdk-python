from __future__ import annotations

import copy
import pickle  # noqa: S403 - round-tripping our own exception, no untrusted data involved
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk.exceptions import (
    ApiError,
    AuthenticationError,
    BranchNotFoundError,
    InvalidResponseError,
    SchemaNamespaceNotFoundError,
    URLNotFoundError,
    VersionNotSupportedError,
)
from infrahub_sdk.schema import (
    SCHEMA_EXPORT_MIN_INFRAHUB_VERSION,
    SchemaExportDocument,
    SchemaExportMode,
    split_by_namespace,
)

if TYPE_CHECKING:
    from collections.abc import Callable

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
    documents = split_by_namespace(EXPORT_RESPONSE)

    assert list(documents) == ["Network", "Location"]
    assert documents["Network"] == {
        "version": "1.0",
        "infrahub_version": "1.13.0",
        "generics": EXPORT_RESPONSE["generics"],
        "nodes": [EXPORT_RESPONSE["nodes"][0], EXPORT_RESPONSE["nodes"][2]],
    }
    assert documents["Location"] == {
        "version": "1.0",
        "infrahub_version": "1.13.0",
        "nodes": [EXPORT_RESPONSE["nodes"][1]],
    }


def test_split_by_namespace_copies_every_other_top_level_field() -> None:
    documents = split_by_namespace({**EXPORT_RESPONSE, "unknown_document_setting": "kept"})

    assert [namespace_document["unknown_document_setting"] for namespace_document in documents.values()] == [
        "kept",
        "kept",
    ]


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


NAMESPACE_EXPORT_URL = "http://mock/api/schema/export?branch=main&namespaces=Locaton&namespaces=Core&mode=BRIEF"
LOCATON_ERROR = {
    "message": "The namespace 'Locaton' does not exist on the branch 'main'",
    "extensions": {"namespace": "Locaton", "code": 404},
}
CORE_ERROR = {
    "message": "The namespace 'Core' is reserved for Infrahub and cannot be exported",
    "extensions": {"namespace": "Core", "code": 404},
}
UNKNOWN_ENDPOINT_ERROR = {
    "message": "The requested endpoint /api/schema/export does not exist",
    "extensions": {"code": 404},
}


@pytest.mark.parametrize("client_type", client_types)
async def test_export_names_each_namespace_the_server_cannot_export(
    httpx_mock: HTTPXMock, clients: BothClients, client_type: str
) -> None:
    httpx_mock.add_response(
        method="GET",
        url=NAMESPACE_EXPORT_URL,
        status_code=404,
        json={"data": None, "errors": [LOCATON_ERROR, CORE_ERROR]},
    )

    with pytest.raises(
        SchemaNamespaceNotFoundError,
        match=(
            r"^The namespace 'Locaton' does not exist on the branch 'main'; "
            r"The namespace 'Core' is reserved for Infrahub and cannot be exported$"
        ),
    ) as exc_info:
        await _export(clients, client_type, branch="main", namespaces=["Locaton", "Core"])

    assert exc_info.value.namespaces == ["Locaton", "Core"]
    assert exc_info.value.messages == [LOCATON_ERROR["message"], CORE_ERROR["message"]]
    assert exc_info.value.http_status == 404


@dataclass
class NotFoundCase:
    name: str
    body: dict[str, Any]


NOT_FOUND_CASES = [
    NotFoundCase(name="fastapi-default", body={"detail": "Not Found"}),
    NotFoundCase(name="infrahub-unknown-endpoint", body={"data": None, "errors": [UNKNOWN_ENDPOINT_ERROR]}),
    NotFoundCase(
        name="one-error-without-namespace", body={"data": None, "errors": [LOCATON_ERROR, UNKNOWN_ENDPOINT_ERROR]}
    ),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in NOT_FOUND_CASES])
async def test_export_reports_a_404_that_names_no_namespace_as_an_unknown_url(
    httpx_mock: HTTPXMock, clients: BothClients, client_type: str, case: NotFoundCase
) -> None:
    httpx_mock.add_response(method="GET", url=NAMESPACE_EXPORT_URL, status_code=404, json=case.body)

    with pytest.raises(URLNotFoundError, match=f"^`{re.escape(NAMESPACE_EXPORT_URL)}` not found.$"):
        await _export(clients, client_type, branch="main", namespaces=["Locaton", "Core"])


@pytest.mark.parametrize("client_type", client_types)
async def test_export_names_a_namespace_whose_error_has_no_message(
    httpx_mock: HTTPXMock, clients: BothClients, client_type: str
) -> None:
    httpx_mock.add_response(
        method="GET",
        url=NAMESPACE_EXPORT_URL,
        status_code=404,
        json={"data": None, "errors": [{"message": None, "extensions": {"namespace": "Locaton", "code": 404}}]},
    )

    with pytest.raises(SchemaNamespaceNotFoundError, match=r"^The namespace 'Locaton' cannot be exported$"):
        await _export(clients, client_type, branch="main", namespaces=["Locaton", "Core"])


@pytest.mark.parametrize("client_type", client_types)
async def test_export_of_an_unknown_branch_raises_branch_not_found(
    httpx_mock: HTTPXMock, clients: BothClients, client_type: str
) -> None:
    httpx_mock.add_response(
        method="GET",
        url="http://mock/api/schema/export?branch=nope&mode=BRIEF",
        status_code=400,
        json={"data": None, "errors": [{"message": "Branch: nope not found.", "extensions": {"code": 400}}]},
    )

    with pytest.raises(BranchNotFoundError, match=r"^The requested branch was not found on the server \[nope\]$"):
        await _export(clients, client_type, branch="nope")


@pytest.mark.parametrize("client_type", client_types)
async def test_export_with_a_value_the_sdk_cannot_read_raises_invalid_response(
    httpx_mock: HTTPXMock, clients: BothClients, client_type: str
) -> None:
    response = {
        **EXPORT_RESPONSE,
        "generics": [],
        "nodes": [{"name": "Device", "namespace": "Network", "attributes": [{"name": "size", "kind": "Decimal"}]}],
    }
    httpx_mock.add_response(method="GET", url="http://mock/api/schema/export?branch=main&mode=BRIEF", json=response)

    with pytest.raises(
        InvalidResponseError,
        match=r"^The schema export from http://mock/api/schema/export\?branch=main&mode=BRIEF holds a value this "
        r"version of the SDK cannot read; use an SDK version that matches the Infrahub server\. ",
    ):
        await _export(clients, client_type, branch="main")


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("status_code", [401, 403])
async def test_export_rejected_for_the_credentials_raises_authentication_error(
    httpx_mock: HTTPXMock, clients: BothClients, client_type: str, status_code: int
) -> None:
    httpx_mock.add_response(
        method="GET",
        url="http://mock/api/schema/export?branch=main&mode=BRIEF",
        status_code=status_code,
        json={"data": None, "errors": [{"message": "Authentication is required", "extensions": {"code": status_code}}]},
    )

    with pytest.raises(AuthenticationError, match=r"^Authentication is required$"):
        await _export(clients, client_type, branch="main")


SERIALISATION_ROUND_TRIPS = {
    "pickle": lambda exc: pickle.loads(pickle.dumps(exc)),  # noqa: S301
    "deepcopy": copy.deepcopy,
    "copy": copy.copy,
}


@pytest.mark.parametrize("round_trip", [pytest.param(fn, id=name) for name, fn in SERIALISATION_ROUND_TRIPS.items()])
def test_export_errors_survive_serialisation(round_trip: Callable[[Exception], Exception]) -> None:
    namespace_error = SchemaNamespaceNotFoundError(namespaces=["Locaton"], messages=[LOCATON_ERROR["message"]])
    namespace_error.http_status = 404
    version_error = VersionNotSupportedError(feature="The schema export", required_version="1.13.0")

    restored_namespace_error = round_trip(namespace_error)
    restored_version_error = round_trip(version_error)

    assert isinstance(restored_namespace_error, SchemaNamespaceNotFoundError)
    assert (
        restored_namespace_error.namespaces,
        restored_namespace_error.messages,
        restored_namespace_error.http_status,
        str(restored_namespace_error),
    ) == (["Locaton"], [LOCATON_ERROR["message"]], 404, LOCATON_ERROR["message"])
    assert isinstance(restored_version_error, VersionNotSupportedError)
    assert (restored_version_error.required_version, str(restored_version_error)) == (
        "1.13.0",
        "The schema export requires Infrahub 1.13.0 or later.",
    )
