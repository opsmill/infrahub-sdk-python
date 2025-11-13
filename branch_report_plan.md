# Branch Report Command - Implementation Plan

## Overview

Create a new `infrahubctl branch report` command that analyzes branches in Infrahub to help users identify branches that could potentially be deleted. The report will aggregate multiple data points:

- Whether branches have any data changes (via diff API)
- Whether branches have open proposed changes
- Whether branches have uncommitted Git changes (for branches synced with Git)

## Goals

1. Provide visibility into branch activity across data, proposed changes, and Git repositories
2. Help users make informed decisions about which branches can be safely deleted
3. Handle potentially long-running operations gracefully with progress indicators
4. Present results in a clear, actionable format

## Architecture Overview

### New Files

- `infrahub_sdk/ctl/branch_report.py` - Main implementation of the report command

### Modified Files

- `infrahub_sdk/ctl/branch.py` - Add the `report` subcommand

### Key Components

1. **Branch Data Collection** - Gather all non-default branches
2. **Diff Analysis** - Trigger and wait for diff calculations
3. **Proposed Changes Check** - Query for open proposed changes per branch
4. **Git Repository Analysis** - Check for Git changes in synced branches
5. **Report Generation** - Create formatted output with findings

## Implementation Steps

### Step 1: Create Data Models ✅ COMPLETED

Create Pydantic models to represent the report data:

- `BranchReportItem` - Contains all analysis results for a single branch
- `BranchReportSummary` - Overall summary statistics

**Fields for BranchReportItem:**

- `branch_name: str`
- `description: str | None`
- `branched_from: str` # This should not be included as we only support branched_from the default branch for now
- `sync_with_git: bool`
- `has_data_changes: bool` - From diff analysis
- `has_proposed_changes: bool` - From proposed changes query
- `proposed_changes_count: int`
- `has_git_changes: bool | None` - None if not synced with Git
- `git_repositories_checked: list[str]` - List of repos checked
- `can_be_deleted: bool` - True if no changes in any category
- `status: str` - Branch status (OPEN, etc.)

**Implementation:** Created `infrahub_sdk/ctl/branch_report.py` with both `BranchReportItem` and `BranchReportSummary` models.

### Step 2: Implement Branch Data Collection ✅ COMPLETED

**Function:** `async def get_all_non_default_branches(client: InfrahubClient) -> list[BranchData]`

- Use `client.branch.all()` to fetch all branches
- Filter out the default branch
- Return list of branch data

**Implementation:** Created `get_all_non_default_branches()` function in `infrahub_sdk/ctl/branch_report.py` that:
- Fetches all branches using `client.branch.all()`
- Filters out branches where `is_default=True`
- Returns a list of `BranchData` objects for non-default branches

### Step 3: Implement Diff Analysis ✅ COMPLETED

**Function:** `async def analyze_branch_diffs(client: InfrahubClient, branches: list[BranchData], progress: Progress) -> dict[str, bool]`

This is a critical component that needs careful handling:

**Approach:**

1. For each branch, trigger a diff calculation using `client.create_diff()`
   - Use `branch.branched_from` as the `from_time`
   - Use current time as `to_time`
   - Set `wait_until_completion=True` to ensure diff is ready
   - Generate a unique diff name (e.g., `f"branch-report-{branch_name}-{timestamp}"`)

2. Query the diff results using `client.get_diff_summary()`
   - Parse the NodeDiff results to determine if there are any changes
   - A branch has changes if any node has `action != 'UNCHANGED'` or has elements with changes

3. Return a dict mapping `branch_name -> has_changes`

**Progress Tracking:**

- Create a Rich Progress task for "Analyzing branch diffs"
- Update progress for each branch analyzed

**Implementation:** Created `analyze_branch_diffs()` function in `infrahub_sdk/ctl/branch_report.py` that:
- Creates a progress task for tracking
- For each branch:
  - Parses the `branched_from` timestamp using `Timestamp` class
  - Generates a unique diff name using branch name and current timestamp
  - Creates a diff calculation with `wait_until_completion=True`
  - Retrieves diff summary using `client.get_diff_summary()`
  - Uses helper function `_has_diff_changes()` to determine if changes exist
  - Handles exceptions gracefully by marking branch as having changes (conservative approach)
- Returns dictionary mapping branch name to boolean indicating whether changes exist

