import pytest

from infrahub_sdk import InfrahubClient
from infrahub_sdk.exceptions import BranchNotFoundError
from infrahub_sdk.testing.docker import TestInfrahubDockerClient


# from infrahub.core.schema import core_models
# from infrahub.server import app
#
# from infrahub_sdk.schema import NodeSchemaAPI
#
# from .conftest import InfrahubTestClient
#
#
#
class TestInfrahubSchema(TestInfrahubDockerClient):
    async def test_query_schema_for_branch_not_found(self, client: InfrahubClient):
        with pytest.raises(BranchNotFoundError) as exc:
            await client.all(kind="BuiltinTag", branch="I-do-not-exist")

        assert str(exc.value) == "The requested branch was not found on the server [I-do-not-exist]"


# class TestInfrahubSchema:
#     @pytest.fixture(scope="class")
#     async def client(self):
#         return InfrahubTestClient(app)
#
#     async def test_schema_all(self, client, init_db_base):
#         config = Config(requester=client.async_request)
#         ifc = InfrahubClient(config=config)
#         schema_nodes = await ifc.schema.all()
#
#         nodes = [node for node in core_models["nodes"] if node["namespace"] != "Internal"]
#         generics = [node for node in core_models["generics"] if node["namespace"] != "Internal"]
#
#         profiles = [node for node in schema_nodes.values() if node.namespace == "Profile"]
#         assert profiles
#
#         assert len(schema_nodes) == len(nodes) + len(generics) + len(profiles)
#         assert "BuiltinTag" in schema_nodes
#         assert isinstance(schema_nodes["BuiltinTag"], NodeSchemaAPI)
#
#     async def test_schema_get(self, client, init_db_base):
#         config = Config(username="admin", password="infrahub", requester=client.async_request)
#         ifc = InfrahubClient(config=config)
#         schema_node = await ifc.schema.get(kind="BuiltinTag")
#
#         assert isinstance(schema_node, NodeSchemaAPI)
#         assert ifc.default_branch in ifc.schema.cache
#         nodes = [node for node in core_models["nodes"] if node["namespace"] != "Internal"]
#         generics = [node for node in core_models["generics"] if node["namespace"] != "Internal"]
#
#         schema_without_profiles = [
#             node for node in ifc.schema.cache[ifc.default_branch].values() if node.namespace != "Profile"
#         ]
#         assert len(schema_without_profiles) == len(nodes) + len(generics)
#
#     async def test_schema_load_many(self, client, init_db_base, schema_extension_01, schema_extension_02):
#         config = Config(username="admin", password="infrahub", requester=client.async_request)
#         ifc = InfrahubClient(config=config)
#         response = await ifc.schema.load(schemas=[schema_extension_01, schema_extension_02])
#
#         assert response.schema_updated
#
#         schema_nodes = await ifc.schema.all(refresh=True)
#         assert "InfraRack" in schema_nodes.keys()
#         assert "ProcurementContract" in schema_nodes.keys()
