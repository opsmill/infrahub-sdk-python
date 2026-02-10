import pytest

from infrahub_sdk import InfrahubClient, InfrahubClientSync
from infrahub_sdk.schema.main import AttributeKind, NodeSchema, SchemaRoot
from infrahub_sdk.schema.main import AttributeSchema as Attr

NAMESPACE = "Testing"
TESTING_FILE_CONTRACT = f"{NAMESPACE}FileContract"

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
        )

    @pytest.fixture(scope="class")
    def schema_file_object_base(self, schema_file_contract: NodeSchema) -> SchemaRoot:
        return SchemaRoot(version="1.0", nodes=[schema_file_contract])

    @pytest.fixture(scope="class")
    async def load_file_object_schema(self, client: InfrahubClient, schema_file_object_base: SchemaRoot) -> None:
        await client.schema.load(schemas=[schema_file_object_base.to_schema_dict()], wait_until_converged=True)

    @pytest.fixture(scope="class")
    def load_file_object_schema_sync(
        self, client_sync: InfrahubClientSync, schema_file_object_base: SchemaRoot
    ) -> None:
        client_sync.schema.load(schemas=[schema_file_object_base.to_schema_dict()], wait_until_converged=True)