**Helper Function:** `_has_diff_changes()` checks if any NodeDiff contains:
- Node action != 'UNCHANGED'
- OR any element with action != 'UNCHANGED'
- OR any element with non-zero summary values (added, updated, removed)

**Questions:**

- Should we use a specific time range for diffs, or compare from branch creation to now? **RESOLVED**: Using branch creation time (`branched_from`) to current time
- Do we need to clean up the diff calculations after we're done? **TODO**: Consider cleanup in future enhancement

### Step 4: Implement Proposed Changes Check ✅ COMPLETED

**Function:** `async def check_proposed_changes(client: InfrahubClient, branches: list[BranchData], progress: Progress) -> dict[str, tuple[bool, int]]`

**Approach:**

1. Query for CoreProposedChange objects filtered by source_branch
2. Filter for open/active proposed changes (not merged, closed, or canceled)
3. Count the number of open proposed changes per branch

**GraphQL Query Structure:**

```graphql
query GetProposedChanges {
  CoreProposedChange {
    source_branch {
      value
    }
    state {
      value
    }
  }
}
```

**Return:**

- Dict mapping `branch_name -> (has_open_pcs, count)`

**Progress Tracking:**

- Single task for "Checking proposed changes"

**Implementation:** Created `check_proposed_changes()` function in `infrahub_sdk/ctl/branch_report.py` that:
- Queries all CoreProposedChange objects using `client.filters()` with `include=["source_branch", "state"]`
- Initializes results dictionary with all branches set to (False, 0)
- Iterates through proposed changes and:
  - Extracts source branch name via relationship peer access
  - Extracts state value
  - Counts only "open" and "closed" states (not "merged" or "cancelled")
- Returns dictionary mapping branch name to tuple of (has_open_changes, count)
- Handles errors gracefully with try-except (conservative approach)

**Questions:**

- What states are considered "open"? These would be "open" or "closed" as someone could reopen a proposed change that have been closed, but if a proposed change is merged or cancelled it can never be opened again. **RESOLVED**: Implemented to filter for "open" and "closed" states only
- Should we also check destination_branch or only source_branch? **RESOLVED**: Only source_branch is relevant

### Step 5: Implement Git Repository Analysis ✅ COMPLETED

**Function:** `async def check_git_changes(client: InfrahubClient, branches: list[BranchData], progress: Progress) -> dict[str, tuple[bool, list[str]]]`

**Implementation:** Created `check_git_changes()` function in `infrahub_sdk/ctl/branch_report.py` that:
- Uses `client.get_list_repositories()` to query all repositories (CoreGenericRepository includes both CoreRepository and CoreReadOnlyRepository)
- Queries repository information across all branches in a single batch operation
- For each branch with `sync_with_git=True`:
  - Compares the commit ID on the branch with the commit ID on the default branch for each repository
  - If commits differ, the branch has Git changes in that repository
  - Collects a list of repository names with changes
- Returns dictionary mapping branch name to tuple of (has_changes, list_of_repos_with_changes)
- For branches not synced with Git, returns `(False, [])` 
- Handles errors gracefully with try-except (conservative approach: marks synced branches as potentially having changes)

**Approach Chosen:** Option B - Query repository commit information
- Leverages the existing `get_list_repositories()` method which efficiently queries all repositories across branches
- Compares commit IDs between the branch and the default branch
- If commits differ, it indicates the branch has different Git state than the default branch
- This approach handles both CoreRepository and CoreReadOnlyRepository automatically via CoreGenericRepository query

**Progress Tracking:**
- Creates progress task for "Checking Git repositories"
- Updates progress for each branch analyzed

**Resolution of Questions:**
- **Best way to check Git changes:** Used `client.get_list_repositories()` which queries commit information across branches
- **Commit vs file changes:** Checking commit differences is sufficient - different commits indicate Git changes
- **CoreRepository vs CoreReadOnlyRepository:** Both are handled automatically via CoreGenericRepository query

### Step 6: Aggregate Results ✅ COMPLETED

**Function:** `def build_report_items(branches: list[BranchData], diff_results: dict, pc_results: dict, git_results: dict) -> list[BranchReportItem]`

- Combine all analysis results into BranchReportItem objects
- Calculate `can_be_deleted` based on all factors:
  - No data changes AND
  - No open proposed changes AND
  - No Git changes (or not synced with Git)
- Sort results by `can_be_deleted` (deletable first), then by name

