import inspect
import ssl
from pathlib import Path

import pytest
from pytest_httpx import HTTPXMock

from infrahub_sdk import Config, InfrahubClient, InfrahubClientSync
from infrahub_sdk.exceptions import NodeNotFoundError
from infrahub_sdk.node import InfrahubNode, InfrahubNodeSync
from tests.unit.sdk.conftest import BothClients

pytestmark = pytest.mark.httpx_mock(can_send_already_matched_responses=True)

excluded_methods = ["request_context"]

async_client_methods = [
    method for method in dir(InfrahubClient) if not method.startswith("_") and method not in excluded_methods
]
sync_client_methods = [
    method for method in dir(InfrahubClientSync) if not method.startswith("_") and method not in excluded_methods
]

batch_client_types = [
    ("standard", False),
    ("standard", True),
    ("sync", False),
    ("sync", True),
]

client_types = ["standard", "sync"]

CURRENT_DIRECTORY = Path(__file__).parent


async def test_verify_config_caches_default_ssl_context(monkeypatch) -> None:
    contexts: list[tuple[str | None, object]] = []

    def fake_create_default_context(*args: object, **kwargs: object) -> object:
        context = object()
        contexts.append((kwargs.get("cafile"), context))
        return context

    monkeypatch.setattr("ssl.create_default_context", fake_create_default_context)

    client = InfrahubClient(config=Config(address="http://mock"))

    first = client.config.tls_context
    second = client.config.tls_context

    assert first is second
    assert contexts == [(None, first)]


async def test_verify_config_caches_tls_ca_file_context(monkeypatch) -> None:
    contexts: list[tuple[str | None, object]] = []

    def fake_create_default_context(*args: object, **kwargs: object) -> object:
        context = object()
        contexts.append((kwargs.get("cafile"), context))
        return context

    monkeypatch.setattr("ssl.create_default_context", fake_create_default_context)

    client = InfrahubClient(
        config=Config(address="http://mock", tls_ca_file=str(CURRENT_DIRECTORY / "test_data/path-1.pem"))
    )

    first = client.config.tls_context
    second = client.config.tls_context

    assert first is second
    assert contexts == [(str(CURRENT_DIRECTORY / "test_data/path-1.pem"), first)]

    client.config.tls_ca_file = str(CURRENT_DIRECTORY / "test_data/path-2.pem")
    third = client.config.tls_context

    assert third is first
    assert contexts == [
        (str(CURRENT_DIRECTORY / "test_data/path-1.pem"), first),
    ]


async def test_verify_config_respects_tls_insecure(monkeypatch) -> None:
    def fake_create_default_context(*args: object, **kwargs: object) -> object:
        raise AssertionError("create_default_context should not be called when TLS is insecure")

    monkeypatch.setattr("ssl.create_default_context", fake_create_default_context)

    client = InfrahubClient(config=Config(address="http://mock", tls_insecure=True))

    verify_value = client.config.tls_context

    assert verify_value.check_hostname is False
    assert verify_value.verify_mode == ssl.CERT_NONE


async def test_verify_config_uses_custom_tls_context(monkeypatch) -> None:
    def fake_create_default_context(*args: object, **kwargs: object) -> object:
        raise AssertionError("create_default_context should not be called when custom context is provided")

    monkeypatch.setattr("ssl.create_default_context", fake_create_default_context)

    config = Config(address="http://mock")
    custom_context = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS_CLIENT)
    config.set_ssl_context(custom_context)

    client = InfrahubClient(config=config)

    clone_client = client.clone()

    assert client.config.tls_context is custom_context
    assert clone_client.config.tls_context is custom_context


async def test_method_sanity() -> None:
    """Validate that there is at least one public method and that both clients look the same."""
    assert async_client_methods
    assert async_client_methods == sync_client_methods


