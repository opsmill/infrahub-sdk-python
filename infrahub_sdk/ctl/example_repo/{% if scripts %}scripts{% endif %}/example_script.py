import logging

from lib.example import print_nodes

from infrahub_sdk import InfrahubClient


async def run(
    client: InfrahubClient,
    log: logging.Logger,
    branch: str,
):
    log.info(f"Running example script on {branch}...")
    nodes = await client.schema.all()
    print_nodes(log, nodes)
