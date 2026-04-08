from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk import InfrahubClient
from infrahub_sdk.protocols_generator.generator import CodeGenerator
from infrahub_sdk.schema import AttributeSchemaAPI

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock


@dataclass
class SyncifyTestCase:
    name: str
    sync: bool
    input: list[str]
    output: list[str]


SYNCIFY_TEST_CASES = [
    SyncifyTestCase(name="sync-str", sync=True, input=["CoreNode"], output=["CoreNodeSync"]),
    SyncifyTestCase(
        name="sync-list",
        sync=True,
        input=["LineageSource", "CoreNode", "CoreObjectTemplate"],
        output=["LineageSource", "CoreObjectTemplateSync", "CoreNodeSync"],
    ),
    SyncifyTestCase(name="async-str", sync=False, input=["CoreNode"], output=["CoreNode"]),
    SyncifyTestCase(
        name="async-list",
        sync=False,
        input=["LineageSource", "CoreNode", "CoreObjectTemplate"],
        output=["LineageSource", "CoreObjectTemplate", "CoreNode"],
    ),
]


@dataclass
class RenderAttributeTestCase:
    name: str
    optional: bool
    default_value: Any
    expected: str


RENDER_ATTRIBUTE_TEST_CASES = [
    RenderAttributeTestCase(
        name="required-no-default",
        optional=False,
        default_value=None,
        expected="enabled: Boolean",
    ),
    RenderAttributeTestCase(
        name="required-with-default",
        optional=False,
        default_value=True,
        expected="enabled: Boolean",
    ),
    RenderAttributeTestCase(
        name="optional-no-default",
        optional=True,
        default_value=None,
        expected="enabled: BooleanOptional",
    ),
    RenderAttributeTestCase(
        name="optional-with-default",
        optional=True,
        default_value=True,
        expected="enabled: Boolean",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    [pytest.param(tc, id=tc.name) for tc in RENDER_ATTRIBUTE_TEST_CASES],
)
async def test_filter_render_attribute(test_case: RenderAttributeTestCase) -> None:
    attr = AttributeSchemaAPI(
        name="enabled",
        kind="Boolean",
        optional=test_case.optional,
        default_value=test_case.default_value,
    )
    assert CodeGenerator._jinja2_filter_render_attribute(attr) == test_case.expected


@pytest.mark.parametrize(
    "test_case",
    [pytest.param(tc, id=tc.name) for tc in SYNCIFY_TEST_CASES],
)
async def test_filter_syncify(test_case: SyncifyTestCase) -> None:
    assert CodeGenerator._jinja2_filter_syncify(value=test_case.input, sync=test_case.sync) == test_case.output
    assert CodeGenerator._jinja2_filter_syncify(value=test_case.input, sync=test_case.sync) == test_case.output


async def test_generator(client: InfrahubClient, mock_schema_query_05: "HTTPXMock") -> None:
    schemas = await client.schema.fetch(branch="main")

    code_generator = CodeGenerator(schema=schemas)
    sync_protocols = code_generator.render()

    assert "class LocationGeneric(CoreNodeSync)" in sync_protocols
    assert "class LocationCountry(LocationGeneric)" in sync_protocols
    assert "class TemplateInfraDevice(LineageSource, CoreObjectTemplateSync, CoreNodeSync)" in sync_protocols

    location_site_sync = """
class LocationSite(LocationGeneric):
    description: StringOptional
    facility_id: StringOptional
    name: String
    physical_address: StringOptional
    shortname: String
    children: RelationshipManagerSync
    member_of_groups: RelationshipManagerSync
    parent: RelatedNodeSync
    profiles: RelationshipManagerSync
    servers: RelationshipManagerSync
    subscriber_of_groups: RelationshipManagerSync
    tags: RelationshipManagerSync
"""

    assert location_site_sync in sync_protocols

    async_protocols = code_generator.render(sync=False)
    assert "class LocationGeneric(CoreNode)" in async_protocols
    assert "class LocationCountry(LocationGeneric)" in async_protocols
    assert "class TemplateInfraDevice(LineageSource, CoreObjectTemplate, CoreNode)" in async_protocols
