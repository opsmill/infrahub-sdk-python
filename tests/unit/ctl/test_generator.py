from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from infrahub_sdk.client import InfrahubClient
from infrahub_sdk.config import Config
from infrahub_sdk.ctl import generator as generator_module
from infrahub_sdk.node import InfrahubNode
from infrahub_sdk.schema import AttributeSchemaAPI, NodeSchemaAPI
from infrahub_sdk.schema.main import AttributeKind
from infrahub_sdk.schema.repository import InfrahubGeneratorDefinitionConfig, InfrahubRepositoryConfig

QUERY_RESULT = {"data": {"FirewallRules": {"edges": []}}}


@dataclass
class ExecutedQuery:
    """A call the CLI made to the GraphQL query."""

    name: str
    variables: dict[str, Any]


@dataclass
class GeneratorRun:
    """A generator the CLI instantiated and ran for one target."""

    identifier: str
    params: dict[str, Any]
    data: dict


@dataclass
class CliHarness:
    """Replaces everything `infrahubctl generator` talks to and records what it did.

    Members are read when the CLI asks for them, so a test can set them after the harness
    is installed.
    """

    definition: InfrahubGeneratorDefinitionConfig
    members: list[InfrahubNode] = field(default_factory=list)
    queries: list[ExecutedQuery] = field(default_factory=list)
    runs: list[GeneratorRun] = field(default_factory=list)

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(generator_module, "find_repository_config_file", lambda: Path(".infrahub.yml"))
        monkeypatch.setattr(generator_module, "get_repository_config", self._repository_config)
        monkeypatch.setattr(generator_module, "execute_graphql_query", self._execute_graphql_query)
        monkeypatch.setattr(generator_module, "initialize_client", self._initialize_client)
        monkeypatch.setattr(InfrahubGeneratorDefinitionConfig, "load_class", self._load_class)

    def _repository_config(self, config_file: Path) -> InfrahubRepositoryConfig:
        return InfrahubRepositoryConfig(generator_definitions=[self.definition])

    def _initialize_client(self, branch: str | None = None) -> StubClient:
        return StubClient(harness=self)

    def _load_class(self, *args: object, **kwargs: object) -> type[RecordingGenerator]:
        harness = self

        class BoundGenerator(RecordingGenerator):
            _harness = harness

        return BoundGenerator

    def _execute_graphql_query(
        self,
        query: str,
        variables_dict: dict[str, Any],
        repository_config: InfrahubRepositoryConfig,
        branch: str | None = None,
        debug: bool = False,
    ) -> dict:
        self.queries.append(ExecutedQuery(name=query, variables=variables_dict))
        return QUERY_RESULT


class RecordingGenerator:
    """Stands in for the generator class the CLI imports from the repository.

    The signature mirrors the call in `ctl/generator.py`, so a change there fails here.
    """

    _harness: CliHarness

    def __init__(
        self,
        query: str,
        client: InfrahubClient,
        branch: str,
        params: dict[str, Any],
        convert_query_response: bool,
        execute_in_proposed_change: bool,
        execute_after_merge: bool,
        infrahub_node: type[InfrahubNode],
    ) -> None:
        self.params = params
        self.branch_name = branch
        self._init_client = StubSchemaClient()

    async def run(self, identifier: str, data: dict) -> None:
        self._harness.runs.append(GeneratorRun(identifier=identifier, params=self.params, data=data))


class StubSchema:
    async def all(self, branch: str | None = None) -> None:
        return None


class StubSchemaClient:
    def __init__(self) -> None:
        self.schema = StubSchema()


@dataclass
class StubRelatedNode:
    peer: InfrahubNode


class StubRelationship:
    def __init__(self, peers: list[StubRelatedNode]) -> None:
        self.peers = peers

    async def fetch(self) -> None:
        return None


class StubGroup:
    """The CoreGroup node the CLI fetches by name."""

    def __init__(self, members: list[InfrahubNode]) -> None:
        self.relationship = StubRelationship(peers=[StubRelatedNode(peer=member) for member in members])

    def _get_relationship_many(self, name: str) -> StubRelationship:
        assert name == "members"
        return self.relationship


class StubClient:
    def __init__(self, harness: CliHarness) -> None:
        self.harness = harness

    async def get(self, **kwargs: object) -> StubGroup:
        return StubGroup(members=self.harness.members)


