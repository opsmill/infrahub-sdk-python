import logging

from infrahub_sdk.node import InfrahubNode


def print_nodes(log: logging.Logger, nodes: list[InfrahubNode]):
    for node in nodes.keys():
        log.info(f"{node} present.")