**Implementation:** Created `build_report_items()` function in `infrahub_sdk/ctl/branch_report.py` that:
- Iterates through all branches and aggregates results from diff, proposed changes, and Git analyses
- Extracts results for each branch with conservative defaults (e.g., if data missing, assume changes exist)
- Properly handles Git changes: sets to `None` for branches not synced with Git
- Calculates `can_be_deleted` flag using logical AND of all criteria:
  - No data changes
  - No open proposed changes
  - No Git changes (or Git sync is disabled)
- Creates `BranchReportItem` objects with all relevant fields populated
- Sorts results with deletable branches first (using `not item.can_be_deleted` as primary key), then alphabetically by branch name
- Returns sorted list of `BranchReportItem` objects ready for display

### Step 7: Generate Report Output ✅ COMPLETED

**Function:** `def display_report(report_items: list[BranchReportItem], console: Console) -> None`

**Output Format (Rich Table):**

- **Branch Name** - Branch identifier
- **Age** - Time since branched_from (using existing `calculate_time_diff`)
- **Data Changes** - ✓/✗
- **Proposed Changes** - Count (0 if none)
- **Git Changes** - ✓/✗/N/A (N/A if not synced)
- **Can Delete?** - ✓/✗ with color coding
- **Status** - Branch status

**Color Coding:**

- Green ✓ for branches that can be deleted
- Red ✗ for branches with activity
- Yellow for warnings

**Summary Section:**

- Total branches analyzed
- Branches that can potentially be deleted
- Branches with data changes
- Branches with proposed changes
- Branches with Git changes

**Implementation:** Created two functions in `infrahub_sdk/ctl/branch_report.py`:

1. **`calculate_summary()`** - Aggregates statistics from report items and returns `BranchReportSummary`:
   - Counts total branches analyzed
   - Counts deletable branches
   - Counts branches with data changes, proposed changes, and Git changes
   - Counts branches synced with Git

2. **`display_report()`** - Displays the branch report using Rich table formatting:
   - Creates a Rich table with columns: Branch Name, Age, Data Changes, Proposed Changes, Git Changes, Can Delete?, Status
   - Uses `calculate_time_diff()` to format branch age from `branched_from` timestamp
   - Color codes entries:
     - Green ✓ for no changes/can delete
     - Red ✗ for changes present/cannot delete
     - Dim N/A for Git changes when not synced with Git
   - Shows repository names for branches with Git changes
   - Displays comprehensive summary section with:
     - Total branches analyzed
     - Number of deletable branches (green)
     - Number of branches with data changes (red)
     - Number of branches with proposed changes (red)
     - Number of branches with Git changes and total synced with Git (red)
   - Handles empty report gracefully with a message

### Step 8: Main Command Implementation ✅ COMPLETED

**Function:** `async def report(config: str = CONFIG_PARAM) -> None`

**Implementation:** Created the `report` command in `infrahub_sdk/ctl/branch.py` that:
- Initializes the Infrahub client using `initialize_client()`
- Sets up Rich progress display with spinner, text, bar, and task progress columns
- Orchestrates all analysis steps in sequence:
  1. Fetches all non-default branches using `get_all_non_default_branches()`
  2. Analyzes branch diffs using `analyze_branch_diffs()` with progress tracking
  3. Checks for proposed changes using `check_proposed_changes()` with progress tracking
  4. Checks for Git changes using `check_git_changes()` with progress tracking
  5. Builds the report items using `build_report_items()`
- Displays the final report using `display_report()`
- Handles edge case of no non-default branches with informative message
- Uses `@app.command("report")` decorator to register the command
- Uses `@catch_exception(console=console)` decorator for error handling
- Suppresses SDK logging output for cleaner user experience

**Integration:**
- Added necessary imports to `branch.py`:
  - Rich progress components (SpinnerColumn, Progress, BarColumn, TaskProgressColumn, TextColumn)
  - All branch report functions from `branch_report.py`
- Command is now available as `infrahubctl branch report`

### Step 9: Error Handling ✅ COMPLETED

Implement robust error handling for:

- Network failures during API calls
- Timeout errors for long-running diff operations
- Permission errors (user might not have access to all data)
- Missing Git repositories

**Approach:**

- Wrap individual branch analysis in try-except blocks
- Continue processing other branches if one fails
- Include error information in the report
- Add a `--verbose` flag for detailed error output

