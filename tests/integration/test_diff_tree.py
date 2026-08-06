from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

import pytest

from infrahub_sdk.testing.docker import TestInfrahubDockerClient
from infrahub_sdk.testing.schemas.animal import TESTING_DOG, SchemaAnimal

if TYPE_CHECKING:
    from infrahub_sdk import InfrahubClient
    from infrahub_sdk.node import InfrahubNode

DIFF_BRANCH = "diff-branch"
DIFF_NAME = "diff-branch-test-diff"
NEW_COLOR = "#000000"


class TestGetDiffTree(TestInfrahubDockerClient, SchemaAnimal):
    @pytest.fixture(scope="class")
    async def branch_with_changes(
        self,
        client: InfrahubClient,
        load_schema: None,
        person_liam: InfrahubNode,
        person_sophia: InfrahubNode,
        dog_rocky: InfrahubNode,
    ) -> None:
        """Create a branch, change an attribute and a relationship on it and compute the diff."""
        branch = await client.branch.create(branch_name=DIFF_BRANCH)

        dog = await client.get(kind=TESTING_DOG, id=dog_rocky.id, branch=DIFF_BRANCH)
        dog.color.value = NEW_COLOR
        dog.owner = person_liam.id
        await dog.save()

        await client.create_diff(
            branch=DIFF_BRANCH,
            name=DIFF_NAME,
            from_time=datetime.fromisoformat(branch.branched_from.replace("Z", "+00:00")),
            to_time=datetime.now(timezone.utc),
        )

    async def test_get_diff_tree_summary_only(
        self, client: InfrahubClient, branch_with_changes: None, dog_rocky: InfrahubNode
    ) -> None:
        """Without include_properties the diff tree only contains summary counts."""
        diff_tree = await client.get_diff_tree(branch=DIFF_BRANCH)

        assert diff_tree is not None
        assert diff_tree["base_branch"] == "main"
        assert diff_tree["diff_branch"] == DIFF_BRANCH
        dog_node = next(node for node in diff_tree["nodes"] if node["id"] == dog_rocky.id)
        assert dog_node["action"] == "UPDATED"
        color_element = next(element for element in dog_node["elements"] if element["name"] == "color")
        assert "properties" not in color_element

    async def test_get_diff_tree_with_properties(
        self,
        client: InfrahubClient,
        branch_with_changes: None,
        person_liam: InfrahubNode,
        person_sophia: InfrahubNode,
        dog_rocky: InfrahubNode,
    ) -> None:
        """With include_properties the diff tree contains previous/new values per change."""
        diff_tree = await client.get_diff_tree(branch=DIFF_BRANCH, include_properties=True)

        assert diff_tree is not None
        dog_node = next(node for node in diff_tree["nodes"] if node["id"] == dog_rocky.id)

        color_element = next(element for element in dog_node["elements"] if element["name"] == "color")
        assert color_element["element_type"] == "ATTRIBUTE"
        color_value = next(prop for prop in color_element["properties"] if prop["property_type"] == "HAS_VALUE")
        assert color_value["action"] == "UPDATED"
        assert color_value["previous_value"] == "#784212"
        assert color_value["new_value"] == NEW_COLOR

        owner_element = next(element for element in dog_node["elements"] if element["name"] == "owner")
        assert owner_element["element_type"] == "RELATIONSHIP_ONE"
        assert owner_element["peer_id"] in {person_liam.id, person_sophia.id}
        assert "peer_label" in owner_element
        owner_value = next(prop for prop in owner_element["properties"] if prop["property_type"] == "IS_RELATED")
        assert owner_value["action"] == "UPDATED"
        assert owner_value["previous_value"] == person_sophia.id
        assert owner_value["new_value"] == person_liam.id