@pytest.mark.parametrize("method", async_client_methods)
async def test_validate_method_signature(
    method,
    replace_async_return_annotation,
    replace_sync_return_annotation,
    replace_async_parameter_annotations,
    replace_sync_parameter_annotations,
) -> None:
    async_method = getattr(InfrahubClient, method)
    sync_method = getattr(InfrahubClientSync, method)
    async_sig = inspect.signature(async_method)
    sync_sig = inspect.signature(sync_method)

    assert replace_async_parameter_annotations(async_sig.parameters) == replace_async_parameter_annotations(
        sync_sig.parameters
    )
    assert replace_sync_parameter_annotations(async_sig.parameters) == replace_sync_parameter_annotations(
        sync_sig.parameters
    )
    assert async_sig.return_annotation == replace_sync_return_annotation(sync_sig.return_annotation)
    assert replace_async_return_annotation(async_sig.return_annotation) == sync_sig.return_annotation


def test_init_with_invalid_address() -> None:
    with pytest.raises(ValueError) as exc:
        InfrahubClient(address="missing-schema")

    assert "The configured address is not a valid url" in str(exc.value)


async def test_get_repositories(
    client: InfrahubClient, mock_branches_list_query, mock_schema_query_02, mock_repositories_query
) -> None:
    repos = await client.get_list_repositories()

    assert len(repos) == 2
    assert repos["infrahub-demo-edge"].repository.get_kind() == "CoreRepository"
    assert repos["infrahub-demo-edge"].repository.id == "9486cfce-87db-479d-ad73-07d80ba96a0f"
    assert repos["infrahub-demo-edge"].branches == {"cr1234": "bbbbbbbbbbbbbbbbbbbb", "main": "aaaaaaaaaaaaaaaaaaaa"}
    assert repos["infrahub-demo-edge-read-only"].repository.get_kind() == "CoreReadOnlyRepository"
    assert repos["infrahub-demo-edge-read-only"].repository.id == "aeff0feb-6a49-406e-b395-de7b7856026d"
    assert repos["infrahub-demo-edge-read-only"].branches == {
        "cr1234": "dddddddddddddddddddd",
        "main": "cccccccccccccccccccc",
    }


@pytest.mark.parametrize("client_type", client_types)
async def test_method_count(clients, mock_query_repository_count, client_type) -> None:
    if client_type == "standard":
        count = await clients.standard.count(kind="CoreRepository")
    else:
        count = clients.sync.count(kind="CoreRepository")

    assert count == 5


@pytest.mark.parametrize("client_type", client_types)
async def test_method_count_with_filter(clients, mock_query_repository_count, client_type) -> None:
    if client_type == "standard":
        count = await clients.standard.count(kind="CoreRepository", name__value="test")
    else:
        count = clients.sync.count(kind="CoreRepository", name__value="test")

    assert count == 5


@pytest.mark.parametrize("client_type", client_types)
async def test_method_get_version(clients, mock_query_infrahub_version, client_type) -> None:
    if client_type == "standard":
        version = await clients.standard.get_version()
    else:
        version = clients.sync.get_version()

    assert version == "1.1.0"


@pytest.mark.parametrize("client_type", client_types)
async def test_method_get_user(clients, mock_query_infrahub_user, client_type) -> None:
    if client_type == "standard":
        user = await clients.standard.get_user()
    else:
        user = clients.sync.get_user()

    assert isinstance(user, dict)
    assert user["AccountProfile"]["display_label"] == "Admin"


@pytest.mark.parametrize("client_type", client_types)
async def test_method_get_user_permissions(clients, mock_query_infrahub_user, client_type) -> None:
    if client_type == "standard":
        groups = await clients.standard.get_user_permissions()
    else:
        groups = clients.sync.get_user_permissions()

    assert isinstance(groups, dict)
    assert groups["Super Administrators"] == ["global:super_admin:allow_all", "object:*:*:any:allow_all"]