@pytest.fixture
async def node_client() -> InfrahubClient:
    """Client the test nodes are bound to, not the one the CLI uses."""
    return InfrahubClient(config=Config(address="http://mock"))


@pytest.fixture
async def rule_schema() -> NodeSchemaAPI:
    """A kind with no name attribute, identified by another attribute."""
    return NodeSchemaAPI(
        name="Rules",
        namespace="Firewall",
        human_friendly_id=["rule_id__value"],
        attributes=[
            AttributeSchemaAPI(name="rule_id", kind=AttributeKind.NUMBER, unique=True),
            AttributeSchemaAPI(name="status", kind=AttributeKind.TEXT),
        ],
    )


@pytest.fixture
def generator_definition() -> InfrahubGeneratorDefinitionConfig:
    return InfrahubGeneratorDefinitionConfig(
        name="process_pending_rules",
        file_path=Path("generators/process_pending.py"),
        query="pending_rules_context",
        targets="pending-firewall-rules",
        parameters={"rule_id": "rule_id__value"},
    )


@pytest.fixture
def cli(monkeypatch: pytest.MonkeyPatch, generator_definition: InfrahubGeneratorDefinitionConfig) -> CliHarness:
    harness = CliHarness(definition=generator_definition)
    harness.install(monkeypatch=monkeypatch)
    return harness


def build_rule(client: InfrahubClient, schema: NodeSchemaAPI, node_id: str, rule_id: int, status: str) -> InfrahubNode:
    return InfrahubNode(
        client=client,
        schema=schema,
        data={"id": node_id, "rule_id": {"value": rule_id}, "status": {"value": status}},
    )


async def run_cli(variables: list[str] | None = None) -> None:
    await generator_module.run(
        generator_name="process_pending_rules",
        path=".",
        debug=False,
        list_available=False,
        variables=variables,
    )


async def test_runs_a_target_kind_without_a_name_attribute(
    cli: CliHarness, node_client: InfrahubClient, rule_schema: NodeSchemaAPI
) -> None:
    """The reported failure: a target with no name attribute used to abort the whole run."""
    cli.members = [
        build_rule(client=node_client, schema=rule_schema, node_id="5d2c0f96", rule_id=12345, status="draft")
    ]

    await run_cli()

    assert cli.runs == [GeneratorRun(identifier="process_pending_rules", params={"rule_id": 12345}, data=QUERY_RESULT)]
    assert cli.queries == [ExecutedQuery(name="pending_rules_context", variables={"rule_id": 12345})]


async def test_gives_each_member_its_own_params(
    cli: CliHarness, node_client: InfrahubClient, rule_schema: NodeSchemaAPI
) -> None:
    """Params identify the tracking group, so members must not share them."""
    cli.members = [
        build_rule(client=node_client, schema=rule_schema, node_id="5d2c0f96", rule_id=12345, status="draft"),
        build_rule(client=node_client, schema=rule_schema, node_id="7a1b2c3d", rule_id=67890, status="draft"),
    ]

    await run_cli()

    assert [run.params for run in cli.runs] == [{"rule_id": 12345}, {"rule_id": 67890}]


async def test_resolves_every_declared_parameter(
    cli: CliHarness, node_client: InfrahubClient, rule_schema: NodeSchemaAPI
) -> None:
    """Every entry of the parameters mapping is resolved, not only the first one."""
    cli.definition.parameters = {"rule_id": "rule_id__value", "status": "status__value"}
    cli.members = [
        build_rule(client=node_client, schema=rule_schema, node_id="5d2c0f96", rule_id=12345, status="draft")
    ]

    await run_cli()

    assert [run.params for run in cli.runs] == [{"rule_id": 12345, "status": "draft"}]


async def test_does_not_run_when_the_group_is_empty(cli: CliHarness) -> None:
    await run_cli()

    assert cli.runs == []
    assert cli.queries == []


async def test_variables_given_on_the_command_line_bypass_the_group(cli: CliHarness) -> None:
    """Variables passed as key=value run the generator once, without looking at the group."""
    await run_cli(variables=["rule_id=12345"])

    assert cli.runs == [
        GeneratorRun(identifier="process_pending_rules", params={"rule_id": "12345"}, data=QUERY_RESULT)
    ]
    assert cli.queries == [ExecutedQuery(name="pending_rules_context", variables={"rule_id": "12345"})]
