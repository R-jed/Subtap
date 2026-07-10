"""批量处理命令：批量转录、字幕合成、批量字幕合成."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from io import StringIO
from contextlib import redirect_stdout
from pathlib import Path
import typer


from subtap.cli._utils import _handle_error


def batch_transcribe(
    args: list[str] = typer.Argument(None, help="输入文件路径（支持拖入）"),
    directory: str = typer.Option(None, "--dir", "-d", help="扫描目录中的媒体文件"),
    configure: bool = typer.Option(False, "--configure", help="运行配置向导"),
    no_confirm: bool = typer.Option(False, "--no-confirm", "-y", help="跳过确认"),
    files: str = typer.Option(None, "--files", "-f", help="输入文件，逗号分隔"),
    output_dir: Path = typer.Option(
        Path("./output"), "--output-dir", "-o", help="输出目录"
    ),
    mode: str | None = typer.Option(None, "--mode", "-m", help="fast / quality"),
    enhance: str | None = typer.Option(
        None, "--enhance", "-e", help="字幕增强模式：off / local / api"
    ),
    translate_to: str | None = typer.Option(
        None, "--translate-to", help="翻译目标语言：en / ja / zh"
    ),
    bilingual: str | None = typer.Option(
        None,
        "--bilingual",
        help="双语字幕顺序：off / source-first / target-first",
    ),
    max_chars: int | None = typer.Option(
        None, "--max-chars", help="每行字幕最大字符数（10-60）", min=10, max=60
    ),
    min_chars: int | None = typer.Option(
        None, "--min-chars", help="每行字幕最小字符数（4-30）", min=4, max=30
    ),
    punctuation: bool | None = typer.Option(
        None, "--punctuation", help="字幕带标点符号（默认不带）"
    ),
    subtitle_language: str | None = typer.Option(
        None, "--subtitle-language", help="字幕输出语种（zh/en/ja）"
    ),
    concurrency: int = typer.Option(
        1,
        "--concurrency",
        "-c",
        help="并发处理数（最大 4）（尚未实现）",
        min=1,
        max=4,
        hidden=True,
    ),
    resume: Path | None = typer.Option(
        None, "--resume", help="恢复中断的任务（传入 manifest.json 路径）"
    ),
    retry_failed: Path | None = typer.Option(
        None, "--retry-failed", help="重试失败的文件（传入 manifest.json 路径）"
    ),
    json_output: bool = typer.Option(False, "--json", help="输出机器可读 JSON"),
    hotwords: str | None = typer.Option(
        None,
        "--hotwords",
        help="ASR 热词列表，逗号分隔（如：瑞幸,CapCut,TikTok）",
    ),
) -> None:
    """批量转录多个媒体文件。

    支持将文件拖入终端或手动输入路径。首次运行会显示配置向导。

    [bold]示例：[/bold]
      subtap batch-transcribe a.mp4 b.mp4 c.mp4
      subtap batch-transcribe --files a.mp4,b.mp4,c.mp4
      subtap batch-transcribe --dir /path/to/media
      subtap batch-transcribe --configure
      subtap batch-transcribe --files a.mp4,b.mp4 --mode quality --translate-to en
      subtap batch-transcribe --resume output/manifest.json
      subtap batch-transcribe --retry-failed output/manifest.json
      subtap batch-transcribe --files a.mp4,b.mp4 --json
    """
    from subtap.batch import (
        PIPELINE_STAGES,
        build_manifest,
        get_failed_items,
        get_pending_items,
        load_manifest,
        make_item,
        parse_files,
        write_manifest,
    )
    from subtap.batch_abort import AbortController
    from subtap.batch_progress import (
        JsonProgressWriter,
        print_progress_footer,
        print_progress_header,
        print_progress_item,
    )
    from subtap.core.pipeline import Pipeline
    from subtap.schemas.config import load_config
    from subtap.ui.tui import RichRunner

    # ── 参数冲突检查 ──────────────────────────────────────────
    if resume and retry_failed:
        _handle_error("错误：--resume 和 --retry-failed 不能同时使用")

    if (resume or retry_failed) and (files or args or directory):
        _handle_error("错误：--resume/--retry-failed 不能与输入文件同时使用")

    # ── 配置向导 ──────────────────────────────────────────────
    from subtap.batch_config import load_batch_config
    from subtap.batch_interactive import (
        collect_files,
        confirm_files,
        run_config_wizard,
        validate_files,
    )

    config_path = Path.home() / ".subtap" / "batch-config.yaml"

    if configure or (not config_path.exists() and not json_output):
        batch_config = run_config_wizard(config_path)
    else:
        batch_config = load_batch_config(config_path)

    # 使用配置文件的值作为默认值（CLI 参数优先）
    if mode is None:
        mode = batch_config.mode
    if enhance is None:
        enhance = batch_config.enhance
    if translate_to is None:
        translate_to = batch_config.translate_to
    if bilingual is None:
        bilingual = batch_config.bilingual
    if max_chars is None:
        max_chars = batch_config.max_chars
    if min_chars is None:
        min_chars = batch_config.min_chars
    if punctuation is None:
        punctuation = batch_config.punctuation
    if subtitle_language is None:
        subtitle_language = batch_config.subtitle_language
    if bilingual != "off" and not translate_to:
        _handle_error("错误：--bilingual 需要同时使用 --translate-to")

    # ── 收集文件（支持多种方式）─────────────────────────────────
    if not resume and not retry_failed:
        collected = collect_files(args, directory)

        # 兼容旧的 --files 参数
        if files:
            collected.extend(parse_files(files))

        if not collected:
            _handle_error("未找到媒体文件")

        # 验证文件（仅用于确认提示，不预过滤——让处理循环记录失败）
        valid, invalid = validate_files(collected)
        if invalid and not json_output:
            for f in invalid:
                typer.echo(f"⚠ 文件不存在：{f}", err=True)

        # 确认（--json 或 --no-confirm 时跳过）
        if not no_confirm and not json_output:
            if not confirm_files(collected):
                typer.echo("已取消")
                return

    # ── 加载配置 ──────────────────────────────────────────────
    config = load_config(Path.home() / ".subtap" / "config.yaml")

    # CLI overrides config only when explicitly provided
    config.output.timestamp = True  # batch 模式始终带时间戳
    if punctuation is not None:
        config.output.subtitle_punctuation = punctuation
    if subtitle_language is not None:
        config.output.subtitle_language = subtitle_language
    if max_chars is not None:
        config.output.max_chars = max_chars
    if min_chars is not None:
        config.output.min_chars = min_chars
    config.output.subtitle_stem = "batch"

    if mode == "quality":
        config.asr.model = "asr_1.7b"

    # Hotwords: CLI overrides config
    if hotwords:
        config.asr.hotwords = [w.strip() for w in hotwords.split(",") if w.strip()]

    # ── 恢复或重试模式 ──────────────────────────────────────
    if resume or retry_failed:
        manifest_path = resume or retry_failed
        assert manifest_path is not None
        if not manifest_path.exists():
            _handle_error(f"manifest 文件不存在：{manifest_path}")

        manifest = load_manifest(manifest_path)
        output_dir = Path(manifest["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)

        if resume:
            items_to_process = get_pending_items(manifest["items"])
            typer.echo(f"▸ 恢复模式：跳过 {manifest['succeeded']} 个成功文件")
        else:
            items_to_process = get_failed_items(manifest["items"])
            typer.echo(f"▸ 重试模式：重试 {len(items_to_process)} 个失败文件")

        if not items_to_process:
            typer.echo("✓ 没有需要处理的文件")
            return

        # 重置待处理项状态并清理 work/ 目录
        import shutil

        for item in items_to_process:
            item["status"] = "pending"
            item["error"] = ""
            for stage in item.get("stages", {}).values():
                if isinstance(stage, dict):
                    stage["status"] = "pending"
            # I4 fix: 清理失败/中断文件的 work/ 目录，防止读到脏数据
            work_dir = Path(item["output_dir"]) / "work"
            if work_dir.exists():
                shutil.rmtree(work_dir)

        items = manifest["items"]
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        items = [make_item(p, output_dir) for p in collected]

    # ── 构建参数快照 ──────────────────────────────────────────
    params = {
        "mode": mode,
        "enhance": enhance,
        "translate_to": translate_to,
        "bilingual": bilingual,
        "max_chars": max_chars,
        "min_chars": min_chars,
        "punctuation": punctuation,
        "subtitle_language": subtitle_language,
        "concurrency": concurrency,
    }

    # ── 初始化中止控制器 ──────────────────────────────────────
    abort_controller = AbortController(output_dir)
    # 清理旧的 abort 标记
    abort_controller.cleanup()
    abort_controller.install_signal_handler()

    # ── 初始化进度显示 ──────────────────────────────────────
    # I2 fix: 记录任务真正开始时间，后续调用复用
    task_created_at = datetime.now(timezone.utc).isoformat()

    json_writer = JsonProgressWriter() if json_output else None
    total = len(items)
    manifest_path = output_dir / "manifest.json"

    if json_writer:
        json_writer.write_start(total, mode, created_at=task_created_at)
    else:
        print_progress_header(total, mode)

    # ── 写入初始 manifest ──────────────────────────────────────
    write_manifest(
        manifest_path,
        build_manifest(output_dir, mode, items, params, created_at=task_created_at),
    )

    # ── 处理文件 ──────────────────────────────────────────────
    start_time = time.time()

    for index, item in enumerate(items, start=1):
        # 检查中止
        if abort_controller.is_aborted():
            if item["status"] in ("pending", "running"):
                item["status"] = "interrupted"
                item["error"] = "用户中止"
            continue

        # 跳过已成功的文件
        if item["status"] == "succeeded":
            continue

        path = Path(item["input_path"])
        item_output_dir = Path(item["output_dir"])
        filename = path.name

        # 文件不存在
        if not path.exists():
            item["status"] = "failed"
            item["error"] = "文件不存在"
            if json_writer:
                json_writer.write_item_complete(
                    index, filename, "failed", error="文件不存在"
                )
            else:
                print_progress_item(index, total, filename, "failed")
            write_manifest(
                manifest_path,
                build_manifest(
                    output_dir, mode, items, params, created_at=task_created_at
                ),
            )
            continue

        # 开始处理
        item["status"] = "running"
        item["stages"] = {s: {"status": "pending"} for s in PIPELINE_STAGES}

        if json_writer:
            json_writer.write_item_start(index, filename)
        else:
            print_progress_item(index, total, filename, "running")

        write_manifest(
            manifest_path,
            build_manifest(output_dir, mode, items, params, created_at=task_created_at),
        )

        # C1 fix: stage_start 移到 try 之前，防止 UnboundLocalError
        stage_start = time.time()

        try:
            # 配置 Pipeline
            item_config = load_config(Path.home() / ".subtap" / "config.yaml")

            # CLI overrides config only when explicitly provided
            item_config.output.timestamp = True  # batch 模式始终带时间戳
            if punctuation is not None:
                item_config.output.subtitle_punctuation = punctuation
            if subtitle_language is not None:
                item_config.output.subtitle_language = subtitle_language
            if max_chars is not None:
                item_config.output.max_chars = max_chars
            if min_chars is not None:
                item_config.output.min_chars = min_chars
            item_config.output.subtitle_stem = path.stem

            if mode == "quality":
                item_config.asr.model = "asr_1.7b"

            pipeline = Pipeline(item_config, work_dir=item_output_dir / "work")
            pipeline.workspace.ensure_dirs()

            # 运行 Pipeline
            runner = RichRunner()

            if json_output:
                with redirect_stdout(StringIO()):
                    meta = runner.run_pipeline(
                        pipeline,
                        path,
                        item_output_dir,
                        fmt="srt",
                        translate_to=translate_to,
                        bilingual=bilingual or "off",
                        enhance=enhance,
                    )
            else:
                meta = runner.run_pipeline(
                    pipeline,
                    path,
                    item_output_dir,
                    fmt="srt",
                    translate_to=translate_to,
                    bilingual=bilingual or "off",
                    enhance=enhance,
                )

            # 记录成功
            item["status"] = "succeeded"
            item["duration"] = time.time() - stage_start
            item["meta"] = meta

            # 更新阶段状态
            timings = meta.get("timings", {})
            for stage_name in item.get("stages", {}):
                if stage_name in timings:
                    item["stages"][stage_name] = {
                        "status": "done",
                        "duration": round(timings[stage_name], 2),
                    }
            if json_writer:
                json_writer.write_item_complete(
                    index, filename, "succeeded", item["duration"]
                )
            else:
                print_progress_item(
                    index, total, filename, "succeeded", duration=item["duration"]
                )

            # 成功处理后清理 L2 中间文件
            from subtap.engine.cleanroom import Cleanroom

            cleanroom = Cleanroom(item_output_dir / "work")
            cleanroom.clean_intermediate_files()

        except Exception as e:
            item["status"] = "failed"
            item["error"] = str(e)
            item["duration"] = time.time() - stage_start

            # 标记失败的阶段
            for stage_name, stage_info in item.get("stages", {}).items():
                if (
                    isinstance(stage_info, dict)
                    and stage_info.get("status") == "running"
                ):
                    stage_info["status"] = "failed"
                    stage_info["error"] = str(e)

            if json_writer:
                json_writer.write_item_complete(index, filename, "failed", error=str(e))
            else:
                print_progress_item(index, total, filename, "failed")

        write_manifest(
            manifest_path,
            build_manifest(output_dir, mode, items, params, created_at=task_created_at),
        )

    # ── 完成 ──────────────────────────────────────────────────
    total_duration = time.time() - start_time
    abort_controller.restore_signal_handler()
    abort_controller.cleanup()

    # 更新完成时间
    manifest = build_manifest(
        output_dir, mode, items, params, created_at=task_created_at
    )
    manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
    manifest["duration"] = total_duration
    write_manifest(manifest_path, manifest)

    if json_writer:
        json_writer.write_complete(
            manifest["ok"],
            manifest["total"],
            manifest["succeeded"],
            manifest["failed"],
            manifest["interrupted"],
            total_duration,
        )
    else:
        print_progress_footer(
            manifest["total"],
            manifest["succeeded"],
            manifest["failed"],
            manifest["interrupted"],
            total_duration,
        )
        typer.echo(f"\n▸ 批量任务清单：{manifest_path}")


def compose_subtitle(
    video: Path = typer.Argument(..., help="输入视频文件"),
    subtitle: Path = typer.Option(..., "--subtitle", "-s", help="字幕文件 SRT/ASS"),
    output: Path = typer.Option(..., "--output", "-o", help="输出视频路径"),
    overwrite: bool = typer.Option(False, "--overwrite", help="覆盖已存在输出文件"),
) -> None:
    """把字幕烧录进单个视频。"""
    from subtap.compose import compose_one

    result = compose_one(video, subtitle, output, overwrite=overwrite)
    if result["status"] != "succeeded":
        _handle_error(f"合成失败：{result['error']}")
    typer.echo(f"✓ 合成完成：{output}")


def batch_compose_subtitle(
    items: Path = typer.Option(..., "--items", help="JSON 文件：[{video, subtitle}]"),
    output_dir: Path = typer.Option(
        Path("./output/composed"), "--output-dir", "-o", help="输出目录"
    ),
    overwrite: bool = typer.Option(False, "--overwrite", help="覆盖已存在输出文件"),
    json_output: bool = typer.Option(False, "--json", help="输出机器可读 JSON"),
) -> None:
    """批量把字幕烧录进视频。"""
    from subtap.compose import compose_batch

    if not items.exists():
        _handle_error(f"批量合成清单不存在：{items}")
    payload = json.loads(items.read_text(encoding="utf-8"))
    manifest = compose_batch(payload, output_dir, overwrite=overwrite)
    if json_output:
        typer.echo(json.dumps(manifest, ensure_ascii=False, indent=2))
        return
    typer.echo(f"▸ 批量合成清单：{output_dir / 'compose-manifest.json'}")
    for item in manifest["items"]:
        icon = "✓" if item["status"] == "succeeded" else "✗"
        typer.echo(f"  {icon} {item['video']} — {item['status']}")