@pytest.mark.parametrize("client_type", client_types)
async def test_method_all_with_limit(clients, mock_query_repository_page1_2, client_type) -> None:
    if client_type == "standard":
        repos = await clients.standard.all(kind="CoreRepository", populate_store=False, limit=3)
        assert clients.standard.store.count() == 0

        repos = await clients.standard.all(kind="CoreRepository", limit=3)
        assert clients.standard.store.count() == 3
    else:
        repos = clients.sync.all(kind="CoreRepository", populate_store=False, limit=3)
        assert clients.sync.store.count() == 0

        repos = clients.sync.all(kind="CoreRepository", limit=3)
        assert clients.sync.store.count() == 3
    assert len(repos) == 3


@pytest.mark.parametrize("client_type", client_types)
async def test_method_all_multiple_pages(
    clients, mock_query_repository_page1_2, mock_query_repository_page2_2, client_type
) -> None:
    if client_type == "standard":
        repos = await clients.standard.all(kind="CoreRepository", populate_store=False)
        assert clients.standard.store.count() == 0

        repos = await clients.standard.all(kind="CoreRepository")
        assert clients.standard.store.count() == 5
    else:
        repos = clients.sync.all(kind="CoreRepository", populate_store=False)
        assert clients.sync.store.count() == 0

        repos = clients.sync.all(kind="CoreRepository")
        assert clients.sync.store.count() == 5

    assert len(repos) == 5


@pytest.mark.parametrize("client_type, use_parallel", batch_client_types)
async def test_method_all_batching(
    clients, mock_query_location_batch_count, mock_query_location_batch, client_type, use_parallel
) -> None:
    if client_type == "standard":
        locations = await clients.standard.all(kind="BuiltinLocation", populate_store=False, parallel=use_parallel)
        assert clients.standard.store.count() == 0

        locations = await clients.standard.all(kind="BuiltinLocation", parallel=use_parallel)
        assert clients.standard.store.count() == 30
    else:
        locations = clients.sync.all(kind="BuiltinLocation", populate_store=False, parallel=use_parallel)
        assert clients.sync.store.count() == 0

        locations = clients.sync.all(kind="BuiltinLocation", parallel=use_parallel)
        assert clients.sync.store.count() == 30

    assert len(locations) == 30


@pytest.mark.parametrize("client_type", client_types)
async def test_method_all_single_page(clients, mock_query_repository_page1_1, client_type) -> None:
    if client_type == "standard":
        repos = await clients.standard.all(kind="CoreRepository", populate_store=False)
        assert clients.standard.store.count() == 0

        repos = await clients.standard.all(kind="CoreRepository")
        assert clients.standard.store.count() == 2
    else:
        repos = clients.sync.all(kind="CoreRepository", populate_store=False)
        assert clients.sync.store.count() == 0

        repos = clients.sync.all(kind="CoreRepository")
        assert clients.sync.store.count() == 2

    assert len(repos) == 2


@pytest.mark.parametrize("client_type", client_types)
async def test_method_all_generic(clients, mock_query_corenode_page1_1, client_type) -> None:
    if client_type == "standard":
        nodes = await clients.standard.all(kind="CoreNode")
    else:
        nodes = clients.sync.all(kind="CoreNode")

    assert len(nodes) == 2
    assert nodes[0].typename == "BuiltinTag"
    assert nodes[1].typename == "BuiltinLocation"


