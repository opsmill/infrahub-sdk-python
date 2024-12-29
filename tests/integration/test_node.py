import pytest

from infrahub_sdk import InfrahubClient
from infrahub_sdk.exceptions import NodeNotFoundError
from infrahub_sdk.node import InfrahubNode
from infrahub_sdk.schema import NodeSchema, NodeSchemaAPI, SchemaRoot
from infrahub_sdk.testing.docker import TestInfrahubDockerClient
from infrahub_sdk.testing.schemas.car_person import TESTING_MANUFACTURER, TESTING_CAR, TESTING_PERSON, SchemaCarPerson

# pylint: disable=unused-argument


class TestInfrahubNode(TestInfrahubDockerClient, SchemaCarPerson):
    @pytest.fixture(scope="class")
    def infrahub_version(self) -> str:
        return "1.0.10"

    @pytest.fixture(scope="class")
    async def initial_schema(self, default_branch: str, client: InfrahubClient, schema_base: SchemaRoot) -> None:
        await client.schema.wait_until_converged(branch=default_branch)

        resp = await client.schema.load(
            schemas=[schema_base.to_schema_dict()], branch=default_branch, wait_until_converged=True
        )
        assert resp.errors == {}

    async def test_node_create(
        self, client: InfrahubClient, initial_schema: None, schema_manufacturer_base: NodeSchema
    ):
        schema_manufacturer = NodeSchemaAPI(**schema_manufacturer_base.model_dump(exclude_unset=True))
        data = {
            "name": {"value": "Fiat"},
            "description": {"value": "An italian brand"},
        }
        node = InfrahubNode(client=client, schema=schema_manufacturer, data=data)
        await node.save()

        assert node.id is not None

    async def test_node_delete(
        self,
        default_branch: str,
        client: InfrahubClient,
        initial_schema: None,
    ):
        await self.create_manufacturers(client=client, branch=default_branch)

        obj: InfrahubNode = client.store.get_by_hfid(key=f"{TESTING_MANUFACTURER}__Volkswagen")
        await obj.delete()

        with pytest.raises(NodeNotFoundError):
            await client.get(kind=TESTING_MANUFACTURER, id=obj.id)

    async def test_node_create_with_relationships(
        self,
        default_branch: str,
        client: InfrahubClient,
        initial_schema: None,
        person_john: InfrahubNode,
        manufacturer_vw: InfrahubNode,
    ):
        data = {
            "name": {"value": "Golf"},
            "color": { "value": "Blue"},
            "owner": person_john.id,
            "manufacturer": manufacturer_vw.id
        }

        with pytest.raises(NodeNotFoundError):
            node_after = await client.get(kind=TESTING_CAR, name__value="Golf")

        node = await client.create(kind=TESTING_CAR, data=data)
        await node.save()

        assert node.id is not None

        node_after = await client.get(kind=TESTING_CAR, id=node.id)
        assert node_after.id == node.id

    # async def test_node_update_payload_with_relationships(
    #     self,
    #     db: InfrahubDatabase,
    #     client: InfrahubClient,
    #     init_db_base,
    #     load_builtin_schema,
    #     tag_blue: Node,
    #     tag_red: Node,
    #     repo01: Node,
    #     gqlquery01: Node,
    # ):
    #     data = {
    #         "name": "rfile10",
    #         "template_path": "mytemplate.j2",
    #         "query": gqlquery01.id,
    #         "repository": repo01.id,
    #         "tags": [tag_blue.id, tag_red.id],
    #     }
    #     schema = await client.schema.get(kind="CoreTransformJinja2", branch="main")
    #     create_payload = client.schema.generate_payload_create(
    #         schema=schema, data=data, source=repo01.id, is_protected=True
    #     )
    #     obj = await client.create(kind="CoreTransformJinja2", branch="main", **create_payload)
    #     await obj.save()

    #     assert obj.id is not None
    #     nodedb = await client.get(kind="CoreTransformJinja2", id=str(obj.id))

    #     input_data = nodedb._generate_input_data()["data"]["data"]
    #     assert input_data["name"]["value"] == "rfile10"
    #     # Validate that the source isn't a dictionary bit a reference to the repo
    #     assert input_data["name"]["source"] == repo01.id

    # async def test_node_create_with_properties(
    #     self,
    #     db: InfrahubDatabase,
    #     client: InfrahubClient,
    #     init_db_base,
    #     load_builtin_schema,
    #     tag_blue: Node,
    #     tag_red: Node,
    #     repo01: Node,
    #     gqlquery01: Node,
    #     first_account: Node,
    # ):
    #     data = {
    #         "name": {
    #             "value": "rfile02",
    #             "is_protected": True,
    #             "source": first_account.id,
    #             "owner": first_account.id,
    #         },
    #         "template_path": {"value": "mytemplate.j2"},
    #         "query": {"id": gqlquery01.id},  # "source": first_account.id, "owner": first_account.id},
    #         "repository": {"id": repo01.id},  # "source": first_account.id, "owner": first_account.id},
    #         "tags": [tag_blue.id, tag_red.id],
    #     }

    #     node = await client.create(kind="CoreTransformJinja2", data=data)
    #     await node.save()

    #     assert node.id is not None

    #     nodedb = await NodeManager.get_one(id=node.id, db=db, include_owner=True, include_source=True)
    #     assert nodedb.name.value == node.name.value  # type: ignore[attr-defined]
    #     assert nodedb.name.is_protected is True

    # async def test_node_update(
    #     self,
    #     db: InfrahubDatabase,
    #     client: InfrahubClient,
    #     init_db_base,
    #     load_builtin_schema,
    #     tag_blue: Node,
    #     tag_red: Node,
    #     repo99: Node,
    # ):
    #     node = await client.get(kind="CoreRepository", name__value="repo99")
    #     assert node.id is not None

    #     node.name.value = "repo95"  # type: ignore[attr-defined]
    #     node.tags.add(tag_blue.id)  # type: ignore[attr-defined]
    #     node.tags.add(tag_red.id)  # type: ignore[attr-defined]
    #     await node.save()

    #     nodedb = await NodeManager.get_one(id=node.id, db=db, include_owner=True, include_source=True)
    #     assert nodedb.name.value == "repo95"
    #     tags = await nodedb.tags.get(db=db)
    #     assert len(tags) == 2

    # async def test_node_update_2(
    #     self,
    #     db: InfrahubDatabase,
    #     client: InfrahubClient,
    #     init_db_base,
    #     load_builtin_schema,
    #     tag_green: Node,
    #     tag_red: Node,
    #     tag_blue: Node,
    #     gqlquery02: Node,
    #     repo99: Node,
    # ):
    #     node = await client.get(kind="CoreGraphQLQuery", name__value="query02")
    #     assert node.id is not None

    #     node.name.value = "query021"  # type: ignore[attr-defined]
    #     node.repository = repo99.id  # type: ignore[attr-defined]
    #     node.tags.add(tag_green.id)  # type: ignore[attr-defined]
    #     node.tags.remove(tag_red.id)  # type: ignore[attr-defined]
    #     await node.save()

    #     nodedb = await NodeManager.get_one(id=node.id, db=db, include_owner=True, include_source=True)
    #     repodb = await nodedb.repository.get_peer(db=db)
    #     assert repodb.id == repo99.id

    #     tags = await nodedb.tags.get(db=db)
    #     assert sorted([tag.peer_id for tag in tags]) == sorted([tag_green.id, tag_blue.id])

    # async def test_node_update_3_idempotency(
    #     self,
    #     db: InfrahubDatabase,
    #     client: InfrahubClient,
    #     init_db_base,
    #     load_builtin_schema,
    #     tag_green: Node,
    #     tag_red: Node,
    #     tag_blue: Node,
    #     gqlquery03: Node,
    #     repo99: Node,
    # ):
    #     node = await client.get(kind="CoreGraphQLQuery", name__value="query03")
    #     assert node.id is not None

    #     updated_query = f"\n\n{node.query.value}"  # type: ignore[attr-defined]
    #     node.name.value = "query031"  # type: ignore[attr-defined]
    #     node.query.value = updated_query  # type: ignore[attr-defined]
    #     first_update = node._generate_input_data(exclude_unmodified=True)
    #     await node.save()
    #     nodedb = await NodeManager.get_one(id=node.id, db=db, include_owner=True, include_source=True)

    #     node = await client.get(kind="CoreGraphQLQuery", name__value="query031")

    #     node.name.value = "query031"  # type: ignore[attr-defined]
    #     node.query.value = updated_query  # type: ignore[attr-defined]

    #     second_update = node._generate_input_data(exclude_unmodified=True)

    #     assert nodedb.query.value == updated_query  # type: ignore[attr-defined]
    #     assert "query" in first_update["data"]["data"]
    #     assert "value" in first_update["data"]["data"]["query"]
    #     assert first_update["variables"]
    #     assert "query" not in second_update["data"]["data"]
    #     assert not second_update["variables"]

    # async def test_convert_node(
    #     self,
    #     db: InfrahubDatabase,
    #     client: InfrahubClient,
    #     location_schema,
    #     init_db_base,
    #     load_builtin_schema,
    #     location_cdg: Node,
    # ):
    #     data = await location_cdg.to_graphql(db=db)
    #     node = InfrahubNode(client=client, schema=location_schema, data=data)

    #     # pylint: disable=no-member
    #     assert node.name.value == "cdg01"  # type: ignore[attr-defined]

    # async def test_relationship_manager_errors_without_fetch(self, client: InfrahubClient, load_builtin_schema):
    #     organization = await client.create("TestOrganization", name="organization-1")
    #     await organization.save()
    #     tag = await client.create("BuiltinTag", name="blurple")
    #     await tag.save()

    #     with pytest.raises(UninitializedError, match=r"Must call fetch"):
    #         organization.tags.add(tag)

    #     await organization.tags.fetch()
    #     organization.tags.add(tag)
    #     await organization.save()

    #     organization = await client.get("TestOrganization", name__value="organization-1")
    #     assert [t.id for t in organization.tags.peers] == [tag.id]

    # async def test_relationships_not_overwritten(
    #     self, client: InfrahubClient, load_builtin_schema, schema_extension_01
    # ):
    #     await client.schema.load(schemas=[schema_extension_01])
    #     rack = await client.create("InfraRack", name="rack-1")
    #     await rack.save()
    #     tag = await client.create("BuiltinTag", name="blizzow")
    #     # TODO: is it a bug that we need to save the object and fetch the tags before adding to a RelationshipManager now?
    #     await tag.save()
    #     await tag.racks.fetch()
    #     tag.racks.add(rack)
    #     await tag.save()
    #     tag_2 = await client.create("BuiltinTag", name="blizzow2")
    #     await tag_2.save()

    #     # the "rack" object has no link to the "tag" object here
    #     # rack.tags.peers is empty
    #     rack.name.value = "New Rack Name"
    #     await rack.save()

    #     # assert that the above rack.save() did not overwrite the existing Rack-Tag relationship
    #     refreshed_rack = await client.get("InfraRack", id=rack.id)
    #     await refreshed_rack.tags.fetch()
    #     assert [t.id for t in refreshed_rack.tags.peers] == [tag.id]

    #     # check that we can purposefully remove a tag
    #     refreshed_rack.tags.remove(tag.id)
    #     await refreshed_rack.save()
    #     rack_without_tag = await client.get("InfraRack", id=rack.id)
    #     await rack_without_tag.tags.fetch()
    #     assert rack_without_tag.tags.peers == []

    #     # check that we can purposefully add a tag
    #     rack_without_tag.tags.add(tag_2)
    #     await rack_without_tag.save()
    #     refreshed_rack_with_tag = await client.get("InfraRack", id=rack.id)
    #     await refreshed_rack_with_tag.tags.fetch()
    #     assert [t.id for t in refreshed_rack_with_tag.tags.peers] == [tag_2.id]

    # async def test_node_create_from_pool(
    #     self, db: InfrahubDatabase, client: InfrahubClient, init_db_base, default_ipam_namespace, load_ipam_schema
    # ):
    #     ip_prefix = await client.create(kind="IpamIPPrefix", prefix="192.0.2.0/24")
    #     await ip_prefix.save()

    #     ip_pool = await client.create(
    #         kind="CoreIPAddressPool",
    #         name="Core loopbacks 1",
    #         default_address_type="IpamIPAddress",
    #         default_prefix_length=32,
    #         ip_namespace=default_ipam_namespace,
    #         resources=[ip_prefix],
    #     )
    #     await ip_pool.save()

    #     devices = []
    #     for i in range(1, 5):
    #         d = await client.create(kind="InfraDevice", name=f"core0{i}", primary_address=ip_pool)
    #         await d.save()
    #         devices.append(d)

    #     assert [str(device.primary_address.peer.address.value) for device in devices] == [
    #         "192.0.2.1/32",
    #         "192.0.2.2/32",
    #         "192.0.2.3/32",
    #         "192.0.2.4/32",
    #     ]

    # async def test_node_update_from_pool(
    #     self, db: InfrahubDatabase, client: InfrahubClient, init_db_base, default_ipam_namespace, load_ipam_schema
    # ):
    #     starter_ip_address = await client.create(kind="IpamIPAddress", address="10.0.0.1/32")
    #     await starter_ip_address.save()

    #     ip_prefix = await client.create(kind="IpamIPPrefix", prefix="192.168.0.0/24")
    #     await ip_prefix.save()

    #     ip_pool = await client.create(
    #         kind="CoreIPAddressPool",
    #         name="Core loopbacks 2",
    #         default_address_type="IpamIPAddress",
    #         default_prefix_length=32,
    #         ip_namespace=default_ipam_namespace,
    #         resources=[ip_prefix],
    #     )
    #     await ip_pool.save()

    #     device = await client.create(kind="InfraDevice", name="core05", primary_address=starter_ip_address)
    #     await device.save()

    #     device.primary_address = ip_pool
    #     await device.save()

    #     assert str(device.primary_address.peer.address.value) == "192.168.0.1/32"
