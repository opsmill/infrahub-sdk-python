"""Unit tests for branch report functionality."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from rich.console import Console
from rich.progress import Progress

from infrahub_sdk.branch import BranchData, BranchStatus
from infrahub_sdk.ctl.branch_report import (
    BranchReportItem,
    BranchReportSummary,
    DiffAnalysisResult,
    GitChangesResult,
    ProposedChangesResult,
    _has_diff_changes,
    analyze_branch_diffs,
    build_report_items,
    calculate_summary,
    check_git_changes,
    check_proposed_changes,
    display_report,
    get_all_non_default_branches,
)


# Test Data Models
class TestBranchReportModels:
    """Test Pydantic models for branch report."""

    def test_branch_report_item_creation(self):
        """Test creating a BranchReportItem with all fields."""
        item = BranchReportItem(
            branch_name="test-branch",
            description="Test branch",
            sync_with_git=True,
            has_data_changes=False,
            has_proposed_changes=False,
            proposed_changes_count=0,
            has_git_changes=False,
            git_repositories_checked=["repo1"],
            can_be_deleted=True,
            status="OPEN",
            errors=[],
        )
        assert item.branch_name == "test-branch"
        assert item.can_be_deleted is True
        assert item.errors == []

    def test_branch_report_item_with_errors(self):
        """Test BranchReportItem with errors."""
        item = BranchReportItem(
            branch_name="test-branch",
            description="Test branch",
            sync_with_git=False,
            has_data_changes=True,
            has_proposed_changes=False,
            proposed_changes_count=0,
            has_git_changes=None,
            git_repositories_checked=[],
            can_be_deleted=False,
            status="OPEN",
            errors=["Diff analysis timeout: timeout occurred"],
        )
        assert len(item.errors) == 1
        assert "timeout" in item.errors[0]

    def test_branch_report_summary_creation(self):
        """Test creating a BranchReportSummary."""
        summary = BranchReportSummary(
            total_branches=10,
            deletable_branches=5,
            branches_with_data_changes=3,
            branches_with_proposed_changes=2,
            branches_with_git_changes=1,
            branches_synced_with_git=6,
        )
        assert summary.total_branches == 10
        assert summary.deletable_branches == 5

    def test_diff_analysis_result(self):
        """Test DiffAnalysisResult model."""
        result = DiffAnalysisResult(branch_name="test", has_changes=True, error=None)
        assert result.branch_name == "test"
        assert result.has_changes is True
        assert result.error is None

    def test_proposed_changes_result(self):
        """Test ProposedChangesResult model."""
        result = ProposedChangesResult(
            branch_name="test", has_changes=True, count=3, error=None
        )
        assert result.branch_name == "test"
        assert result.count == 3

    def test_git_changes_result(self):
        """Test GitChangesResult model."""
        result = GitChangesResult(
            branch_name="test",
            has_changes=True,
            repos_with_changes=["repo1", "repo2"],
            error=None,
        )
        assert len(result.repos_with_changes) == 2


# Test Helper Functions
class TestHasDiffChanges:
    """Test the _has_diff_changes helper function."""

    def test_no_changes(self):
        """Test with no changes."""
        node_diffs = [
            {"action": "UNCHANGED", "elements": []},
        ]
        assert _has_diff_changes(node_diffs) is False

    def test_node_action_changed(self):
        """Test when node action is not UNCHANGED."""
        node_diffs = [
            {"action": "ADDED", "elements": []},
        ]
        assert _has_diff_changes(node_diffs) is True

    def test_element_action_changed(self):
        """Test when element action is not UNCHANGED."""
        node_diffs = [
            {
                "action": "UNCHANGED",
                "elements": [{"action": "UPDATED", "summary": {}}],
            },
        ]
        assert _has_diff_changes(node_diffs) is True

    def test_element_summary_added(self):
        """Test when element has added items."""
        node_diffs = [
            {
                "action": "UNCHANGED",
                "elements": [
                    {"action": "UNCHANGED", "summary": {"added": 1, "updated": 0, "removed": 0}}
                ],
            },
        ]
        assert _has_diff_changes(node_diffs) is True

    def test_element_summary_updated(self):
        """Test when element has updated items."""
        node_diffs = [
            {
                "action": "UNCHANGED",
                "elements": [
                    {"action": "UNCHANGED", "summary": {"added": 0, "updated": 2, "removed": 0}}
                ],
            },
        ]
        assert _has_diff_changes(node_diffs) is True

    def test_element_summary_removed(self):
        """Test when element has removed items."""
        node_diffs = [
            {
                "action": "UNCHANGED",
                "elements": [
                    {"action": "UNCHANGED", "summary": {"added": 0, "updated": 0, "removed": 3}}
                ],
            },
        ]
        assert _has_diff_changes(node_diffs) is True

    def test_multiple_nodes_no_changes(self):
        """Test multiple nodes with no changes."""
        node_diffs = [
            {"action": "UNCHANGED", "elements": []},
            {"action": "UNCHANGED", "elements": [{"action": "UNCHANGED", "summary": {}}]},
        ]
        assert _has_diff_changes(node_diffs) is False

    def test_multiple_nodes_one_changed(self):
        """Test multiple nodes where one has changes."""
        node_diffs = [
            {"action": "UNCHANGED", "elements": []},
            {"action": "UPDATED", "elements": []},
        ]
        assert _has_diff_changes(node_diffs) is True


# Test Build Report Items
class TestBuildReportItems:
    """Test the build_report_items function."""

    def test_build_report_items_basic(self):
        """Test building report items with basic data."""
        branches = [
            BranchData(
                id="1",
                name="branch1",
                description="Test branch 1",
                sync_with_git=False,
                is_default=False,
                has_schema_changes=False,
                status=BranchStatus.OPEN,
                branched_from="2023-01-01T00:00:00Z",
            ),
        ]
        diff_results = [DiffAnalysisResult(branch_name="branch1", has_changes=False)]
        pc_results = [
            ProposedChangesResult(branch_name="branch1", has_changes=False, count=0)
        ]
        git_results = [
            GitChangesResult(branch_name="branch1", has_changes=False, repos_with_changes=[])
        ]

        items = build_report_items(branches, diff_results, pc_results, git_results)

        assert len(items) == 1
        assert items[0].branch_name == "branch1"
        assert items[0].can_be_deleted is True
        assert items[0].has_git_changes is None  # Not synced with Git

    def test_build_report_items_with_changes(self):
        """Test building report items with various changes."""
        branches = [
            BranchData(
                id="1",
                name="branch1",
                description="Has data changes",
                sync_with_git=False,
                is_default=False,
                has_schema_changes=False,
                status=BranchStatus.OPEN,
                branched_from="2023-01-01T00:00:00Z",
            ),
            BranchData(
                id="2",
                name="branch2",
                description="Has proposed changes",
                sync_with_git=False,
                is_default=False,
                has_schema_changes=False,
                status=BranchStatus.OPEN,
                branched_from="2023-01-01T00:00:00Z",
            ),
            BranchData(
                id="3",
                name="branch3",
                description="Has Git changes",
                sync_with_git=True,
                is_default=False,
                has_schema_changes=False,
                status=BranchStatus.OPEN,
                branched_from="2023-01-01T00:00:00Z",
            ),
        ]
        diff_results = [
            DiffAnalysisResult(branch_name="branch1", has_changes=True),
            DiffAnalysisResult(branch_name="branch2", has_changes=False),
            DiffAnalysisResult(branch_name="branch3", has_changes=False),
        ]
        pc_results = [
            ProposedChangesResult(branch_name="branch1", has_changes=False, count=0),
            ProposedChangesResult(branch_name="branch2", has_changes=True, count=2),
            ProposedChangesResult(branch_name="branch3", has_changes=False, count=0),
        ]
        git_results = [
            GitChangesResult(branch_name="branch1", has_changes=False, repos_with_changes=[]),
            GitChangesResult(branch_name="branch2", has_changes=False, repos_with_changes=[]),
            GitChangesResult(
                branch_name="branch3", has_changes=True, repos_with_changes=["repo1"]
            ),
        ]

        items = build_report_items(branches, diff_results, pc_results, git_results)

        assert len(items) == 3
        # All should be not deletable due to changes
        assert all(not item.can_be_deleted for item in items)

    def test_build_report_items_with_errors(self):
        """Test building report items with errors."""
        branches = [
            BranchData(
                id="1",
                name="branch1",
                description="Error in diff",
                sync_with_git=False,
                is_default=False,
                has_schema_changes=False,
                status=BranchStatus.OPEN,
                branched_from="2023-01-01T00:00:00Z",
            ),
        ]
        diff_results = [
            DiffAnalysisResult(
                branch_name="branch1",
                has_changes=True,
                error="Diff analysis timeout: timeout",
            )
        ]
        pc_results = [
            ProposedChangesResult(branch_name="branch1", has_changes=False, count=0)
        ]
        git_results = [
            GitChangesResult(branch_name="branch1", has_changes=False, repos_with_changes=[])
        ]

        items = build_report_items(branches, diff_results, pc_results, git_results)

        assert len(items) == 1
        assert len(items[0].errors) == 1
        assert "timeout" in items[0].errors[0]
        assert not items[0].can_be_deleted  # Conservative: has changes

    def test_build_report_items_sorting(self):
        """Test that report items are sorted correctly (deletable first)."""
        branches = [
            BranchData(
                id="1",
                name="a-branch",
                description="Has changes",
                sync_with_git=False,
                is_default=False,
                has_schema_changes=False,
                status=BranchStatus.OPEN,
                branched_from="2023-01-01T00:00:00Z",
            ),
            BranchData(
                id="2",
                name="b-branch",
                description="No changes",
                sync_with_git=False,
                is_default=False,
                has_schema_changes=False,
                status=BranchStatus.OPEN,
                branched_from="2023-01-01T00:00:00Z",
            ),
            BranchData(
                id="3",
                name="c-branch",
                description="No changes",
                sync_with_git=False,
                is_default=False,
                has_schema_changes=False,
                status=BranchStatus.OPEN,
                branched_from="2023-01-01T00:00:00Z",
            ),
        ]
        diff_results = [
            DiffAnalysisResult(branch_name="a-branch", has_changes=True),
            DiffAnalysisResult(branch_name="b-branch", has_changes=False),
            DiffAnalysisResult(branch_name="c-branch", has_changes=False),
        ]
        pc_results = [
            ProposedChangesResult(branch_name="a-branch", has_changes=False, count=0),
            ProposedChangesResult(branch_name="b-branch", has_changes=False, count=0),
            ProposedChangesResult(branch_name="c-branch", has_changes=False, count=0),
        ]
        git_results = [
            GitChangesResult(branch_name="a-branch", has_changes=False, repos_with_changes=[]),
            GitChangesResult(branch_name="b-branch", has_changes=False, repos_with_changes=[]),
            GitChangesResult(branch_name="c-branch", has_changes=False, repos_with_changes=[]),
        ]

        items = build_report_items(branches, diff_results, pc_results, git_results)

        # Deletable branches should be first
        assert items[0].can_be_deleted is True
        assert items[0].branch_name == "b-branch"
        assert items[1].can_be_deleted is True
        assert items[1].branch_name == "c-branch"
        assert items[2].can_be_deleted is False
        assert items[2].branch_name == "a-branch"


# Test Summary Calculation
class TestCalculateSummary:
    """Test the calculate_summary function."""

    def test_calculate_summary_empty(self):
        """Test summary calculation with no items."""
        summary = calculate_summary([])
        assert summary.total_branches == 0
        assert summary.deletable_branches == 0

    def test_calculate_summary_basic(self):
        """Test summary calculation with basic data."""
        items = [
            BranchReportItem(
                branch_name="branch1",
                description="",
                sync_with_git=False,
                has_data_changes=False,
                has_proposed_changes=False,
                proposed_changes_count=0,
                has_git_changes=None,
                git_repositories_checked=[],
                can_be_deleted=True,
                status="OPEN",
            ),
            BranchReportItem(
                branch_name="branch2",
                description="",
                sync_with_git=True,
                has_data_changes=True,
                has_proposed_changes=False,
                proposed_changes_count=0,
                has_git_changes=False,
                git_repositories_checked=[],
                can_be_deleted=False,
                status="OPEN",
            ),
        ]
        summary = calculate_summary(items)
        assert summary.total_branches == 2
        assert summary.deletable_branches == 1
        assert summary.branches_with_data_changes == 1
        assert summary.branches_with_proposed_changes == 0
        assert summary.branches_with_git_changes == 0
        assert summary.branches_synced_with_git == 1

    def test_calculate_summary_comprehensive(self):
        """Test summary calculation with various branch states."""
        items = [
            BranchReportItem(
                branch_name="deletable",
                description="",
                sync_with_git=False,
                has_data_changes=False,
                has_proposed_changes=False,
                proposed_changes_count=0,
                has_git_changes=None,
                git_repositories_checked=[],
                can_be_deleted=True,
                status="OPEN",
            ),
            BranchReportItem(
                branch_name="has-data",
                description="",
                sync_with_git=False,
                has_data_changes=True,
                has_proposed_changes=False,
                proposed_changes_count=0,
                has_git_changes=None,
                git_repositories_checked=[],
                can_be_deleted=False,
                status="OPEN",
            ),
            BranchReportItem(
                branch_name="has-pcs",
                description="",
                sync_with_git=False,
                has_data_changes=False,
                has_proposed_changes=True,
                proposed_changes_count=3,
                has_git_changes=None,
                git_repositories_checked=[],
                can_be_deleted=False,
                status="OPEN",
            ),
            BranchReportItem(
                branch_name="has-git",
                description="",
                sync_with_git=True,
                has_data_changes=False,
                has_proposed_changes=False,
                proposed_changes_count=0,
                has_git_changes=True,
                git_repositories_checked=["repo1"],
                can_be_deleted=False,
                status="OPEN",
            ),
        ]
        summary = calculate_summary(items)
        assert summary.total_branches == 4
        assert summary.deletable_branches == 1
        assert summary.branches_with_data_changes == 1
        assert summary.branches_with_proposed_changes == 1
        assert summary.branches_with_git_changes == 1
        assert summary.branches_synced_with_git == 1


# Test Async Functions with Mocks
class TestGetAllNonDefaultBranches:
    """Test the get_all_non_default_branches function."""

    @pytest.mark.asyncio
    async def test_get_all_non_default_branches(self):
        """Test fetching non-default branches."""
        mock_client = MagicMock()
        mock_client.branch.all = AsyncMock(
            return_value={
                "main": BranchData(
                    id="1",
                    name="main",
                    sync_with_git=True,
                    is_default=True,
                    has_schema_changes=False,
                    status=BranchStatus.OPEN,
                    branched_from="2023-01-01T00:00:00Z",
                ),
                "branch1": BranchData(
                    id="2",
                    name="branch1",
                    sync_with_git=False,
                    is_default=False,
                    has_schema_changes=False,
                    status=BranchStatus.OPEN,
                    branched_from="2023-01-02T00:00:00Z",
                ),
                "branch2": BranchData(
                    id="3",
                    name="branch2",
                    sync_with_git=False,
                    is_default=False,
                    has_schema_changes=False,
                    status=BranchStatus.OPEN,
                    branched_from="2023-01-03T00:00:00Z",
                ),
            }
        )

        result = await get_all_non_default_branches(mock_client)

        assert len(result) == 2
        assert all(not branch.is_default for branch in result)
        assert {branch.name for branch in result} == {"branch1", "branch2"}

    @pytest.mark.asyncio
    async def test_get_all_non_default_branches_empty(self):
        """Test when there are no non-default branches."""
        mock_client = MagicMock()
        mock_client.branch.all = AsyncMock(
            return_value={
                "main": BranchData(
                    id="1",
                    name="main",
                    sync_with_git=True,
                    is_default=True,
                    has_schema_changes=False,
                    status=BranchStatus.OPEN,
                    branched_from="2023-01-01T00:00:00Z",
                ),
            }
        )

        result = await get_all_non_default_branches(mock_client)

        assert len(result) == 0


class TestAnalyzeBranchDiffs:
    """Test the analyze_branch_diffs function."""

    @pytest.mark.asyncio
    async def test_analyze_branch_diffs_no_changes(self):
        """Test analyzing branches with no changes."""
        mock_client = MagicMock()
        mock_client.create_diff = AsyncMock()
        mock_client.get_diff_summary = AsyncMock(
            return_value=[{"action": "UNCHANGED", "elements": []}]
        )

        branches = [
            BranchData(
                id="1",
                name="branch1",
                sync_with_git=False,
                is_default=False,
                has_schema_changes=False,
                status=BranchStatus.OPEN,
                branched_from="2023-01-01T00:00:00Z",
            ),
        ]

        # Create a mock progress object
        mock_progress = MagicMock(spec=Progress)
        mock_progress.add_task = Mock(return_value="task_id")
        mock_progress.advance = Mock()

        results = await analyze_branch_diffs(mock_client, branches, mock_progress)

        assert len(results) == 1
        assert results[0].branch_name == "branch1"
        assert results[0].has_changes is False
        assert results[0].error is None

    @pytest.mark.asyncio
    async def test_analyze_branch_diffs_with_changes(self):
        """Test analyzing branches with changes."""
        mock_client = MagicMock()
        mock_client.create_diff = AsyncMock()
        mock_client.get_diff_summary = AsyncMock(
            return_value=[{"action": "UPDATED", "elements": []}]
        )

        branches = [
            BranchData(
                id="1",
                name="branch1",
                sync_with_git=False,
                is_default=False,
                has_schema_changes=False,
                status=BranchStatus.OPEN,
                branched_from="2023-01-01T00:00:00Z",
            ),
        ]

        mock_progress = MagicMock(spec=Progress)
        mock_progress.add_task = Mock(return_value="task_id")
        mock_progress.advance = Mock()

        results = await analyze_branch_diffs(mock_client, branches, mock_progress)

        assert len(results) == 1
        assert results[0].has_changes is True

    @pytest.mark.asyncio
    async def test_analyze_branch_diffs_timeout(self):
        """Test handling timeout during diff analysis."""
        mock_client = MagicMock()
        mock_client.create_diff = AsyncMock(side_effect=TimeoutError("Timeout"))
        mock_client.get_diff_summary = AsyncMock()

        branches = [
            BranchData(
                id="1",
                name="branch1",
                sync_with_git=False,
                is_default=False,
                has_schema_changes=False,
                status=BranchStatus.OPEN,
                branched_from="2023-01-01T00:00:00Z",
            ),
        ]

        mock_progress = MagicMock(spec=Progress)
        mock_progress.add_task = Mock(return_value="task_id")
        mock_progress.advance = Mock()

        results = await analyze_branch_diffs(mock_client, branches, mock_progress)

        assert len(results) == 1
        assert results[0].has_changes is True  # Conservative: assume changes
        assert results[0].error is not None
        assert "timeout" in results[0].error.lower()

    @pytest.mark.asyncio
    async def test_analyze_branch_diffs_permission_error(self):
        """Test handling permission error during diff analysis."""
        mock_client = MagicMock()
        mock_client.create_diff = AsyncMock(
            side_effect=PermissionError("Permission denied")
        )

        branches = [
            BranchData(
                id="1",
                name="branch1",
                sync_with_git=False,
                is_default=False,
                has_schema_changes=False,
                status=BranchStatus.OPEN,
                branched_from="2023-01-01T00:00:00Z",
            ),
        ]

        mock_progress = MagicMock(spec=Progress)
        mock_progress.add_task = Mock(return_value="task_id")
        mock_progress.advance = Mock()

        results = await analyze_branch_diffs(mock_client, branches, mock_progress)

        assert len(results) == 1
        assert results[0].has_changes is True
        assert "Permission denied" in results[0].error


class TestCheckProposedChanges:
    """Test the check_proposed_changes function."""

    @pytest.mark.asyncio
    async def test_check_proposed_changes_no_pcs(self):
        """Test checking branches with no proposed changes."""
        mock_client = MagicMock()
        mock_client.filters = AsyncMock(return_value=[])
        mock_client.default_branch = "main"

        branches = [
            BranchData(
                id="1",
                name="branch1",
                sync_with_git=False,
                is_default=False,
                has_schema_changes=False,
                status=BranchStatus.OPEN,
                branched_from="2023-01-01T00:00:00Z",
            ),
        ]

        mock_progress = MagicMock(spec=Progress)
        mock_progress.add_task = Mock(return_value="task_id")
        mock_progress.advance = Mock()

        results = await check_proposed_changes(mock_client, branches, mock_progress)

        assert len(results) == 1
        assert results[0].has_changes is False
        assert results[0].count == 0

    @pytest.mark.asyncio
    async def test_check_proposed_changes_with_pcs(self):
        """Test checking branches with proposed changes."""
        # Create mock proposed change
        mock_pc = MagicMock()
        mock_source_branch = MagicMock()
        mock_source_branch.name.value = "branch1"
        mock_pc.source_branch.peer = mock_source_branch
        mock_pc.state.value = "open"

        mock_client = MagicMock()
        mock_client.filters = AsyncMock(return_value=[mock_pc])
        mock_client.default_branch = "main"

        branches = [
            BranchData(
                id="1",
                name="branch1",
                sync_with_git=False,
                is_default=False,
                has_schema_changes=False,
                status=BranchStatus.OPEN,
                branched_from="2023-01-01T00:00:00Z",
            ),
        ]

        mock_progress = MagicMock(spec=Progress)
        mock_progress.add_task = Mock(return_value="task_id")
        mock_progress.advance = Mock()

        results = await check_proposed_changes(mock_client, branches, mock_progress)

        assert len(results) == 1
        assert results[0].has_changes is True
        assert results[0].count == 1


class TestCheckGitChanges:
    """Test the check_git_changes function."""

    @pytest.mark.asyncio
    async def test_check_git_changes_no_sync(self):
        """Test checking branches not synced with Git."""
        mock_client = MagicMock()
        mock_client.get_list_repositories = AsyncMock(return_value={})
        mock_client.default_branch = "main"

        branches = [
            BranchData(
                id="1",
                name="branch1",
                sync_with_git=False,  # Not synced
                is_default=False,
                has_schema_changes=False,
                status=BranchStatus.OPEN,
                branched_from="2023-01-01T00:00:00Z",
            ),
        ]

        mock_progress = MagicMock(spec=Progress)
        mock_progress.add_task = Mock(return_value="task_id")
        mock_progress.advance = Mock()

        results = await check_git_changes(mock_client, branches, mock_progress)

        assert len(results) == 1
        assert results[0].has_changes is False
        assert len(results[0].repos_with_changes) == 0

    @pytest.mark.asyncio
    async def test_check_git_changes_with_sync_no_changes(self):
        """Test checking Git-synced branches with no changes."""
        # Mock repository data
        mock_repo_data = MagicMock()
        mock_repo_data.branches = {
            "main": "commit-abc123",
            "branch1": "commit-abc123",  # Same commit as main
        }

        mock_client = MagicMock()
        mock_client.get_list_repositories = AsyncMock(
            return_value={"repo1": mock_repo_data}
        )
        mock_client.default_branch = "main"

        branches = [
            BranchData(
                id="1",
                name="branch1",
                sync_with_git=True,  # Synced
                is_default=False,
                has_schema_changes=False,
                status=BranchStatus.OPEN,
                branched_from="2023-01-01T00:00:00Z",
            ),
        ]

        mock_progress = MagicMock(spec=Progress)
        mock_progress.add_task = Mock(return_value="task_id")
        mock_progress.advance = Mock()

        results = await check_git_changes(mock_client, branches, mock_progress)

        assert len(results) == 1
        assert results[0].has_changes is False

    @pytest.mark.asyncio
    async def test_check_git_changes_with_sync_with_changes(self):
        """Test checking Git-synced branches with changes."""
        # Mock repository data
        mock_repo_data = MagicMock()
        mock_repo_data.branches = {
            "main": "commit-abc123",
            "branch1": "commit-xyz789",  # Different commit from main
        }

        mock_client = MagicMock()
        mock_client.get_list_repositories = AsyncMock(
            return_value={"repo1": mock_repo_data}
        )
        mock_client.default_branch = "main"

        branches = [
            BranchData(
                id="1",
                name="branch1",
                sync_with_git=True,
                is_default=False,
                has_schema_changes=False,
                status=BranchStatus.OPEN,
                branched_from="2023-01-01T00:00:00Z",
            ),
        ]

        mock_progress = MagicMock(spec=Progress)
        mock_progress.add_task = Mock(return_value="task_id")
        mock_progress.advance = Mock()

        results = await check_git_changes(mock_client, branches, mock_progress)

        assert len(results) == 1
        assert results[0].has_changes is True
        assert "repo1" in results[0].repos_with_changes


class TestDisplayReport:
    """Test the display_report function."""

    def test_display_report_empty(self):
        """Test displaying an empty report."""
        mock_console = MagicMock(spec=Console)
        display_report([], [], mock_console, verbose=False)

        # Should print a message about no branches
        mock_console.print.assert_called()
        calls = [str(call) for call in mock_console.print.call_args_list]
        assert any("No branches" in str(call) for call in calls)

    def test_display_report_with_items(self):
        """Test displaying a report with items."""
        items = [
            BranchReportItem(
                branch_name="branch1",
                description="Test",
                sync_with_git=False,
                has_data_changes=False,
                has_proposed_changes=False,
                proposed_changes_count=0,
                has_git_changes=None,
                git_repositories_checked=[],
                can_be_deleted=True,
                status="OPEN",
            ),
        ]
        branches = [
            BranchData(
                id="1",
                name="branch1",
                sync_with_git=False,
                is_default=False,
                has_schema_changes=False,
                status=BranchStatus.OPEN,
                branched_from="2023-01-01T00:00:00Z",
            ),
        ]

        mock_console = MagicMock(spec=Console)
        display_report(items, branches, mock_console, verbose=False)

        # Should print table and summary
        assert mock_console.print.call_count > 0

    def test_display_report_verbose_with_errors(self):
        """Test displaying report in verbose mode with errors."""
        items = [
            BranchReportItem(
                branch_name="branch1",
                description="Test",
                sync_with_git=False,
                has_data_changes=True,
                has_proposed_changes=False,
                proposed_changes_count=0,
                has_git_changes=None,
                git_repositories_checked=[],
                can_be_deleted=False,
                status="OPEN",
                errors=["Diff analysis timeout: timeout occurred"],
            ),
        ]
        branches = [
            BranchData(
                id="1",
                name="branch1",
                sync_with_git=False,
                is_default=False,
                has_schema_changes=False,
                status=BranchStatus.OPEN,
                branched_from="2023-01-01T00:00:00Z",
            ),
        ]

        mock_console = MagicMock(spec=Console)
        display_report(items, branches, mock_console, verbose=True)

        # Should print error details in verbose mode
        calls = [str(call) for call in mock_console.print.call_args_list]
        assert any("timeout" in str(call).lower() for call in calls)

