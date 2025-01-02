from infrahub_sdk import InfrahubClient
from infrahub_sdk.node import InfrahubNode


async def group_add_subscriber(
    client: InfrahubClient, group: InfrahubNode, subscribers: list[str], branch: str
) -> dict:
    subscribers_str = ["{ id: " + f'"{subscriber}"' + " }" for subscriber in subscribers]
    query = """
    mutation {
        RelationshipAdd(
            data: {
                id: "%s",
                name: "subscribers",
                nodes: [ %s ]
            }
        ) {
            ok
        }
    }
    """ % (
        group.id,
        ", ".join(subscribers_str),
    )

    return await client.execute_graphql(query=query, branch_name=branch, tracker="mutation-relationshipadd")
