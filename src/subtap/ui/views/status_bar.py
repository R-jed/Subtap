"""Status bar component for TUI home page."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


class StatusBar:
    """Renders model readiness, disk space, and pending job status."""

    def __init__(self, subtap_root: Path | None = None):
        self.root = subtap_root or (Path.home() / ".subtap")

    def check_models(self) -> dict:
        """Check model installation status. Non-blocking."""
        try:
            from subtap.schemas.config import load_config
            from subtap.core.models import ModelRegistry

            config_path = self.root / "config.yaml"
            config = load_config(config_path) if config_path.exists() else None
            if config is None:
                return {"all_ready": False, "installed_count": 0, "total": 0}

            registry = ModelRegistry(config)
            statuses = registry.status()
            installed = sum(1 for s in statuses if s.installed)
            return {
                "all_ready": installed == len(statuses),
                "installed_count": installed,
                "total": len(statuses),
            }
        except Exception:
            logger.exception("check_models failed")
            return {"all_ready": False, "installed_count": 0, "total": 0}

    def check_disk(self) -> dict:
        """Check ~/.subtap disk usage."""
        try:
            total = sum(
                f.stat().st_size for f in self.root.rglob("*") if f.is_file()
            )
            usage = shutil.disk_usage(self.root)
            return {
                "used_bytes": total,
                "free_bytes": usage.free,
            }
        except Exception:
            logger.exception("check_disk failed")
            return {"used_bytes": 0, "free_bytes": 0}

    def check_pending_jobs(self) -> int:
        """Count pending job directories."""
        jobs_dir = self.root / "jobs"
        if not jobs_dir.exists():
            return 0
        return sum(1 for d in jobs_dir.iterdir() if d.is_dir())

    def render(self) -> list[str]:
        """Render 3 status lines as ANSI strings."""
        from subtap.ui.theme import Theme

        t = Theme()
        models = self.check_models()
        disk = self.check_disk()
        pending = self.check_pending_jobs()

        # Model status
        if models["all_ready"]:
            model_line = f"  {t.GREEN}✓ 模型就绪{t.NC}（{models['installed_count']}/{models['total']}）"
        else:
            model_line = f"  {t.YELLOW}⚠ 模型未就绪{t.NC}（{models['installed_count']}/{models['total']}）"

        # Disk status
        free_gb = disk["free_bytes"] / (1024**3)
        if free_gb < 5:
            disk_line = f"  {t.RED}✗ 磁盘空间不足{t.NC}（剩余 {free_gb:.1f} GB）"
        else:
            disk_line = f"  {t.GREEN}✓ 磁盘空间充足{t.NC}（剩余 {free_gb:.1f} GB）"

        # Pending jobs
        if pending > 0:
            job_line = f"  {t.YELLOW}⏳ {pending} 个未完成任务{t.NC}"
        else:
            job_line = f"  {t.GREEN}✓ 无待处理任务{t.NC}"

        return [model_line, disk_line, job_line]
