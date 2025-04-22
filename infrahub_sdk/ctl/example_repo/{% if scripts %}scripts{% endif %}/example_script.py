import logging

from infrahub_sdk import InfrahubClient
from lib.example import print_nodes


async def run(
    client: InfrahubClient,
    log: logging.Logger,
    branch: str,
):
    log.info("Running example script...")
    nodes = await client.schema.all()
    print_nodes(client, log, nodes)
