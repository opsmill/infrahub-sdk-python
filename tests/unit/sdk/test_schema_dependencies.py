from __future__ import annotations

from infrahub_sdk.schema.dependencies import DeletionOrder, PeerLookup
from tests.helpers.schemas import mandatory, node_schema, node_schemas

TARGET_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
DEPENDENT_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
CHAIN_IDS = [
    "c1c1c1c1-c1c1-c1c1-c1c1-c1c1c1c1c1c1",
    "c2c2c2c2-c2c2-c2c2-c2c2-c2c2c2c2c2c2",
    "c3c3c3c3-c3c3-c3c3-c3c3-c3c3c3c3c3c3",
]


def test_deletion_order_deletes_the_holder_before_the_node_it_holds() -> None:
    """Group order is creation order, so the node that is held comes first and must be moved last."""
    schemas = node_schemas(
        node_schema("Target"), node_schema("Dependent", relationships=[mandatory("target", "ReproTarget")])
    )
    order = DeletionOrder(candidates=[("ReproTarget", TARGET_ID), ("ReproDependent", DEPENDENT_ID)], schemas=schemas)

    assert order.peer_lookups == []
    assert order.order() == [("ReproDependent", DEPENDENT_ID), ("ReproTarget", TARGET_ID)]


def test_deletion_order_resolves_a_generic_peer_to_the_kinds_inheriting_it() -> None:
    schemas = node_schemas(
        node_schema("Address", inherit_from=["ReproEndpoint"]),
        node_schema("Session", relationships=[mandatory("src", "ReproEndpoint")]),
    )
    order = DeletionOrder(candidates=[("ReproAddress", TARGET_ID), ("ReproSession", DEPENDENT_ID)], schemas=schemas)

    assert order.order() == [("ReproSession", DEPENDENT_ID), ("ReproAddress", TARGET_ID)]


def test_deletion_order_follows_a_chain_of_kinds() -> None:
    schemas = node_schemas(
        node_schema("First"),
        node_schema("Second", relationships=[mandatory("first", "ReproFirst")]),
        node_schema("Third", relationships=[mandatory("second", "ReproSecond")]),
    )
    candidates = [("ReproFirst", CHAIN_IDS[0]), ("ReproSecond", CHAIN_IDS[1]), ("ReproThird", CHAIN_IDS[2])]

    assert DeletionOrder(candidates=candidates, schemas=schemas).order() == candidates[::-1]


def test_deletion_order_ignores_optional_relationships() -> None:
    schemas = node_schemas(
        node_schema("Target"),
        node_schema("Dependent", relationships=[{"name": "target", "peer": "ReproTarget", "optional": True}]),
    )
    candidates = [("ReproTarget", TARGET_ID), ("ReproDependent", DEPENDENT_ID)]

    assert DeletionOrder(candidates=candidates, schemas=schemas).order() == candidates


def test_deletion_order_orders_members_of_the_same_kind_by_their_peers() -> None:
    """Each chain link holds the previous one, so the last created is deleted first."""
    schemas = node_schemas(node_schema("Chain", relationships=[mandatory("previous", "ReproChain")]))
    candidates = [("ReproChain", member_id) for member_id in CHAIN_IDS]
    order = DeletionOrder(candidates=candidates, schemas=schemas)

    assert order.peer_lookups == [PeerLookup(kind="ReproChain", ids=CHAIN_IDS, relationships={"previous": False})]
    member_peers = {CHAIN_IDS[1]: {CHAIN_IDS[0]}, CHAIN_IDS[2]: {CHAIN_IDS[1]}}
    assert order.order(node_peers=member_peers) == candidates[::-1]


def test_deletion_order_orders_kinds_that_hold_each_other_by_their_peers() -> None:
    schemas = node_schemas(
        node_schema("Left", relationships=[mandatory("rights", "ReproRight", cardinality="many")]),
        node_schema("Right", relationships=[mandatory("lefts", "ReproLeft", cardinality="many")]),
    )
    candidates = [("ReproLeft", TARGET_ID), ("ReproRight", DEPENDENT_ID)]
    order = DeletionOrder(candidates=candidates, schemas=schemas)

    assert {lookup.kind for lookup in order.peer_lookups} == {"ReproLeft", "ReproRight"}
    assert order.order(node_peers={DEPENDENT_ID: {TARGET_ID}}) == candidates[::-1]


def test_deletion_order_keeps_group_order_without_peers_for_a_self_referencing_kind() -> None:
    schemas = node_schemas(node_schema("Chain", relationships=[mandatory("previous", "ReproChain")]))
    candidates = [("ReproChain", member_id) for member_id in CHAIN_IDS]

    assert DeletionOrder(candidates=candidates, schemas=schemas).order() == candidates


def test_deletion_order_puts_a_kind_missing_from_the_schema_last() -> None:
    schemas = node_schemas(
        node_schema("Target"), node_schema("Dependent", relationships=[mandatory("target", "ReproTarget")])
    )
    candidates = [("ReproRemoved", CHAIN_IDS[0]), ("ReproTarget", TARGET_ID), ("ReproDependent", DEPENDENT_ID)]

    assert DeletionOrder(candidates=candidates, schemas=schemas).order() == [
        ("ReproDependent", DEPENDENT_ID),
        ("ReproTarget", TARGET_ID),
        ("ReproRemoved", CHAIN_IDS[0]),
    ]


def test_deletion_order_ignores_a_mandatory_peer_that_is_not_a_candidate() -> None:
    """A peer kind the run is not deleting adds no dependency between the candidates."""
    schemas = node_schemas(
        node_schema("Target"),
        node_schema("Dependent", relationships=[mandatory("target", "ReproTarget")]),
    )
    candidates = [("ReproDependent", DEPENDENT_ID), ("ReproDependent", CHAIN_IDS[0])]
    order = DeletionOrder(candidates=candidates, schemas=schemas)

    assert order.peer_lookups == []
    assert order.order() == candidates


def test_deletion_order_keeps_group_order_when_the_peers_form_a_cycle() -> None:
    """The server cannot store such a cycle; if the peers read back describe one, the group order is kept."""
    schemas = node_schemas(node_schema("Chain", relationships=[mandatory("previous", "ReproChain")]))
    candidates = [("ReproChain", member_id) for member_id in CHAIN_IDS[:2]]
    member_peers = {CHAIN_IDS[0]: {CHAIN_IDS[1]}, CHAIN_IDS[1]: {CHAIN_IDS[0]}}

    order = DeletionOrder(candidates=candidates, schemas=schemas)

    assert order.order(node_peers=member_peers) == candidates
