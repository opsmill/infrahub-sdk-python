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
