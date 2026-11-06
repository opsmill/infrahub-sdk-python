from __future__ import annotations

import pytest
from invoke import Exit

import tasks


class TestRequireTool:
    """Verify that require_tool() raises with a helpful message when an external tool is missing."""

    def test_raises_when_tool_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Arrange
        monkeypatch.setattr(tasks, "which", lambda _name: None)

        # Act / Assert
        with pytest.raises(Exit, match="mytool is not installed"):
            tasks.require_tool("mytool", "Install it with: pip install mytool")

    def test_passes_when_tool_installed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Arrange
        monkeypatch.setattr(tasks, "which", lambda _name: "/usr/bin/mytool")

        # Act / Assert — no exception means tool is found
        tasks.require_tool("mytool", "Install it with: pip install mytool")

    def test_error_message_contains_install_hint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Arrange
        monkeypatch.setattr(tasks, "which", lambda _name: None)

        # Act / Assert
        with pytest.raises(Exit, match="Install it with: npm install"):
            tasks.require_tool("sometool", "Install it with: npm install")


INTEGRATION_DIRECTORY = tasks.MAIN_DIRECTORY_PATH / tasks.INTEGRATION_TEST_DIRECTORY


def _listed_files() -> list[str]:
    return [path for paths in tasks.INTEGRATION_TEST_SHARDS.values() for path in paths]


def _shard_files(shard: str) -> set[str]:
    """Resolve a shard's pytest arguments to the integration test files it runs."""
    args = tasks._integration_shard_targets(shard).split()
    prefix = f"{tasks.INTEGRATION_TEST_DIRECTORY}/"
    if args[0] == tasks.INTEGRATION_TEST_DIRECTORY:
        ignored = {arg.removeprefix(f"--ignore={prefix}") for arg in args[1:]}
        return {path.name for path in INTEGRATION_DIRECTORY.glob("test_*.py")} - ignored
    return {arg.removeprefix(prefix) for arg in args}


class TestIntegrationShards:
    """Verify that the CI shards run every integration test file exactly once."""

    def test_listed_files_exist(self) -> None:
        missing = [path for path in _listed_files() if not (INTEGRATION_DIRECTORY / path).is_file()]

        assert not missing

    def test_listed_files_are_unique(self) -> None:
        listed = _listed_files()

        assert len(listed) == len(set(listed))

    def test_shards_cover_every_file_once(self) -> None:
        all_files = {path.name for path in INTEGRATION_DIRECTORY.glob("test_*.py")}
        shards = [*tasks.INTEGRATION_TEST_SHARDS, tasks.INTEGRATION_TEST_CATCHALL_SHARD]
        files_per_shard = [_shard_files(shard) for shard in shards]

        assert sum(len(files) for files in files_per_shard) == len(all_files)
        assert set().union(*files_per_shard) == all_files

    def test_unknown_shard_raises(self) -> None:
        with pytest.raises(Exit, match="Unknown integration test shard 'missing'"):
            tasks._integration_shard_targets("missing")
