from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest

from infrahub_sdk.template import Jinja2Template
from infrahub_sdk.template.exceptions import JinjaFilterError, JinjaTemplateError, JinjaTemplateOperationViolationError
from infrahub_sdk.template.filters import INFRAHUB_FILTERS, ExecutionContext, FilterDefinition
from infrahub_sdk.template.infrahub_filters import InfrahubFilters, from_json, from_yaml

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from infrahub_sdk import InfrahubClient


pytestmark = pytest.mark.httpx_mock(can_send_already_matched_responses=True)

ARTIFACT_CONTENT_URL = "http://mock/api/storage/object"
FILE_BY_STORAGE_ID_URL = "http://mock/api/files/by-storage-id"

CLIENT_FILTER_PARAMS = [
    pytest.param(
        "artifact_content",
        "{{ storage_id | artifact_content }}",
        f"{ARTIFACT_CONTENT_URL}/test-id",
        {"content-type": "text/plain"},
        id="artifact_content",
    ),
    pytest.param(
        "file_object_content",
        "{{ storage_id | file_object_content }}",
        f"{FILE_BY_STORAGE_ID_URL}/test-id",
        {"content-type": "text/plain"},
        id="file_object_content",
    ),
]


class TestJinjaFilterError:
    def test_instantiation_without_hint(self) -> None:
        exc = JinjaFilterError(filter_name="my_filter", message="something broke")
        assert exc.filter_name == "my_filter"
        assert exc.hint is None
        assert exc.message == "Filter 'my_filter': something broke"

    def test_instantiation_with_hint(self) -> None:
        exc = JinjaFilterError(filter_name="my_filter", message="something broke", hint="try harder")
        assert exc.filter_name == "my_filter"
        assert exc.hint == "try harder"
        assert exc.message == "Filter 'my_filter': something broke — try harder"


class TestFilterDefinition:
    def test_trusted_when_all_contexts(self) -> None:
        fd = FilterDefinition(name="abs", allowed_contexts=ExecutionContext.ALL, source="jinja2")
        assert fd.trusted is True

    def test_not_trusted_when_local_only(self) -> None:
        fd = FilterDefinition(name="safe", allowed_contexts=ExecutionContext.LOCAL, source="jinja2")
        assert fd.trusted is False

    def test_not_trusted_when_worker_and_local(self) -> None:
        fd = FilterDefinition(
            name="artifact_content",
            allowed_contexts=ExecutionContext.WORKER | ExecutionContext.LOCAL,
            source="infrahub",
        )
        assert fd.trusted is False

    def test_not_trusted_when_core_only(self) -> None:
        fd = FilterDefinition(name="custom", allowed_contexts=ExecutionContext.CORE, source="test")
        assert fd.trusted is False

    def test_infrahub_filters_list_sorted(self) -> None:
        """Infrahub filter names should be in alphabetical order."""
        names = [fd.name for fd in INFRAHUB_FILTERS]
        assert names == sorted(names)


class TestValidateContext:
    def test_restricted_true_blocks_untrusted_filters(self) -> None:
        """restricted=True behaves like ExecutionContext.CORE -- blocks LOCAL-only filters."""
        jinja = Jinja2Template(template="{{ network | get_all_host }}")
        with pytest.raises(JinjaTemplateOperationViolationError) as exc:
            jinja.validate(restricted=True)
        assert exc.value.message == "The 'get_all_host' filter isn't allowed to be used"

    def test_restricted_false_allows_all_filters(self) -> None:
        """restricted=False behaves like ExecutionContext.LOCAL -- allows everything."""
        jinja = Jinja2Template(template="{{ network | get_all_host }}")
        jinja.validate(restricted=False)

    def test_context_core_blocks_artifact_content(self) -> None:
        jinja = Jinja2Template(template="{{ sid | artifact_content }}")
        with pytest.raises(JinjaTemplateOperationViolationError) as exc:
            jinja.validate(context=ExecutionContext.CORE)
        assert exc.value.message == "The 'artifact_content' filter isn't allowed to be used"

    def test_context_worker_allows_artifact_content(self) -> None:
        jinja = Jinja2Template(template="{{ sid | artifact_content }}")
        jinja.validate(context=ExecutionContext.WORKER)

    def test_context_worker_blocks_local_only_filters(self) -> None:
        """WORKER context should still block LOCAL-only filters like 'safe'."""
        jinja = Jinja2Template(template="{{ data | safe }}")
        with pytest.raises(JinjaTemplateOperationViolationError) as exc:
            jinja.validate(context=ExecutionContext.WORKER)
        assert exc.value.message == "The 'safe' filter isn't allowed to be used"

    def test_context_local_allows_local_only_filters(self) -> None:
        jinja = Jinja2Template(template="{{ data | safe }}")
        jinja.validate(context=ExecutionContext.LOCAL)

    def test_context_local_allows_artifact_content(self) -> None:
        """LOCAL context allows artifact_content (WORKER | LOCAL)."""
        jinja = Jinja2Template(template="{{ sid | artifact_content }}")
        jinja.validate(context=ExecutionContext.LOCAL)

    @pytest.mark.parametrize("context", [ExecutionContext.CORE, ExecutionContext.WORKER])
    def test_user_filters_always_allowed(self, context: ExecutionContext) -> None:
        def my_custom_filter(value: str) -> str:
            return value.upper()

        jinja = Jinja2Template(template="{{ name | my_custom }}", filters={"my_custom": my_custom_filter})
        jinja.validate(context=context)

    def test_context_core_allows_from_json(self) -> None:
        jinja = Jinja2Template(template="{{ '{\"a\":1}' | from_json }}")
        jinja.validate(context=ExecutionContext.CORE)