@pytest.mark.parametrize("client_type", client_types)
async def test_method_get_by_id(httpx_mock: HTTPXMock, clients, mock_schema_query_01, client_type) -> None:
    response = {
        "data": {
            "CoreRepository": {
                "edges": [
                    {
                        "node": {
                            "__typename": "CoreRepository",
                            "id": "bfae43e8-5ebb-456c-a946-bf64e930710a",
                            "name": {"value": "infrahub-demo-core"},
                            "location": {"value": "git@github.com:opsmill/infrahub-demo-core.git"},
                            "commit": {"value": "bbbbbbbbbbbbbbbbbbbb"},
                        }
                    }
                ]
            }
        }
    }

    response_id = "bfae43e8-5ebb-456c-a946-bf64e930710a"
    httpx_mock.add_response(
        method="POST",
        json=response,
        match_headers={"X-Infrahub-Tracker": "query-corerepository-page1"},
        is_reusable=True,
    )

    if client_type == "standard":
        repo = await clients.standard.get(kind="CoreRepository", id=response_id, populate_store=False)
        assert isinstance(repo, InfrahubNode)
        with pytest.raises(NodeNotFoundError):
            assert clients.standard.store.get(key=response_id)

        repo = await clients.standard.get(kind="CoreRepository", id=response_id)
        assert isinstance(repo, InfrahubNode)
        assert clients.standard.store.get(key=response_id)
    else:
        repo = clients.sync.get(kind="CoreRepository", id=response_id, populate_store=False)
        assert isinstance(repo, InfrahubNodeSync)
        with pytest.raises(NodeNotFoundError):
            assert clients.sync.store.get(key=response_id)

        repo = clients.sync.get(kind="CoreRepository", id=response_id)
        assert isinstance(repo, InfrahubNodeSync)
        assert clients.sync.store.get(key=response_id)


@pytest.mark.parametrize("client_type", client_types)
async def test_method_get_by_hfid(httpx_mock: HTTPXMock, clients, mock_schema_query_01, client_type) -> None:
    response = {
        "data": {
            "CoreRepository": {
                "edges": [
                    {
                        "node": {
                            "__typename": "CoreRepository",
                            "id": "bfae43e8-5ebb-456c-a946-bf64e930710a",
                            "hfid": ["infrahub-demo-core"],
                            "name": {"value": "infrahub-demo-core"},
                            "location": {"value": "git@github.com:opsmill/infrahub-demo-core.git"},
                            "commit": {"value": "bbbbbbbbbbbbbbbbbbbb"},
                        }
                    }
                ]
            }
        }
    }

    response_id = "bfae43e8-5ebb-456c-a946-bf64e930710a"
    httpx_mock.add_response(
        method="POST",
        json=response,
        match_headers={"X-Infrahub-Tracker": "query-corerepository-page1"},
        is_reusable=True,
    )

    if client_type == "standard":
        repo = await clients.standard.get(kind="CoreRepository", hfid=["infrahub-demo-core"], populate_store=False)
        assert isinstance(repo, InfrahubNode)
        with pytest.raises(NodeNotFoundError):
            assert clients.standard.store.get(key=response_id)

        repo = await clients.standard.get(kind="CoreRepository", hfid=["infrahub-demo-core"])
        assert isinstance(repo, InfrahubNode)
        assert clients.standard.store.get(key=response_id)
    else:
        repo = clients.sync.get(kind="CoreRepository", hfid=["infrahub-demo-core"], populate_store=False)
        assert isinstance(repo, InfrahubNodeSync)
        with pytest.raises(NodeNotFoundError):
            assert clients.sync.store.get(key="infrahub-demo-core")

        repo = clients.sync.get(kind="CoreRepository", hfid=["infrahub-demo-core"])
        assert isinstance(repo, InfrahubNodeSync)
        assert clients.sync.store.get(key=response_id)


