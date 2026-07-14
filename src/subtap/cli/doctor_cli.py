"""Doctor 命令：系统诊断和工作区状态检查."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import typer

from subtap.cli._utils import auto_json


def _collect_workspace_status(work_dir: Path = Path("./work")) -> dict[str, Any]:
    """Collect workspace status as structured data (pure function, no side effects)."""
    from subtap.engine.git_guard import GitGuard
    from subtap.engine.cleanroom import Cleanroom

    git_guard = GitGuard(work_dir)
    git_status = git_guard.get_git_status()

    cleanroom = Cleanroom(work_dir)
    cr_result = cleanroom.check_workspace()
    model_status = cleanroom.check_model_status()

    pipeline_files = {
        name: (work_dir / name).exists()
        for name in (
            "chunks/chunks.jsonl",
            "asr/asr.jsonl",
            "cleaned.jsonl",
            "sentences.jsonl",
            "aligned.jsonl",
        )
    }

    return {
        "git": {
            "is_repo": git_guard.is_git_repo(),
            "branch": git_status["branch"],
            "commit_hash": git_status["commit_hash"],
            "dirty": git_status["is_dirty"],
            "changed_files": git_status["changed_files"],
        },
        "cleanroom": cr_result,
        "models": model_status["models"],
        "pipeline_files": pipeline_files,
    }


def _render_workspace_status(status: dict[str, Any]) -> None:
    """Render workspace status as human-readable text."""
    typer.echo("═══ 工作区状态检查 ═══\n")

    # 1. Git 状态
    git = status["git"]
    if git["is_repo"]:
        typer.echo("▸ Git 状态")
        typer.echo(f"  分支: {git['branch']}")
        typer.echo(f"  提交: {git['commit_hash']}")
        dirty_icon = (
            typer.style("✗ 脏", fg=typer.colors.RED)
            if git["dirty"]
            else typer.style("✓ 干净", fg=typer.colors.GREEN)
        )
        typer.echo(f"  状态: {dirty_icon}")
        if git["changed_files"]:
            for f in git["changed_files"][:5]:
                typer.echo(f"    - {f}")
    else:
        typer.echo("▸ Git 状态")
        typer.echo(typer.style("  ⚠ 非 Git 仓库", fg=typer.colors.YELLOW))

    # 2. 工作环境卫生
    cr_result = status["cleanroom"]
    typer.echo("\n▸ 工作环境卫生")
    clean_icon = (
        typer.style("✓ 干净", fg=typer.colors.GREEN)
        if cr_result["is_clean"]
        else typer.style("⚠ 有问题", fg=typer.colors.YELLOW)
    )
    typer.echo(f"  状态: {clean_icon}")
    if cr_result["issues"]:
        for issue in cr_result["issues"]:
            typer.echo(f"    - {issue}")

    # 3. 模型状态
    typer.echo("\n▸ 模型状态")
    for m in status["models"]:
        icon = (
            typer.style("✓", fg=typer.colors.GREEN)
            if m["installed"]
            else typer.style("✗", fg=typer.colors.RED)
        )
        typer.echo(f"  {icon} {m['name']}")

    # 4. Pipeline 状态
    labels = {
        "chunks/chunks.jsonl": "切段结果",
        "asr/asr.jsonl": "ASR 结果",
        "cleaned.jsonl": "清洗结果",
        "sentences.jsonl": "断句结果",
        "aligned.jsonl": "对齐结果",
    }
    typer.echo("\n▸ Pipeline 中间文件")
    for name, exists in status["pipeline_files"].items():
        icon = (
            typer.style("✓", fg=typer.colors.GREEN)
            if exists
            else typer.style("○", fg=typer.colors.WHITE)
        )
        typer.echo(f"  {icon} {labels[name]}")

    typer.echo("\n═══ 检查完成 ═══")


def doctor(
    release: bool = typer.Option(False, "--release", help="执行发布前完整检查"),
    workspace: bool = typer.Option(False, "--workspace", "-ws", help="检查工作区状态"),
    json_output: bool = typer.Option(False, "--json", help="输出机器可读 JSON"),
) -> None:
    """检查系统依赖和运行环境"""
    json_output = auto_json(json_output)

    # ── Workspace mode ──────────────────────────────────────
    workspace_status = _collect_workspace_status() if workspace else None

    # Standalone workspace without --release and --json: text output and return
    if workspace and not release and not json_output:
        assert workspace_status is not None  # workspace=True guarantees collection
        _render_workspace_status(workspace_status)
        return

    checks: list[tuple[str, str, bool, str]] = []

    # 基础依赖
    ffmpeg_ok = shutil.which("ffmpeg") is not None
    checks.append(
        (
            "ffmpeg",
            "音视频处理",
            ffmpeg_ok,
            "" if ffmpeg_ok else "未找到，请安装：brew install ffmpeg",
        )
    )

    ffprobe_ok = shutil.which("ffprobe") is not None
    checks.append(
        (
            "ffprobe",
            "媒体探测",
            ffprobe_ok,
            "" if ffprobe_ok else "未找到，请安装：brew install ffmpeg",
        )
    )

    py_ver = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    py_ok = sys.version_info >= (3, 10)
    checks.append(
        (
            "python",
            "Python 版本",
            py_ok,
            f"v{py_ver}" if py_ok else f"v{py_ver}（需要 >= 3.10）",
        )
    )

    # 工作空间
    subtap_dir = Path.home() / ".subtap"
    ws_ok = (
        subtap_dir.exists() and os.access(str(subtap_dir), os.W_OK)
        if subtap_dir.exists()
        else False
    )
    checks.append(
        (
            "workspace",
            "工作空间",
            ws_ok,
            "" if ws_ok else f"不可写或不存在：{subtap_dir}",
        )
    )

    # --release 模式：增加模型和 TUI 检查
    if release:
        import importlib.util

        # MLX 运行时
        mlx_ok = importlib.util.find_spec("mlx") is not None
        checks.append(
            (
                "mlx",
                "MLX 运行时",
                mlx_ok,
                "" if mlx_ok else "未安装，请：pip install mlx",
            )
        )

        # mlx-audio
        mla_ok = importlib.util.find_spec("mlx_audio") is not None
        checks.append(
            (
                "mlx-audio",
                "MLX Audio",
                mla_ok,
                "" if mla_ok else "未安装，请：pip install mlx-audio",
            )
        )

        # rich
        rich_ok = importlib.util.find_spec("rich") is not None
        checks.append(
            (
                "rich",
                "Rich TUI",
                rich_ok,
                "" if rich_ok else "未安装，请：pip install rich",
            )
        )

    # 打印结果
    all_ok = True
    report: dict[str, Any] = {
        "ok": True,
        "release": release,
        "checks": [],
        "config": {},
        "models": [],
    }
    if workspace_status is not None:
        report["workspace_status"] = workspace_status
    for _name, label, ok, detail in checks:
        report["checks"].append(
            {"name": _name, "label": label, "ok": ok, "detail": detail}
        )
        icon = (
            typer.style("✓", fg=typer.colors.GREEN)
            if ok
            else typer.style("✗", fg=typer.colors.RED)
        )
        msg = f"  {icon} {label}"
        if detail:
            msg += f" — {detail}"
        if not json_output:
            typer.echo(msg)
        if not ok:
            all_ok = False

    # ── 配置状态 ───────────────────────────────────────────
    if not json_output:
        typer.echo("\n▸ 配置状态")
    config_path = subtap_dir / "config.yaml"
    if config_path.exists():
        report["config"] = {"path": str(config_path), "exists": True, "valid": False}
        if not json_output:
            typer.echo(f"  ✓ {config_path} 存在")
        try:
            from subtap.schemas.config import load_config

            load_config(config_path)
            report["config"]["valid"] = True
            if not json_output:
                typer.echo("  ✓ 配置文件有效")
        except Exception as e:
            report["config"]["error"] = str(e)
            if not json_output:
                typer.echo(f"  ✗ 配置文件无效：{e}")
            all_ok = False
    else:
        report["config"] = {"path": str(config_path), "exists": False, "valid": False}
        if not json_output:
            typer.echo(f"  ✗ {config_path} 不存在")
        all_ok = False

    # ── 目录结构完整性 ────────────────────────────────────
    from subtap.core.safe_delete import _EXPECTED_DIRS

    dir_results: list[dict[str, Any]] = []
    for rel in _EXPECTED_DIRS:
        full = subtap_dir / rel
        exists = full.exists()
        dir_results.append({"name": rel, "exists": exists})
    report["directories"] = dir_results

    if not json_output:
        typer.echo("\n▸ 目录结构完整性")
        for d in dir_results:
            icon = (
                typer.style("✓", fg=typer.colors.GREEN)
                if d["exists"]
                else typer.style("✗", fg=typer.colors.RED)
            )
            typer.echo(f"  {icon} {d['name']}")

    # ── 清单版本 ─────────────────────────────────────────
    from subtap.core.manifest import get_manifest_path, load_manifest

    manifest_info: dict[str, Any] = {"exists": False}
    try:
        # Resolve manifest path using a minimal config stub
        _config_stub = SimpleNamespace(
            models=SimpleNamespace(root=str(subtap_dir / "models"))
        )
        manifest_path = get_manifest_path(_config_stub)
        if manifest_path.exists():
            mm = load_manifest(manifest_path)
            manifest_info = {
                "exists": True,
                "version": mm.version,
                "model_count": len(mm.models),
                "path": str(manifest_path),
            }
    except Exception as e:
        manifest_info["error"] = str(e)
    report["manifest"] = manifest_info

    if not json_output:
        typer.echo("\n▸ 清单版本")
        if manifest_info.get("exists"):
            typer.echo(
                f"  ✓ 版本: {manifest_info['version']}，模型数: {manifest_info['model_count']}"
            )
        else:
            err = manifest_info.get("error", "文件不存在")
            typer.echo(f"  ⚠ 清单不可用: {err}")

    # ── 模型状态 ───────────────────────────────────────────
    if not json_output:
        typer.echo("\n▸ 模型状态")
    try:
        from subtap.schemas.config import load_config
        from subtap.core.models import ModelRegistry

        config = load_config(config_path)
        report["runtime"] = {
            "asr_model": config.asr.model,
            "asr_quantization": config.asr.quantization,
            "aligner_model": config.align.model,
            "aligner_quantization": config.align.quantization,
            "keep_model_alive": bool(
                config.asr.keep_model_alive or config.align.keep_model_alive
            ),
            "warmup": False,  # 预热功能未启用
            "device_backend": "mlx-metal",
        }
        external_audio_sent = getattr(config.asr, "backend", "") == "http-asr"
        report["privacy"] = {
            "external_audio_sent": external_audio_sent,
            "local_only_available": True,
            "default_local": True,
        }
        report["output"] = {
            "default_dir": "./output",
            "final_outputs": ["final.srt", "final.vtt", "final.json", "final.tsv"],
            "draft_outputs": ["draft.srt", "draft.json"],
        }
        remote_api = getattr(config, "remote_api", None)
        api_key_env = getattr(remote_api, "api_key_env", "SUBTAP_API_KEY")
        report["llm"] = {
            "api_configured": bool(os.environ.get(api_key_env)),
            "api_key_env": api_key_env,
            "audio_sent": False,
        }

        if not json_output:
            typer.echo(
                f"  ASR：{config.asr.model} / {config.asr.quantization}，"
                f"对齐：{config.align.model} / {config.align.quantization}"
            )
            typer.echo("  模型策略：任务阶段加载，阶段结束释放，不默认常驻或预热")
            privacy_text = (
                "当前 ASR 会外发音频；--local-only 会阻止该配置"
                if external_audio_sent
                else "音频不外发；--local-only 可用"
            )
            typer.echo(f"  隐私：{privacy_text}")
            typer.echo("  输出：默认写入 ./output，精对齐生成 final.*")

        required_models = {config.asr.model, config.align.model}
        registry = ModelRegistry(config)
        for ms in registry.status():
            required = ms.name in required_models
            icon = (
                typer.style("✓", fg=typer.colors.GREEN)
                if ms.installed
                else typer.style("✗", fg=typer.colors.RED)
            )
            report["models"].append(
                {
                    "name": ms.name,
                    "required": required,
                    "installed": ms.installed,
                    "path": str(ms.path),
                    "missing_files": ms.missing_files,
                }
            )
            if not json_output:
                typer.echo(f"  {icon} {ms.name}")
            if required and not ms.installed:
                all_ok = False
                if not json_output:
                    typer.echo(f"    路径：{ms.path}")
                if ms.missing_files:
                    if not json_output:
                        typer.echo(f"    缺失：{', '.join(ms.missing_files)}")
    except Exception as e:
        report["models_error"] = str(e)
        if release:
            all_ok = False
        if not json_output:
            typer.echo(f"  ⚠ 无法检查模型状态：{e}")

    report["ok"] = all_ok
    if json_output:
        typer.echo(json.dumps(report, ensure_ascii=False, indent=2))
        if release and not all_ok:
            raise typer.Exit(1)
        return

    if all_ok:
        typer.echo(typer.style("\n✓ 所有检查通过！", fg=typer.colors.GREEN))
    else:
        typer.echo(
            typer.style("\n✗ 部分检查未通过，请根据提示修复", fg=typer.colors.RED)
        )
        if release:
            raise typer.Exit(1)