**Implementation:** Comprehensive error handling has been added throughout the branch report functionality:

1. **Enhanced Data Models:**
   - Added `errors: list[str]` field to `BranchReportItem` to track errors per branch

2. **Improved Error Handling in Analysis Functions:**
   - `analyze_branch_diffs()` now returns tuple of `(results, errors)` and catches:
     - `TimeoutError` - for diff calculation timeouts
     - `PermissionError` - for permission denied errors
     - `Exception` - for any other unexpected errors
   - `check_proposed_changes()` now returns tuple of `(results, errors)` and catches:
     - `PermissionError` - for permission denied when querying proposed changes
     - `Exception` - for any other errors (applies to all branches globally)
   - `check_git_changes()` now returns tuple of `(results, errors)` and catches:
     - `PermissionError` - for permission denied when querying Git repositories
     - `Exception` - for any other errors (applies to all synced branches)

3. **Error Aggregation:**
   - `build_report_items()` now accepts error dictionaries from all analysis functions
   - Aggregates all errors for each branch into the report item
   - Conservative approach: branches with errors are assumed to have changes (safer to keep)

4. **Enhanced Display with Error Reporting:**
   - `display_report()` now accepts `verbose` parameter
   - Shows warning symbol (⚠) in table cells when errors occurred during analysis
   - Summary includes count of branches with errors
   - In verbose mode, displays detailed error information per branch with explanation

5. **Command Line Interface:**
   - Added `--verbose` / `-v` flag to `infrahubctl branch report` command
   - Updated command documentation to explain error handling behavior
   - Updated command to unpack error tuples from analysis functions
   - Passes verbose flag to display function

**Error Handling Strategy:**
- **Graceful Degradation:** Errors in one branch don't stop analysis of other branches
- **Conservative Defaults:** When analysis fails, assume changes exist (safer to keep the branch)
- **Transparent Reporting:** Errors are tracked and can be displayed with `--verbose` flag
- **User Guidance:** Clear messages explain that branches with errors are handled conservatively

**Refactoring Improvement - Result Objects:**
After initial implementation, the error handling was refactored to use dedicated result objects instead of tuples of dictionaries:

- **Created Result Models:**
  - `DiffAnalysisResult` - Contains branch name, has_changes, and optional error
  - `ProposedChangesResult` - Contains branch name, has_changes, count, and optional error
  - `GitChangesResult` - Contains branch name, has_changes, repos_with_changes, and optional error

- **Benefits:**
  - Much easier to understand - each branch's result is self-contained
  - Type-safe - Pydantic models provide validation
  - No need to match keys across multiple dictionaries
  - Cleaner function signatures: `-> list[DiffAnalysisResult]` instead of `-> tuple[dict[str, bool], dict[str, str]]`
  - More maintainable code with better encapsulation

- **Updated Functions:**
  - `analyze_branch_diffs()` now returns `list[DiffAnalysisResult]`
  - `check_proposed_changes()` now returns `list[ProposedChangesResult]`
  - `check_git_changes()` now returns `list[GitChangesResult]`
  - `build_report_items()` accepts lists of result objects instead of separate dictionaries

### Step 10: Testing Considerations ✅ COMPLETED

**Unit Tests** (`tests/unit/ctl/test_branch_report.py`):

- Test data model validation
- Test report aggregation logic
- Test output formatting
- Mock API responses

**Integration Tests** (`tests/integration/test_branch_report.py`):

- Test with actual Infrahub instance (if available)
- Test with various branch configurations
- Test error handling

**Implementation:** Created comprehensive test suites:

1. **Unit Tests** (`tests/unit/ctl/test_branch_report.py`) - 35 tests covering:
   - **Data Models** (6 tests):
     - BranchReportItem creation and validation
     - BranchReportSummary creation
     - Result models (DiffAnalysisResult, ProposedChangesResult, GitChangesResult)
   
   - **Helper Functions** (8 tests):
     - `_has_diff_changes()` with various scenarios:
       - No changes
       - Node action changed
       - Element action changed
       - Summary values (added, updated, removed)
       - Multiple nodes
   
   - **Build Report Items** (4 tests):
     - Basic report building
     - Report with various changes
     - Report with errors
     - Sorting verification (deletable first)
   
   - **Summary Calculation** (3 tests):
     - Empty summary
     - Basic summary
     - Comprehensive summary with all metrics
   
   - **Async Functions with Mocks** (14 tests):
     - `get_all_non_default_branches()` - fetching and filtering branches
     - `analyze_branch_diffs()` - with changes, no changes, timeout, permission errors
     - `check_proposed_changes()` - no PCs, with PCs
     - `check_git_changes()` - no sync, with sync (changes and no changes)
     - `display_report()` - empty, with items, verbose mode with errors

