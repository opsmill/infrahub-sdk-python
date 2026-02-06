import pytest

from infrahub_sdk import InfrahubClient, InfrahubClientSync
from infrahub_sdk.exceptions import GraphQLError
from infrahub_sdk.node import InfrahubNode, InfrahubNodeSync
from infrahub_sdk.schema.main import AttributeKind, NodeSchema, RelationshipKind, SchemaRoot
from infrahub_sdk.schema.main import AttributeSchema as Attr
from infrahub_sdk.schema.main import RelationshipSchema as Rel

NAMESPACE = "Testing"
TESTING_FILE_CONTRACT = f"{NAMESPACE}FileContract"
TESTING_CIRCUIT = f"{NAMESPACE}Circuit"

PDF_MAGIC_BYTES = b"%PDF-1.4 fake pdf content for testing"
PNG_MAGIC_BYTES = b"\x89PNG\r\n\x1a\n fake png content for testing"
TEXT_CONTENT = b"This is a simple text file content for testing purposes."


class SchemaFileObject:
    @pytest.fixture(scope="class")
    def schema_file_contract(self) -> NodeSchema:
        return NodeSchema(
            name="FileContract",
            namespace=NAMESPACE,
            include_in_menu=True,
            inherit_from=["CoreFileObject"],
            display_label="file_name__value",
            human_friendly_id=["contract_ref__value"],
            order_by=["contract_ref__value"],
            attributes=[
                Attr(name="contract_ref", kind=AttributeKind.TEXT, unique=True),
                Attr(name="description", kind=AttributeKind.TEXT, optional=True),
                Attr(name="active", kind=AttributeKind.BOOLEAN, default_value=True, optional=True),
            ],
            relationships=[
                Rel(
                    name="circuit",
                    kind=RelationshipKind.ATTRIBUTE,
                    optional=True,
                    peer=TESTING_CIRCUIT,
                    cardinality="one",
                    identifier="circuit__contracts",
                ),
            ],
        )

    @pytest.fixture(scope="class")
    def schema_circuit(self) -> NodeSchema:
        return NodeSchema(
            name="Circuit",
            namespace=NAMESPACE,
            include_in_menu=True,
            display_label="circuit_id__value",
            human_friendly_id=["circuit_id__value"],
            order_by=["circuit_id__value"],
            attributes=[
                Attr(name="circuit_id", kind=AttributeKind.TEXT, unique=True),
                Attr(name="bandwidth", kind=AttributeKind.NUMBER, optional=True),
            ],
            relationships=[
                Rel(
                    name="contracts",
                    kind=RelationshipKind.GENERIC,
                    optional=True,
                    peer=TESTING_FILE_CONTRACT,
                    cardinality="many",
                    identifier="circuit__contracts",
                ),
            ],
        )

    @pytest.fixture(scope="class")
    def schema_file_object_base(self, schema_file_contract: NodeSchema, schema_circuit: NodeSchema) -> SchemaRoot:
        return SchemaRoot(version="1.0", nodes=[schema_file_contract, schema_circuit])

    @pytest.fixture(scope="class")
    async def load_file_object_schema(self, client: InfrahubClient, schema_file_object_base: SchemaRoot) -> None:
        resp = await client.schema.load(schemas=[schema_file_object_base.to_schema_dict()], wait_until_converged=True)
        if resp.errors:
            raise GraphQLError(errors=[resp.errors])

    @pytest.fixture(scope="class")
    def load_file_object_schema_sync(
        self, client_sync: InfrahubClientSync, schema_file_object_base: SchemaRoot
    ) -> None:
        resp = client_sync.schema.load(schemas=[schema_file_object_base.to_schema_dict()], wait_until_converged=True)
        if resp.errors:
            raise GraphQLError(errors=[resp.errors])

    @pytest.fixture(scope="class")
    async def circuit_main(
        self,
        client: InfrahubClient,
        load_file_object_schema: None,  # noqa: ARG002
    ) -> InfrahubNode:
        obj = await client.create(kind=TESTING_CIRCUIT, circuit_id="CIRCUIT-001", bandwidth=1000)
        await obj.save()
        return obj

    @pytest.fixture(scope="class")
    def circuit_main_sync(
        self,
        client_sync: InfrahubClientSync,
        load_file_object_schema_sync: None,  # noqa: ARG002
    ) -> InfrahubNodeSync:
        obj = client_sync.create(kind=TESTING_CIRCUIT, circuit_id="CIRCUIT-SYNC-001", bandwidth=2000)
        obj.save()
        return obj
