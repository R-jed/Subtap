"""Git state guard — validates and auto-commits before pipeline execution."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


class GitGuard:
    """Git state validation and auto-commit for pipeline safety.

    Ensures the workspace is in a clean git state before running,
    and optionally auto-commits dirty state as a checkpoint.
    """

    def __init__(self, workspace_root: Path):
        self.root = workspace_root

    def is_git_repo(self) -> bool:
        """Check if workspace is inside a git repository."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=self.root, capture_output=True, text=True,
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False

    def get_git_status(self) -> dict[str, Any]:
        """Get structured git state info.

        Returns:
            {
                "commit_hash": str,
                "branch": str,
                "is_dirty": bool,
                "changed_files": list[str],
            }
        """
        if not self.is_git_repo():
            return {"commit_hash": "", "branch": "", "is_dirty": False, "changed_files": []}

        # Get short commit hash
        hash_result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=self.root, capture_output=True, text=True,
        )
        commit_hash = hash_result.stdout.strip()

        # Get branch name
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=self.root, capture_output=True, text=True,
        )
        branch = branch_result.stdout.strip()

        # Get changed files
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=self.root, capture_output=True, text=True,
        )
        changed_files = []
        for line in status_result.stdout.strip().splitlines():
            if line.strip():
                # Format: "XY filename"
                changed_files.append(line[3:].strip())

        return {
            "commit_hash": commit_hash,
            "branch": branch,
            "is_dirty": len(changed_files) > 0,
            "changed_files": changed_files,
        }

    def pre_task_check(self) -> dict[str, Any]:
        """Validate git state before pipeline execution.

        Returns:
            {"ok": bool, "issues": list[str]}
        """
        issues: list[str] = []

        if not self.is_git_repo():
            issues.append("工作目录不在 git 仓库中")
            return {"ok": False, "issues": issues}

        status = self.get_git_status()
        if status["is_dirty"]:
            count = len(status["changed_files"])
            issues.append(f"存在 {count} 个未提交的变更文件")
            for f in status["changed_files"][:5]:  # show first 5
                issues.append(f"  - {f}")
            if count > 5:
                issues.append(f"  ...及其他 {count - 5} 个文件")

        return {"ok": len(issues) == 0, "issues": issues}

    def auto_commit_if_needed(self) -> dict[str, Any]:
        """Auto-commit dirty state with checkpoint message.

        Only commits if there are actual changes. Uses message:
        "auto: checkpoint before pipeline execution"

        Returns:
            {"committed": bool, "commit_hash": str, "reason": str}
        """
        if not self.is_git_repo():
            return {"committed": False, "reason": "非 git 仓库，跳过自动提交"}

        status = self.get_git_status()
        if not status["is_dirty"]:
            return {"committed": False, "reason": "工作区干净，无需提交"}

        # Stage all changes
        subprocess.run(["git", "add", "-A"], cwd=self.root, capture_output=True)

        # Commit with checkpoint message
        result = subprocess.run(
            ["git", "commit", "-m", "auto: checkpoint before pipeline execution"],
            cwd=self.root, capture_output=True, text=True,
        )

        if result.returncode != 0:
            return {"committed": False, "reason": f"提交失败: {result.stderr.strip()}"}

        # Get new commit hash
        hash_result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=self.root, capture_output=True, text=True,
        )

        return {
            "committed": True,
            "commit_hash": hash_result.stdout.strip(),
            "reason": "已自动提交工作区变更",
        }
