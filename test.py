from infrahub_sdk import InfrahubClientSync
from infrahub_sdk.types import NodeMetaOrder, Order
from infrahub_sdk.enums import OrderDirection

client = InfrahubClientSync()

tags = client.all("BuiltinTag", include_metadata=True, order=Order(node_metadata=NodeMetaOrder(updated_at=OrderDirection.DESC)))

for tag in tags:
    # print(f"Tag: {tag.name.value}")
    metadata = tag.get_node_metadata()
    print(f"{tag.name.value} - Last updated: {metadata.updated_at}")