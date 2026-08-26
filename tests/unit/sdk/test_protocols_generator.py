from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk import InfrahubClient
from infrahub_sdk.protocols_generator.generator import CodeGenerator
from infrahub_sdk.protocols_generator.target import ProtocolTarget
from infrahub_sdk.schema import (
    AttributeSchemaAPI,
    GenericSchemaAPI,
    RelationshipCardinality,
    RelationshipSchemaAPI,
)
from tests.helpers.fixtures import read_fixture

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

GOLDEN_SUBDIR = "protocols_generator"


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


@dataclass
class HierarchyTestCase:
    name: str
    declared_relationships: list[str]


HIERARCHY_TEST_CASES = [
    HierarchyTestCase(name="neither-declared", declared_relationships=[]),
    HierarchyTestCase(name="only-parent-declared", declared_relationships=["parent"]),
    HierarchyTestCase(name="only-children-declared", declared_relationships=["children"]),
    HierarchyTestCase(name="both-declared", declared_relationships=["parent", "children"]),
]


@dataclass
class GoldenTestCase:
    name: str
    sync: bool
    fixture: str


GOLDEN_TEST_CASES = [
    GoldenTestCase(name="async", sync=False, fixture="user_schema_async.txt"),
    GoldenTestCase(name="sync", sync=True, fixture="user_schema_sync.txt"),
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
    generator = CodeGenerator(schema={})

    assert generator._jinja2_filter_syncify(value=test_case.input, sync=test_case.sync) == test_case.output
    assert generator._jinja2_filter_syncify(value=test_case.input, sync=test_case.sync) == test_case.output


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
    children: RelationshipManagerSync[LocationRack]
    member_of_groups: RelationshipManagerSync[CoreGroupSync]
    parent: RelationshipAttributeSync[LocationCountry]
    profiles: RelationshipManagerSync[CoreProfileSync]
    servers: RelationshipManagerSync[NetworkManagementServer]
    subscriber_of_groups: RelationshipManagerSync[CoreGroupSync]
    tags: RelationshipManagerSync[BuiltinTagSync]
"""

    assert location_site_sync in sync_protocols

    async_protocols = code_generator.render(sync=False)
    assert "class LocationGeneric(CoreNode)" in async_protocols
    assert "class LocationCountry(LocationGeneric)" in async_protocols
    assert "class TemplateInfraDevice(LineageSource, CoreObjectTemplate, CoreNode)" in async_protocols


@pytest.mark.parametrize(
    "test_case",
    [pytest.param(tc, id=tc.name) for tc in GOLDEN_TEST_CASES],
)
async def test_render_user_schema_matches_golden(
    test_case: GoldenTestCase, client: InfrahubClient, mock_schema_query_05: "HTTPXMock"
) -> None:
    """Rendering a user schema produces output byte-identical to the committed reference.

    The output of `infrahubctl protocols` is checked into user repositories and type-checked
    there, so any change to it - a renamed annotation, a reordered member, a different import
    line - is a change to something users depend on. Comparing the whole file makes that
    surface as a diff a reviewer has to accept on purpose, rather than passing unnoticed
    because the assertions only sampled a few lines.
    """
    schemas = await client.schema.fetch(branch="main")

    rendered = CodeGenerator(schema=schemas).render(sync=test_case.sync)

    assert rendered == read_fixture(test_case.fixture, GOLDEN_SUBDIR)


@pytest.mark.parametrize(
    "test_case",
    [pytest.param(tc, id=tc.name) for tc in HIERARCHY_TEST_CASES],
)
async def test_hierarchy_members_are_declared_once(test_case: HierarchyTestCase) -> None:
    """A hierarchical kind declares `parent` and `children` exactly once.

    Both come from the hierarchy unless the schema already exposes them as relationships, which
    it does for anything read from the API. Emitting either one twice is not a type error, so a
    duplicate silently overrides the first declaration with whatever the second one says.
    """
    relationships = [
        RelationshipSchemaAPI(
            name=name,
            peer="LocationSite",
            cardinality=RelationshipCardinality.ONE if name == "parent" else RelationshipCardinality.MANY,
        )
        for name in test_case.declared_relationships
    ]
    generic = GenericSchemaAPI(name="Site", namespace="Location", hierarchical=True, relationships=relationships)

    rendered = CodeGenerator(schema={"LocationSite": generic}).render(sync=False)

    body = rendered[rendered.index("class LocationSite") :]
    assert body.count("parent:") == 1
    assert body.count("children:") == 1


async def test_render_sdk_core_emits_both_variants(client: InfrahubClient, mock_schema_query_05: "HTTPXMock") -> None:
    """Generating infrahub_sdk.protocols itself puts both variants in one module.

    Every kind is local there, so the module cannot import the kinds it defines, the sync classes
    need a suffix to keep their names distinct, and a peer has to be referenced by its own sync
    class rather than by an imported one.
    """
    schemas = await client.schema.fetch(branch="main")

    rendered = CodeGenerator(schema=schemas, target=ProtocolTarget.SDK_CORE).render()

    assert "from infrahub_sdk.protocols import" not in rendered
    assert "from .protocols_base import CoreNode, CoreNodeSync" in rendered

    assert "class LocationGeneric(CoreNode):" in rendered
    assert "class LocationGenericSync(CoreNodeSync):" in rendered
    assert "class LocationSite(LocationGeneric):" in rendered
    assert "class LocationSiteSync(LocationGenericSync):" in rendered

    assert "parent: RelationshipAttribute[LocationCountry]" in rendered
    assert "parent: RelationshipAttributeSync[LocationCountrySync]" in rendered


async def test_render_sdk_core_ignores_sync_argument(client: InfrahubClient, mock_schema_query_05: "HTTPXMock") -> None:
    """The async/sync choice does not apply when both variants land in the same module."""
    schemas = await client.schema.fetch(branch="main")
    generator = CodeGenerator(schema=schemas, target=ProtocolTarget.SDK_CORE)

    assert generator.render(sync=True) == generator.render(sync=False)
