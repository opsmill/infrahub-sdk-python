"""Integration tests for branch report functionality.

These tests use the TestInfrahubDockerClient to test against a real Infrahub instance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from infrahub_sdk.ctl.branch_report import (
    analyze_branch_diffs,
    build_report_items,
    check_git_changes,
    check_proposed_changes,
    display_report,
    get_all_non_default_branches,
)
from infrahub_sdk.testing.docker import TestInfrahubDockerClient

if TYPE_CHECKING:
    from infrahub_sdk import InfrahubClient


class TestBranchReportIntegration(TestInfrahubDockerClient):
    """Integration tests for branch report command."""

    @pytest.fixture
    async def setup_test_branches(self, client: InfrahubClient):
        """Set up test branches for integration testing."""
        # Create test branches
        await client.branch.create(branch_name="test-branch-1", sync_with_git=False)
        await client.branch.create(branch_name="test-branch-2", sync_with_git=False)
        await client.branch.create(branch_name="test-branch-3", sync_with_git=False)

        yield

        # Cleanup - delete test branches
        try:
            await client.branch.delete("test-branch-1")
        except Exception:
            pass
        try:
            await client.branch.delete("test-branch-2")
        except Exception:
            pass
        try:
            await client.branch.delete("test-branch-3")
        except Exception:
            pass

    async def test_get_all_non_default_branches_integration(self, client: InfrahubClient, setup_test_branches):
        """Test fetching non-default branches from real Infrahub instance."""
        branches = await get_all_non_default_branches(client)

        # Should have at least our 3 test branches
        assert len(branches) >= 3
        assert all(not branch.is_default for branch in branches)

        # Check our test branches are present
        branch_names = {branch.name for branch in branches}
        assert "test-branch-1" in branch_names
        assert "test-branch-2" in branch_names
        assert "test-branch-3" in branch_names

    async def test_analyze_branch_diffs_integration(self, client: InfrahubClient, setup_test_branches):
        """Test analyzing branch diffs with real Infrahub instance."""
        branches = await get_all_non_default_branches(client)
        test_branches = [b for b in branches if b.name.startswith("test-branch-")]

        # Create progress for the analysis
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
        ) as progress:
            results = await analyze_branch_diffs(client, test_branches, progress)

        # Should have results for all test branches
        assert len(results) >= 3

        # Results should have correct structure
        for result in results:
            assert result.branch_name.startswith("test-branch-")
            assert isinstance(result.has_changes, bool)
            # New branches with no changes should show has_changes=False
            assert result.has_changes is False

    async def test_check_proposed_changes_integration(self, client: InfrahubClient, setup_test_branches):
        """Test checking proposed changes with real Infrahub instance."""
        branches = await get_all_non_default_branches(client)
        test_branches = [b for b in branches if b.name.startswith("test-branch-")]

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
        ) as progress:
            results = await check_proposed_changes(client, test_branches, progress)

        # Should have results for all test branches
        assert len(results) >= 3

        # Test branches should have no proposed changes
        for result in results:
            assert result.branch_name.startswith("test-branch-")
            assert result.has_changes is False
            assert result.count == 0

    async def test_check_git_changes_integration(self, client: InfrahubClient, setup_test_branches):
        """Test checking Git changes with real Infrahub instance."""
        branches = await get_all_non_default_branches(client)
        test_branches = [b for b in branches if b.name.startswith("test-branch-")]

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
        ) as progress:
            results = await check_git_changes(client, test_branches, progress)

        # Should have results for all test branches
        assert len(results) >= 3

        # Test branches are not synced with Git, so should have no changes
        for result in results:
            assert result.branch_name.startswith("test-branch-")
            assert result.has_changes is False
            assert len(result.repos_with_changes) == 0

    async def test_full_report_workflow_integration(self, client: InfrahubClient, setup_test_branches):
        """Test the complete branch report workflow."""
        # Step 1: Get all non-default branches
        branches = await get_all_non_default_branches(client)
        test_branches = [b for b in branches if b.name.startswith("test-branch-")]

        assert len(test_branches) >= 3

        # Step 2: Analyze all aspects
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
        ) as progress:
            diff_results = await analyze_branch_diffs(client, test_branches, progress)
            pc_results = await check_proposed_changes(client, test_branches, progress)
            git_results = await check_git_changes(client, test_branches, progress)

        # Step 3: Build report items
        report_items = build_report_items(test_branches, diff_results, pc_results, git_results)

        # Verify report items
        assert len(report_items) >= 3

        # New test branches should be deletable (no changes)
        for item in report_items:
            assert item.branch_name.startswith("test-branch-")
            assert item.can_be_deleted is True  # No changes in new branches
            assert not item.has_data_changes
            assert not item.has_proposed_changes
            assert item.has_git_changes is None  # Not synced with Git

        # Step 4: Display report (just verify it doesn't crash)
        console = Console()
        display_report(report_items, test_branches, console, verbose=False)

    async def test_report_with_data_changes_integration(self, client: InfrahubClient, setup_test_branches):
        """Test branch report when branch has data changes.

        Note: This test creates a node on a test branch to simulate data changes.
        """
        # Create a simple node on test-branch-1 to create data changes
        # We'll use a built-in schema type that should exist
        try:
            # Try to create a tag or account (built-in types)
            await client.create(
                kind="BuiltinTag",
                branch="test-branch-1",
                name="test-tag",
                description="Test tag for integration test",
            )
        except Exception:
            # If BuiltinTag doesn't exist, skip this test
            pytest.skip("Built-in schema types not available for testing")

        # Now run the analysis
        branches = await get_all_non_default_branches(client)
        test_branch = [b for b in branches if b.name == "test-branch-1"]

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
        ) as progress:
            diff_results = await analyze_branch_diffs(client, test_branch, progress)
            pc_results = await check_proposed_changes(client, test_branch, progress)
            git_results = await check_git_changes(client, test_branch, progress)

        report_items = build_report_items(test_branch, diff_results, pc_results, git_results)

        # Branch should have data changes
        assert len(report_items) == 1
        assert report_items[0].has_data_changes is True
        assert report_items[0].can_be_deleted is False

    async def test_report_display_verbose_mode_integration(self, client: InfrahubClient, setup_test_branches):
        """Test displaying report in verbose mode."""
        branches = await get_all_non_default_branches(client)
        test_branches = [b for b in branches if b.name.startswith("test-branch-")]

        # Run full analysis
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
        ) as progress:
            diff_results = await analyze_branch_diffs(client, test_branches, progress)
            pc_results = await check_proposed_changes(client, test_branches, progress)
            git_results = await check_git_changes(client, test_branches, progress)

        report_items = build_report_items(test_branches, diff_results, pc_results, git_results)

        # Display in verbose mode (just verify it doesn't crash)
        console = Console()
        display_report(report_items, test_branches, console, verbose=True)

        # Display in non-verbose mode
        display_report(report_items, test_branches, console, verbose=False)


class TestBranchReportEdgeCases(TestInfrahubDockerClient):
    """Test edge cases and error handling in branch report."""

    async def test_empty_branches_list(self, client: InfrahubClient):
        """Test handling when there are no non-default branches."""
        # Get all branches
        all_branches = await get_all_non_default_branches(client)

        # If there are no branches, that's ok - test with empty list
        empty_branches = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
        ) as progress:
            diff_results = await analyze_branch_diffs(client, empty_branches, progress)
            pc_results = await check_proposed_changes(client, empty_branches, progress)
            git_results = await check_git_changes(client, empty_branches, progress)

        report_items = build_report_items(empty_branches, diff_results, pc_results, git_results)

        assert len(report_items) == 0

        # Display should handle empty list gracefully
        console = Console()
        display_report(report_items, empty_branches, console, verbose=False)

    async def test_branch_with_git_sync(self, client: InfrahubClient):
        """Test branch report for branches synced with Git."""
        # Create a branch with Git sync enabled
        branch_name = "test-git-sync-branch"
        try:
            await client.branch.create(branch_name=branch_name, sync_with_git=True)

            branches = await get_all_non_default_branches(client)
            test_branch = [b for b in branches if b.name == branch_name]

            assert len(test_branch) == 1
            assert test_branch[0].sync_with_git is True

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
            ) as progress:
                diff_results = await analyze_branch_diffs(client, test_branch, progress)
                pc_results = await check_proposed_changes(client, test_branch, progress)
                git_results = await check_git_changes(client, test_branch, progress)

            report_items = build_report_items(test_branch, diff_results, pc_results, git_results)

            assert len(report_items) == 1
            # Git changes should be a boolean (not None) for synced branches
            assert isinstance(report_items[0].has_git_changes, bool)

        finally:
            # Cleanup
            try:
                await client.branch.delete(branch_name)
            except Exception:
                pass

    async def test_report_sorting(self, client: InfrahubClient):
        """Test that report items are sorted correctly."""
        # Create branches with different characteristics
        branch1 = "test-deletable-a"
        branch2 = "test-deletable-b"
        branch3 = "test-has-changes"

        try:
            await client.branch.create(branch_name=branch1, sync_with_git=False)
            await client.branch.create(branch_name=branch2, sync_with_git=False)
            await client.branch.create(branch_name=branch3, sync_with_git=False)

            # Create data on branch3 to make it non-deletable
            try:
                await client.create(
                    kind="BuiltinTag",
                    branch=branch3,
                    name="test-tag",
                    description="Test",
                )
            except Exception:
                pass  # If we can't create data, skip this part

            branches = await get_all_non_default_branches(client)
            test_branches = [b for b in branches if b.name in [branch1, branch2, branch3]]

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
            ) as progress:
                diff_results = await analyze_branch_diffs(client, test_branches, progress)
                pc_results = await check_proposed_changes(client, test_branches, progress)
                git_results = await check_git_changes(client, test_branches, progress)

            report_items = build_report_items(test_branches, diff_results, pc_results, git_results)

            # Deletable branches should come first
            deletable_items = [item for item in report_items if item.can_be_deleted]
            non_deletable_items = [item for item in report_items if not item.can_be_deleted]

            # Check that all deletable items come before non-deletable items
            if deletable_items and non_deletable_items:
                last_deletable_idx = report_items.index(deletable_items[-1])
                first_non_deletable_idx = report_items.index(non_deletable_items[0])
                assert last_deletable_idx < first_non_deletable_idx

        finally:
            # Cleanup
            for branch_name in [branch1, branch2, branch3]:
                try:
                    await client.branch.delete(branch_name)
                except Exception:
                    pass