@pytest.mark.parametrize("client_type", client_types)
async def test_method_get_by_default_filter(httpx_mock: HTTPXMock, clients, mock_schema_query_01, client_type) -> None:
    response = {
        "data": {
            "CoreRepository": {
                "edges": [
                    {
                        "node": {
                            "__typename": "CoreRepository",
                            "id": "bfae43e8-5ebb-456c-a946-bf64e930710a",
                            "name": {"value": "infrahub-demo-core"},
                            "location": {"value": "git@github.com:opsmill/infrahub-demo-core.git"},
                            "commit": {"value": "bbbbbbbbbbbbbbbbbbbb"},
                        }
                    }
                ]
            }
        }
    }

    response_id = "bfae43e8-5ebb-456c-a946-bf64e930710a"
    httpx_mock.add_response(
        method="POST",
        json=response,
        match_headers={"X-Infrahub-Tracker": "query-corerepository-page1"},
        is_reusable=True,
    )

    if client_type == "standard":
        repo = await clients.standard.get(kind="CoreRepository", id="infrahub-demo-core", populate_store=False)
        assert isinstance(repo, InfrahubNode)
        with pytest.raises(NodeNotFoundError):
            assert clients.standard.store.get(key=response_id)

        repo = await clients.standard.get(kind="CoreRepository", id="infrahub-demo-core")
        assert clients.standard.store.get(key=response_id)
    else:
        repo = clients.sync.get(kind="CoreRepository", id="infrahub-demo-core", populate_store=False)
        assert isinstance(repo, InfrahubNodeSync)
        with pytest.raises(NodeNotFoundError):
            assert clients.sync.store.get(key="infrahub-demo-core")

        repo = clients.sync.get(kind="CoreRepository", id="infrahub-demo-core")
        assert clients.sync.store.get(key=response_id)


@pytest.mark.parametrize("client_type", client_types)
async def test_method_get_by_name(httpx_mock: HTTPXMock, clients, mock_schema_query_01, client_type) -> None:
    response = {
        "data": {
            "CoreRepository": {
                "edges": [
                    {
                        "node": {
                            "__typename": "CoreRepository",
                            "id": "bfae43e8-5ebb-456c-a946-bf64e930710a",
                            "name": {"value": "infrahub-demo-core"},
                            "location": {"value": "git@github.com:opsmill/infrahub-demo-core.git"},
                            "commit": {"value": "bbbbbbbbbbbbbbbbbbbb"},
                        }
                    }
                ]
            }
        }
    }

    httpx_mock.add_response(
        method="POST",
        json=response,
        match_headers={"X-Infrahub-Tracker": "query-corerepository-page1"},
        is_reusable=True,
    )

    if client_type == "standard":
        repo = await clients.standard.get(kind="CoreRepository", name__value="infrahub-demo-core")
        assert isinstance(repo, InfrahubNode)
    else:
        repo = clients.sync.get(kind="CoreRepository", name__value="infrahub-demo-core")
        assert isinstance(repo, InfrahubNodeSync)
    assert repo.id == "bfae43e8-5ebb-456c-a946-bf64e930710a"


@pytest.mark.parametrize("client_type", client_types)
async def test_method_get_not_found(
    httpx_mock: HTTPXMock, clients, mock_query_repository_page1_empty, client_type
) -> None:
    with pytest.raises(NodeNotFoundError):
        if client_type == "standard":
            await clients.standard.get(kind="CoreRepository", name__value="infrahub-demo-core")
        else:
            clients.sync.get(kind="CoreRepository", name__value="infrahub-demo-core")


@pytest.mark.parametrize("client_type", client_types)
async def test_method_get_not_found_none(
    httpx_mock: HTTPXMock, clients, mock_query_repository_page1_empty, client_type
) -> None:
    if client_type == "standard":
        response = await clients.standard.get(
            kind="CoreRepository", name__value="infrahub-demo-core", raise_when_missing=False
        )
    else:
        response = clients.sync.get(kind="CoreRepository", name__value="infrahub-demo-core", raise_when_missing=False)

    assert response is None


@pytest.mark.parametrize("client_type", client_types)
async def test_method_get_found_many(
    httpx_mock: HTTPXMock,
    clients,
    mock_schema_query_01,
    mock_query_repository_page1_1,
    client_type,
) -> None:
    with pytest.raises(IndexError):
        if client_type == "standard":
            await clients.standard.get(kind="CoreRepository", id="bfae43e8-5ebb-456c-a946-bf64e930710a")
        else:
            clients.sync.get(kind="CoreRepository", id="bfae43e8-5ebb-456c-a946-bf64e930710a")


