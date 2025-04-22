from infrahub_sdk import InfrahubClient
from infrahub_sdk.node import InfrahubNode
from typing import List
import logging


def print_nodes(client: InfrahubClient, log: logging.Logger, nodes: List[InfrahubNode]):
    for node in nodes.keys():
        log.info(f"{node} present.")
