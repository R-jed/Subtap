"""Tests for engine/git_guard.py — Git state guard."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from subtap.engine.git_guard import GitGuard


@pytest.fixture
def git_workspace(tmp_path: Path) -> Path:
    """Create a git-initialized workspace."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        capture_output=True,
    )
    # Create initial commit so HEAD exists
    (tmp_path / "README.md").write_text("init")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "chore: initialize test repository"],
        cwd=tmp_path,
        capture_output=True,
    )
    return tmp_path


@pytest.fixture
def git_guard(git_workspace: Path) -> GitGuard:
    return GitGuard(git_workspace)


@pytest.fixture
def non_git_workspace(tmp_path: Path) -> Path:
    """A workspace that is NOT a git repo."""
    return tmp_path


# ── pre_task_check ───────────────────────────────────────────


class TestPreTaskCheck:
    """pre_task_check validates git state before pipeline run."""

    def test_clean_git_state_passes(self, git_guard: GitGuard):
        result = git_guard.pre_task_check()
        assert result["ok"] is True
        assert result["issues"] == []

    def test_detects_uncommitted_changes(
        self, git_guard: GitGuard, git_workspace: Path
    ):
        # Create uncommitted file
        (git_workspace / "dirty.txt").write_text("uncommitted")

        result = git_guard.pre_task_check()
        assert result["ok"] is False
        assert any(
            "uncommitted" in issue.lower() or "未提交" in issue
            for issue in result["issues"]
        )

    def test_detects_modified_tracked_file(
        self, git_guard: GitGuard, git_workspace: Path
    ):
        # Modify existing tracked file
        (git_workspace / "README.md").write_text("modified")

        result = git_guard.pre_task_check()
        assert result["ok"] is False

    def test_non_git_repo_reports_error(self, non_git_workspace: Path):
        guard = GitGuard(non_git_workspace)
        result = guard.pre_task_check()
        assert result["ok"] is False
        assert any("git" in issue.lower() for issue in result["issues"])


# ── get_git_status ───────────────────────────────────────────


class TestGetGitStatus:
    """get_git_status returns structured git state info."""

    def test_returns_commit_hash(self, git_guard: GitGuard):
        status = git_guard.get_git_status()
        assert "commit_hash" in status
        assert len(status["commit_hash"]) >= 7  # short hash

    def test_returns_branch_name(self, git_guard: GitGuard):
        status = git_guard.get_git_status()
        assert "branch" in status
        assert isinstance(status["branch"], str)

    def test_returns_dirty_flag(self, git_guard: GitGuard):
        status = git_guard.get_git_status()
        assert "is_dirty" in status
        assert status["is_dirty"] is False

    def test_dirty_workspace_flagged(self, git_guard: GitGuard, git_workspace: Path):
        (git_workspace / "new.txt").write_text("new")
        status = git_guard.get_git_status()
        assert status["is_dirty"] is True

    def test_returns_changed_files(self, git_guard: GitGuard, git_workspace: Path):
        (git_workspace / "new.txt").write_text("new")
        status = git_guard.get_git_status()
        assert "changed_files" in status
        assert isinstance(status["changed_files"], list)


# ── auto_commit_if_needed ────────────────────────────────────


class TestAutoCommitIfNeeded:
    """auto_commit_if_needed commits dirty state with checkpoint message."""

    def test_no_commit_when_clean(self, git_guard: GitGuard, git_workspace: Path):
        result = git_guard.auto_commit_if_needed()
        assert result["committed"] is False

    def test_commits_dirty_state(self, git_guard: GitGuard, git_workspace: Path):
        (git_workspace / "work" / "data.jsonl").parent.mkdir(exist_ok=True)
        (git_workspace / "work" / "data.jsonl").write_text("{}\n")

        result = git_guard.auto_commit_if_needed()
        assert result["committed"] is True
        assert "commit_hash" in result

        # Verify the commit exists
        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=git_workspace,
            capture_output=True,
            text=True,
        )
        assert "chore: checkpoint" in log.stdout

    def test_uses_checkpoint_message(self, git_guard: GitGuard, git_workspace: Path):
        (git_workspace / "temp.txt").write_text("temp")

        git_guard.auto_commit_if_needed()

        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=git_workspace,
            capture_output=True,
            text=True,
        )
        assert "checkpoint before pipeline execution" in log.stdout

    def test_non_git_repo_skips_gracefully(self, non_git_workspace: Path):
        guard = GitGuard(non_git_workspace)
        result = guard.auto_commit_if_needed()
        assert result["committed"] is False
        assert result.get("reason") is not None


# ── is_git_repo ──────────────────────────────────────────────


class TestIsGitRepo:
    """is_git_repo detects git repository."""

    def test_git_repo_returns_true(self, git_guard: GitGuard):
        assert git_guard.is_git_repo() is True

    def test_non_git_returns_false(self, non_git_workspace: Path):
        guard = GitGuard(non_git_workspace)
        assert guard.is_git_repo() is False