@pytest.mark.parametrize("client_type", client_types)
async def test_method_filters_many(httpx_mock: HTTPXMock, clients, mock_query_repository_page1_1, client_type) -> None:
    if client_type == "standard":
        repos = await clients.standard.filters(
            kind="CoreRepository",
            ids=[
                "bfae43e8-5ebb-456c-a946-bf64e930710a",
                "9486cfce-87db-479d-ad73-07d80ba96a0f",
            ],
            populate_store=False,
        )
        assert len(repos) == 2
        assert clients.standard.store.count() == 0

        repos = await clients.standard.filters(
            kind="CoreRepository",
            ids=[
                "bfae43e8-5ebb-456c-a946-bf64e930710a",
                "9486cfce-87db-479d-ad73-07d80ba96a0f",
            ],
        )
        assert clients.standard.store.count() == 2
        assert len(repos) == 2
    else:
        repos = clients.sync.filters(
            kind="CoreRepository",
            ids=[
                "bfae43e8-5ebb-456c-a946-bf64e930710a",
                "9486cfce-87db-479d-ad73-07d80ba96a0f",
            ],
            populate_store=False,
        )
        assert len(repos) == 2
        assert clients.sync.store.count() == 0

        repos = clients.sync.filters(
            kind="CoreRepository",
            ids=[
                "bfae43e8-5ebb-456c-a946-bf64e930710a",
                "9486cfce-87db-479d-ad73-07d80ba96a0f",
            ],
        )
        assert clients.sync.store.count() == 2
        assert len(repos) == 2


@pytest.mark.parametrize("client_type", client_types)
async def test_method_filters_empty(
    httpx_mock: HTTPXMock, clients, mock_query_repository_page1_empty, client_type
) -> None:
    if client_type == "standard":
        repos = await clients.standard.filters(
            kind="CoreRepository",
            ids=[
                "bfae43e8-5ebb-456c-a946-bf64e930710a",
                "9486cfce-87db-479d-ad73-07d80ba96a0f",
            ],
        )
    else:
        repos = clients.sync.filters(
            kind="CoreRepository",
            ids=[
                "bfae43e8-5ebb-456c-a946-bf64e930710a",
                "9486cfce-87db-479d-ad73-07d80ba96a0f",
            ],
        )
    assert len(repos) == 0