2. **Integration Tests** (`tests/integration/test_branch_report.py`) - Tests using TestInfrahubDockerClient:
   - **Basic Operations**:
     - `test_get_all_non_default_branches_integration()` - Fetch branches from real instance
     - `test_analyze_branch_diffs_integration()` - Diff analysis with real API
     - `test_check_proposed_changes_integration()` - Proposed changes check
     - `test_check_git_changes_integration()` - Git changes check
   
   - **Complete Workflows**:
     - `test_full_report_workflow_integration()` - End-to-end report generation
     - `test_report_with_data_changes_integration()` - Report when branch has data
     - `test_report_display_verbose_mode_integration()` - Display in both modes
   
   - **Edge Cases**:
     - `test_empty_branches_list()` - No branches to analyze
     - `test_branch_with_git_sync()` - Git-synced branches
     - `test_report_sorting()` - Verify sorting logic

**Test Results:**
- ✅ All 35 unit tests pass
- Integration tests require Docker environment (TestInfrahubDockerClient)
- Tests use proper fixtures and mocking patterns consistent with existing codebase
- Error scenarios are comprehensively covered

## Command Line Interface

### Basic Usage

```bash
infrahubctl branch report
```

### Potential Future Options

```bash
# Show only deletable branches
infrahubctl branch report --deletable-only

# Output as JSON
infrahubctl branch report --format json

# Save to file
infrahubctl branch report --output report.txt

# Skip Git analysis (faster)
infrahubctl branch report --skip-git

# Verbose error output
infrahubctl branch report --verbose
```

## Dependencies

All dependencies are already available:

- `rich` - For progress indicators and tables
- `typer` - For CLI framework
- `pydantic` - For data models
- Existing Infrahub SDK client methods

## Open Questions

### Critical Questions (Need Answers Before Implementation)

1. **Diff API Usage:**
   - What's the recommended pattern for triggering diffs programmatically?
   - Should we create a unique diff name for each run, or reuse?
   - Do diff calculations need to be cleaned up after use?
   - What timeout should we use for diff completion?

2. **Proposed Changes:**
   - What are all the possible states for CoreProposedChange.state?
   - Which states should be considered "open" for our analysis?
   - Should we check both source_branch and destination_branch?

3. **Git Repository Integration:**
   - What's the best API to check for Git changes per branch?
   - Is there a `/api/git/diff` or similar endpoint?
   - How do we handle branches that exist in Infrahub but not in Git?
   - Should we differentiate between CoreRepository and CoreReadOnlyRepository?

4. **Performance:**
   - For large Infrahub instances with many branches, this could take a long time
   - Should we implement parallel processing for diff calculations?
   - Should there be a limit on the number of branches to analyze?
   - Should we batch API requests?

5. **User Experience:**
   - Should there be a confirmation prompt before analyzing many branches?
   - Should we provide an estimate of how long the analysis will take?
   - Should results be cached for a period of time?

### Nice-to-Have Questions

6. **Additional Metrics:**
   - Should we include branch age in the decision criteria?
   - Should we check for any active tasks on the branch?
   - Should we include branch description in the report?

7. **Interactive Mode:**
   - Should we offer an interactive mode to delete branches directly from the report?
   - Should we support bulk operations?

## Success Criteria

- ✓ Command successfully analyzes all non-default branches
- ✓ Accurately identifies branches with data changes
- ✓ Accurately identifies branches with proposed changes
- ✓ Accurately identifies branches with Git changes (when applicable)
- ✓ Provides clear, actionable output
- ✓ Handles errors gracefully
- ✓ Performance is acceptable for instances with dozens of branches
- ✓ Progress indicators provide good user feedback during analysis

## Future Enhancements

1. Export report to JSON/CSV/Excel
2. Interactive deletion mode
3. Scheduled reporting (cron-friendly)
4. Integration with CI/CD for automated branch cleanup
5. Branch age-based recommendations
6. Branch activity metrics (last commit, last change, etc.)
7. Webhook integration for notifications
8. Dashboard visualization of branch health
