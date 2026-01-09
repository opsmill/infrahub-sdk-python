from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from infrahub_sdk import InfrahubClient
from infrahub_sdk.protocols_generator.generator import CodeGenerator

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