@pytest.mark.parametrize("client_type", client_types)
async def test_allocate_next_ip_address(
    httpx_mock: HTTPXMock,
    mock_schema_query_ipam: HTTPXMock,
    clients,
    ipaddress_pool_schema,
    ipam_ipprefix_schema,
    ipam_ipprefix_data,
    client_type,
) -> None:
    httpx_mock.add_response(
        method="POST",
        json={
            "data": {
                "InfrahubIPAddressPoolGetResource": {
                    "ok": True,
                    "node": {
                        "id": "17da1246-54f1-a9c0-2784-179f0ec5b128",
                        "kind": "IpamIPAddress",
                        "identifier": "test",
                        "display_label": "192.0.2.0/32",
                    },
                }
            }
        },
        match_headers={"X-Infrahub-Tracker": "allocate-ip-loopback"},
        is_reusable=True,
    )
    httpx_mock.add_response(
        method="POST",
        json={
            "data": {
                "IpamIPAddress": {
                    "count": 1,
                    "edges": [
                        {
                            "node": {
                                "id": "17d9bd8d-8fc2-70b0-278a-179f425e25cb",
                                "__typename": "IpamIPAddress",
                                "address": {"value": "192.0.2.0/32"},
                                "description": {"value": "test"},
                            }
                        }
                    ],
                }
            }
        },
        match_headers={"X-Infrahub-Tracker": "query-ipamipaddress-page1"},
        is_reusable=True,
    )

    if client_type == "standard":
        ip_prefix = InfrahubNode(client=clients.standard, schema=ipam_ipprefix_schema, data=ipam_ipprefix_data)
        ip_pool = InfrahubNode(
            client=clients.standard,
            schema=ipaddress_pool_schema,
            data={
                "id": "pppppppp-pppp-pppp-pppp-pppppppppppp",
                "name": "Core loopbacks",
                "default_address_type": "IpamIPAddress",
                "default_prefix_length": 32,
                "ip_namespace": "ip_namespace",
                "resources": [ip_prefix],
            },
        )
        ip_address = await clients.standard.allocate_next_ip_address(
            resource_pool=ip_pool,
            identifier="test",
            prefix_length=32,
            address_type="IpamIPAddress",
            data={"description": "test"},
            tracker="allocate-ip-loopback",
        )
    else:
        ip_prefix = InfrahubNodeSync(client=clients.sync, schema=ipam_ipprefix_schema, data=ipam_ipprefix_data)
        ip_pool = InfrahubNodeSync(
            client=clients.sync,
            schema=ipaddress_pool_schema,
            data={
                "id": "pppppppp-pppp-pppp-pppp-pppppppppppp",
                "name": "Core loopbacks",
                "default_address_type": "IpamIPAddress",
                "default_prefix_length": 32,
                "ip_namespace": "ip_namespace",
                "resources": [ip_prefix],
            },
        )
        ip_address = clients.sync.allocate_next_ip_address(
            resource_pool=ip_pool,
            identifier="test",
            prefix_length=32,
            address_type="IpamIPAddress",
            data={"description": "test"},
            tracker="allocate-ip-loopback",
        )

    assert ip_address
    assert str(ip_address.address.value) == "192.0.2.0/32"
    assert ip_address.description.value == "test"


@pytest.mark.parametrize("client_type", client_types)
async def test_allocate_next_ip_prefix(
    httpx_mock: HTTPXMock,
    mock_schema_query_ipam: HTTPXMock,
    clients,
    ipprefix_pool_schema,
    ipam_ipprefix_schema,
    ipam_ipprefix_data,
    client_type,
) -> None:
    httpx_mock.add_response(
        method="POST",
        json={
            "data": {
                "InfrahubIPPrefixPoolGetResource": {
                    "ok": True,
                    "node": {
                        "id": "7d9bd8d-8fc2-70b0-278a-179f425e25cb",
                        "kind": "IpamIPPrefix",
                        "identifier": "test",
                        "display_label": "192.0.2.0/31",
                    },
                }
            }
        },
        match_headers={"X-Infrahub-Tracker": "allocate-ip-interco"},
        is_reusable=True,
    )
    httpx_mock.add_response(
        method="POST",
        json={
            "data": {
                "IpamIPPrefix": {
                    "count": 1,
                    "edges": [
                        {
                            "node": {
                                "id": "17d9bd8d-8fc2-70b0-278a-179f425e25cb",
                                "__typename": "IpamIPPrefix",
                                "prefix": {"value": "192.0.2.0/31"},
                                "description": {"value": "test"},
                            }
                        }
                    ],
                }
            }
        },
        match_headers={"X-Infrahub-Tracker": "query-ipamipprefix-page1"},
        is_reusable=True,
    )

    if client_type == "standard":
        ip_prefix = InfrahubNode(client=clients.standard, schema=ipam_ipprefix_schema, data=ipam_ipprefix_data)
        ip_pool = InfrahubNode(
            client=clients.standard,
            schema=ipprefix_pool_schema,
            data={
                "id": "pppppppp-pppp-pppp-pppp-pppppppppppp",
                "name": "Core intercos",
                "default_prefix_type": "IpamIPPrefix",
                "default_prefix_length": 31,
                "ip_namespace": "ip_namespace",
                "resources": [ip_prefix],
            },
        )
        ip_prefix = await clients.standard.allocate_next_ip_prefix(
            resource_pool=ip_pool,
            identifier="test",
            prefix_length=31,
            prefix_type="IpamIPPrefix",
            data={"description": "test"},
            tracker="allocate-ip-interco",
        )
    else:
        ip_prefix = InfrahubNodeSync(client=clients.sync, schema=ipam_ipprefix_schema, data=ipam_ipprefix_data)
        ip_pool = InfrahubNodeSync(
            client=clients.sync,
            schema=ipprefix_pool_schema,
            data={
                "id": "pppppppp-pppp-pppp-pppp-pppppppppppp",
                "name": "Core intercos",
                "default_prefix_type": "IpamIPPrefix",
                "default_prefix_length": 31,
                "ip_namespace": "ip_namespace",
                "resources": [ip_prefix],
            },
        )
        ip_prefix = clients.sync.allocate_next_ip_prefix(
            resource_pool=ip_pool,
            identifier="test",
            prefix_length=31,
            prefix_type="IpamIPPrefix",
            data={"description": "test"},
            tracker="allocate-ip-interco",
        )

    assert ip_prefix
    assert str(ip_prefix.prefix.value) == "192.0.2.0/31"
    assert ip_prefix.description.value == "test"


