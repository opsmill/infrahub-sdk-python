from infrahub_sdk import InfrahubClient
from infrahub_sdk.node import InfrahubNode


async def group_add_subscriber(
    client: InfrahubClient, group: InfrahubNode, subscribers: list[str], branch: str
) -> dict:
    subscribers_str = ["{ id: " + f'"{subscriber}"' + " }" for subscriber in subscribers]
    query = f"""
    mutation {{
        RelationshipAdd(
            data: {{
                id: "{group.id}",
                name: "subscribers",
                nodes: [ {", ".join(subscribers_str)} ]
            }}
        ) {{
            ok
        }}
    }}
    """

    return await client.execute_graphql(query=query, branch_name=branch, tracker="mutation-relationshipadd")