class TestClientDependentFilters:
    @pytest.mark.parametrize(("filter_name", "template", "url", "headers"), CLIENT_FILTER_PARAMS)
    async def test_happy_path(
        self,
        filter_name: str,
        template: str,
        url: str,
        headers: dict[str, str],
        client: InfrahubClient,
        httpx_mock: HTTPXMock,
    ) -> None:
        httpx_mock.add_response(method="GET", url=url, text="rendered content", headers=headers)
        jinja = Jinja2Template(template=template, client=client)
        result = await jinja.render(variables={"storage_id": "test-id"})
        assert result == "rendered content"

    @pytest.mark.parametrize(("filter_name", "template", "url", "headers"), CLIENT_FILTER_PARAMS)
    @pytest.mark.parametrize(
        ("storage_id_value", "expected_message"),
        [
            pytest.param(
                None,
                "Filter '{filter_name}': storage_id is null"
                " — ensure the GraphQL query returns a valid storage_id value",
                id="null",
            ),
            pytest.param(
                "",
                "Filter '{filter_name}': storage_id is empty"
                " — ensure the GraphQL query returns a non-empty storage_id value",
                id="empty",
            ),
        ],
    )
    async def test_invalid_storage_id(
        self,
        filter_name: str,
        template: str,
        url: str,
        headers: dict[str, str],
        storage_id_value: str | None,
        expected_message: str,
        client: InfrahubClient,
    ) -> None:
        jinja = Jinja2Template(template=template, client=client)
        with pytest.raises(JinjaTemplateError) as exc:
            await jinja.render(variables={"storage_id": storage_id_value})
        assert exc.value.message == expected_message.format(filter_name=filter_name)

    @pytest.mark.parametrize(
        ("template", "url"),
        [
            pytest.param(
                "{{ storage_id | artifact_content }}", f"{ARTIFACT_CONTENT_URL}/abc-123", id="artifact_content"
            ),
            pytest.param(
                "{{ storage_id | file_object_content }}", f"{FILE_BY_STORAGE_ID_URL}/abc-123", id="file_object_content"
            ),
        ],
    )
    async def test_store_exception_is_wrapped(
        self, template: str, url: str, client: InfrahubClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_exception(httpx.ConnectError("connection timeout"), method="GET", url=url)
        jinja = Jinja2Template(template=template, client=client)
        with pytest.raises(JinjaTemplateError):
            await jinja.render(variables={"storage_id": "abc-123"})

    @pytest.mark.parametrize(
        ("template", "url", "storage_id", "expected_message"),
        [
            pytest.param(
                "{{ storage_id | artifact_content }}",
                f"{ARTIFACT_CONTENT_URL}/sid-x",
                "sid-x",
                "Filter 'artifact_content': permission denied for storage_id: sid-x",
                id="artifact_content",
            ),
            pytest.param(
                "{{ storage_id | file_object_content }}",
                f"{FILE_BY_STORAGE_ID_URL}/fid-x",
                "fid-x",
                "Filter 'file_object_content': permission denied for storage_id: fid-x",
                id="file_object_content",
            ),
        ],
    )
    async def test_auth_error(
        self,
        template: str,
        url: str,
        storage_id: str,
        expected_message: str,
        client: InfrahubClient,
        httpx_mock: HTTPXMock,
    ) -> None:
        httpx_mock.add_response(method="GET", url=url, status_code=403, json={"errors": [{"message": "forbidden"}]})
        jinja = Jinja2Template(template=template, client=client)
        with pytest.raises(JinjaTemplateError) as exc:
            await jinja.render(variables={"storage_id": storage_id})
        assert exc.value.message == expected_message

    async def test_file_object_content_binary_content_rejected(
        self, client: InfrahubClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url=f"{FILE_BY_STORAGE_ID_URL}/fid-bin",
            content=b"\x00\x01\x02",
            headers={"content-type": "application/octet-stream"},
        )
        jinja = Jinja2Template(template="{{ storage_id | file_object_content }}", client=client)
        with pytest.raises(JinjaTemplateError) as exc:
            await jinja.render(variables={"storage_id": "fid-bin"})
        assert (
            exc.value.message == "Filter 'file_object_content': Binary content not supported:"
            " content-type 'application/octet-stream' for identifier 'fid-bin'"
        )

    async def test_file_object_content_by_hfid_missing_kind(self, client: InfrahubClient) -> None:
        jinja = Jinja2Template(template="{{ hfid | file_object_content_by_hfid }}", client=client)
        with pytest.raises(JinjaTemplateError) as exc:
            await jinja.render(variables={"hfid": ["contract-2024"]})
        assert exc.value.message == (
            "Filter 'file_object_content_by_hfid': 'kind' argument is required"
            ' — use {{ hfid | file_object_content_by_hfid(kind="MyKind") }}'
        )


class TestFromJsonFilter:
    def test_valid_json(self) -> None:
        result = from_json('{"key": "value", "num": 42}')
        assert result == {"key": "value", "num": 42}

    def test_valid_json_list(self) -> None:
        result = from_json("[1, 2, 3]")
        assert result == [1, 2, 3]

    def test_empty_string_returns_empty_dict(self) -> None:
        assert from_json("") == {}

    def test_malformed_json_raises_error(self) -> None:
        with pytest.raises(JinjaFilterError) as exc:
            from_json("{not valid json}")
        assert exc.value.filter_name == "from_json"
        assert exc.value.message is not None
        assert exc.value.message.startswith("Filter 'from_json': invalid JSON: Expecting property name")

    async def test_render_through_template(self) -> None:
        jinja = Jinja2Template(template="{{ data | from_json }}")
        result = await jinja.render(variables={"data": '{"a": 1}'})
        assert result == "{'a': 1}"


class TestFromYamlFilter:
    def test_valid_yaml(self) -> None:
        result = from_yaml("key: value\nnum: 42")
        assert result == {"key": "value", "num": 42}

    def test_valid_yaml_list(self) -> None:
        result = from_yaml("- one\n- two\n- three")
        assert result == ["one", "two", "three"]

    def test_empty_string_returns_empty_dict(self) -> None:
        assert from_yaml("") == {}

    def test_malformed_yaml_raises_error(self) -> None:
        with pytest.raises(JinjaFilterError) as exc:
            from_yaml("key:\n\t- broken: [unclosed")
        assert exc.value.filter_name == "from_yaml"
        assert exc.value.message is not None
        assert exc.value.message.startswith("Filter 'from_yaml': invalid YAML: while scanning for the next token")

    async def test_render_through_template(self) -> None:
        jinja = Jinja2Template(template="{{ data | from_yaml }}")
        result = await jinja.render(variables={"data": "key: value"})
        assert result == "{'key': 'value'}"


class TestFilterChaining:
    async def test_artifact_content_piped_to_from_json(self, client: InfrahubClient, httpx_mock: HTTPXMock) -> None:
        json_payload = '{"hostname": "router1", "interfaces": ["eth0", "eth1"]}'
        httpx_mock.add_response(method="GET", url=f"{ARTIFACT_CONTENT_URL}/store-789", text=json_payload)
        jinja = Jinja2Template(template="{{ storage_id | artifact_content | from_json }}", client=client)
        result = await jinja.render(variables={"storage_id": "store-789"})
        assert result == "{'hostname': 'router1', 'interfaces': ['eth0', 'eth1']}"


class TestClientFilter:
    @pytest.mark.parametrize("filter_name", InfrahubFilters.CLIENT_FILTER_NAMES)
    async def test_no_client_raises(self, filter_name: str) -> None:
        filters = InfrahubFilters(client=None)
        method = getattr(filters, filter_name)
        with pytest.raises(JinjaFilterError) as exc:
            await method("some-id")
        assert (
            exc.value.message
            == f"Filter '{filter_name}': requires an InfrahubClient — pass a client via Jinja2Template(client=...)"
        )
        assert exc.value.filter_name == filter_name

    async def test_set_client_enables_artifact_content(self, client: InfrahubClient, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(method="GET", url=f"{ARTIFACT_CONTENT_URL}/abc", text="deferred content")
        tpl = Jinja2Template(template="{{ sid | artifact_content }}")

        with pytest.raises(JinjaTemplateError):
            await tpl.render(variables={"sid": "abc"})

        tpl.set_client(client=client)
        result = await tpl.render(variables={"sid": "abc"})
        assert result == "deferred content"