EXPECTED_ECHO = """URL: http://mock/graphql/main
QUERY:

    query GetTags($name: String!) {
        BuiltinTag(name__value: $name) {
            edges {
                node {
                    id
                    display_label
                }
            }
        }
    }

VARIABLES:
{
    "name": "red"
}

"""


@pytest.mark.parametrize("client_type", client_types)
async def test_query_echo(httpx_mock: HTTPXMock, echo_clients, client_type) -> None:
    httpx_mock.add_response(
        method="POST",
        json={"data": {"BuiltinTag": {"edges": []}}},
        is_reusable=True,
    )

    query = """
    query GetTags($name: String!) {
        BuiltinTag(name__value: $name) {
            edges {
                node {
                    id
                    display_label
                }
            }
        }
    }
"""

    variables = {"name": "red"}

    if client_type == "standard":
        response = await echo_clients.standard.execute_graphql(query=query, variables=variables)
    else:
        response = echo_clients.sync.execute_graphql(query=query, variables=variables)

    assert response == {"BuiltinTag": {"edges": []}}
    assert echo_clients.stdout.getvalue().splitlines() == EXPECTED_ECHO.splitlines()


@pytest.mark.parametrize("client_type", client_types)
async def test_clone(clients: BothClients, client_type: str) -> None:
    """Validate that the configuration of a cloned client is a replica of the original client"""
    if client_type == "standard":
        clone = clients.standard.clone()
        assert clone.config == clients.standard.config
        assert isinstance(clone, InfrahubClient)
        assert clients.standard.default_branch == clone.default_branch
    else:
        clone = clients.sync.clone()
        assert clone.config == clients.sync.config
        assert isinstance(clone, InfrahubClientSync)
        assert clients.sync.default_branch == clone.default_branch


@pytest.mark.parametrize("client_type", client_types)
async def test_clone_define_branch(clients: BothClients, client_type: str) -> None:
    """Validate that the clone branch parameter sets the correct branch of the cloned client"""
    clone_branch = "my_other_branch"
    if client_type == "standard":
        original_branch = clients.standard.default_branch
        clone = clients.standard.clone(branch=clone_branch)
        assert clients.standard.store._default_branch == original_branch
        assert isinstance(clone, InfrahubClient)
        assert clients.standard.default_branch != clone.default_branch
    else:
        original_branch = clients.standard.default_branch
        clone = clients.sync.clone(branch="my_other_branch")
        assert clients.sync.store._default_branch == original_branch
        assert isinstance(clone, InfrahubClientSync)
        assert clients.sync.default_branch != clone.default_branch

    assert clone.default_branch == clone_branch
    assert original_branch != clone_branch
    assert clone.store._default_branch == clone_branch
