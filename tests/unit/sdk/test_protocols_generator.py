import pytest

from infrahub_sdk import InfrahubClient
from infrahub_sdk.protocols_generator.generator import CodeGenerator


@pytest.mark.parametrize(
    "sync,input,output",
    [
        (True, "CoreNode", "CoreNodeSync"),
        (
            True,
            ["LineageSource", "CoreNode", "CoreObjectTemplate"],
            ["LineageSource", "CoreNodeSync", "CoreObjectTemplate"],
        ),
        (False, "CoreNode", "CoreNode"),
        (
            False,
            ["LineageSource", "CoreNode", "CoreObjectTemplate"],
            ["LineageSource", "CoreNode", "CoreObjectTemplate"],
        ),
    ],
)
async def test_filter_syncify(sync, input, output):
    assert CodeGenerator._jinja2_filter_syncify(value=input, sync=sync) == output
    assert CodeGenerator._jinja2_filter_syncify(value=input, sync=sync) == output


async def test_generator(client: InfrahubClient, mock_schema_query_05):
    schemas = await client.schema.fetch(branch="main")

    code_generator = CodeGenerator(schema=schemas)
    sync_protocols = code_generator.render()
    assert "class LocationGeneric(CoreNodeSync)" in sync_protocols
    assert "class LocationCountry(LocationGeneric)" in sync_protocols
    assert "class TemplateInfraDevice(LineageSource, CoreNodeSync, CoreObjectTemplate)" in sync_protocols

    location_site_sync = """
class LocationSite(LocationGeneric):
    facility_id: StringOptional
    physical_address: StringOptional
    description: StringOptional
    name: String
    shortname: String
    member_of_groups: RelationshipManagerSync
    subscriber_of_groups: RelationshipManagerSync
    profiles: RelationshipManagerSync
    children: RelationshipManagerSync
    parent: RelatedNodeSync
    servers: RelationshipManagerSync
    tags: RelationshipManagerSync
"""
    assert location_site_sync in sync_protocols

    async_protocols = code_generator.render(sync=False)
    assert "class LocationGeneric(CoreNode)" in async_protocols
    assert "class LocationCountry(LocationGeneric)" in async_protocols
    assert "class TemplateInfraDevice(LineageSource, CoreNode, CoreObjectTemplate)" in async_protocols
