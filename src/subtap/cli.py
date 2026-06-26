"""Subtap CLI — 中文优先字幕生成引擎入口."""

from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path

import typer

from subtap import __version__

app = typer.Typer(
    name="subtap",
    help="Subtap — 本地优先的 AI 字幕生成引擎",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# ── 基础命令 ──────────────────────────────────────────────

@app.command()
def version() -> None:
    """显示版本信息"""
    typer.echo(f"subtap v{__version__}")
    typer.echo(f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    typer.echo(f"系统 {platform.system()} {platform.machine()}")


@app.command()
def init() -> None:
    """初始化工作空间（~/.subtap/）"""
    home = Path.home()
    subtap_dir = home / ".subtap"
    config_path = subtap_dir / "config.yaml"
    glossary_dir = subtap_dir / "glossary"
    db_path = subtap_dir / "subtap.db"

    subtap_dir.mkdir(parents=True, exist_ok=True)
    glossary_dir.mkdir(parents=True, exist_ok=True)

    if not config_path.exists():
        default_config = Path(__file__).resolve().parents[2] / "configs" / "default.yaml"
        if default_config.exists():
            shutil.copy2(default_config, config_path)
        else:
            config_path.write_text("# Subtap 配置\n")

    if not db_path.exists():
        db_path.touch()

    glossary_global = glossary_dir / "global.yaml"
    if not glossary_global.exists():
        glossary_global.write_text("# 全局术语表\nentries: []\n")

    typer.echo(f"✓ 工作空间已初始化：{subtap_dir}")
    typer.echo(f"  配置文件：{config_path}")
    typer.echo(f"  术语表：  {glossary_dir}")
    typer.echo(f"  数据库：  {db_path}")


# ── Doctor 命令 ────────────────────────────────────────────

@app.command()
def doctor(
    release: bool = typer.Option(False, "--release", help="执行发布前完整检查"),
) -> None:
    """检查系统依赖和运行环境"""
    checks: list[tuple[str, str, bool, str]] = []

    # 基础依赖
    ffmpeg_ok = shutil.which("ffmpeg") is not None
    checks.append(("ffmpeg", "音视频处理", ffmpeg_ok, "" if ffmpeg_ok else "未找到，请安装：brew install ffmpeg"))

    ffprobe_ok = shutil.which("ffprobe") is not None
    checks.append(("ffprobe", "媒体探测", ffprobe_ok, "" if ffprobe_ok else "未找到，请安装：brew install ffmpeg"))

    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 10)
    checks.append(("python", "Python 版本", py_ok, f"v{py_ver}" if py_ok else f"v{py_ver}（需要 >= 3.10）"))

    # 工作空间
    subtap_dir = Path.home() / ".subtap"
    ws_ok = subtap_dir.exists() and os.access(str(subtap_dir), os.W_OK) if subtap_dir.exists() else False
    checks.append(("workspace", "工作空间", ws_ok, "" if ws_ok else f"不可写或不存在：{subtap_dir}"))

    config_path = subtap_dir / "config.yaml"
    cfg_ok = config_path.exists()
    if cfg_ok:
        try:
            from subtap.schemas.config import load_config
            load_config(config_path)
        except Exception as e:
            cfg_ok = False
    checks.append(("config", "配置文件", cfg_ok, "" if cfg_ok else f"缺失或损坏：{config_path}"))

    # --release 模式：增加模型和 TUI 检查
    if release:
        # MLX 运行时
        try:
            import mlx
            mlx_ok = True
        except ImportError:
            mlx_ok = False
        checks.append(("mlx", "MLX 运行时", mlx_ok, "" if mlx_ok else "未安装，请：pip install mlx"))

        # mlx-audio
        try:
            import mlx_audio
            mla_ok = True
        except ImportError:
            mla_ok = False
        checks.append(("mlx-audio", "MLX Audio", mla_ok, "" if mla_ok else "未安装，请：pip install mlx-audio"))

        # rich
        try:
            import rich
            rich_ok = True
        except ImportError:
            rich_ok = False
        checks.append(("rich", "Rich TUI", rich_ok, "" if rich_ok else "未安装，请：pip install rich"))

        # 模型文件
        project_root = Path(__file__).resolve().parents[2]
        for name, label in [("asr_0.6b", "ASR 0.6B"), ("aligner", "对齐模型")]:
            model_dir = project_root / "models" / name
            model_ok = model_dir.exists() and any(model_dir.iterdir())
            checks.append((name, label, model_ok, "" if model_ok else f"缺失：{model_dir}"))

    # 打印结果
    all_ok = True
    for _name, label, ok, detail in checks:
        icon = typer.style("✓", fg=typer.colors.GREEN) if ok else typer.style("✗", fg=typer.colors.RED)
        msg = f"  {icon} {label}"
        if detail:
            msg += f" — {detail}"
        typer.echo(msg)
        if not ok:
            all_ok = False

    if all_ok:
        typer.echo(typer.style("\n✓ 所有检查通过！", fg=typer.colors.GREEN))
    else:
        typer.echo(typer.style("\n✗ 部分检查未通过，请根据提示修复", fg=typer.colors.RED))
        raise typer.Exit(1)


# ── Run 命令 ───────────────────────────────────────────────

@app.command()
def run(
    input_path: Path = typer.Argument(..., help="输入媒体文件路径（支持 mp3/mp4/wav/mkv 等）"),
    work_dir: Path = typer.Option(Path("./work"), "-w", "--work-dir", help="工作目录"),
    output_dir: Path = typer.Option(Path("./output"), "-o", "--output-dir", help="输出目录"),
    fmt: str = typer.Option("srt", "--format", "-f", help="导出格式：srt / ass / txt"),
    skip_clean: bool = typer.Option(False, "--skip-clean", help="跳过文本清洗阶段"),
    skip_align: bool = typer.Option(False, "--skip-align", help="跳过时间轴对齐阶段"),
    use_tui: bool = typer.Option(True, "--tui/--no-tui", help="启用 TUI 界面（默认开启）"),
) -> None:
    """运行完整字幕生成流程

    [bold]流程：[/bold] 音频标准化 → 切段 → 语音识别 → 文本清洗 → 智能断句 → 时间轴对齐 → 字幕导出

    [bold]示例：[/bold]
      subtap run video.mp3
      subtap run audio.mp3 -o ./subtitles --format ass
      subtap run input.mp3 --no-tui --skip-clean
    """
    from subtap.schemas.config import load_config
    from subtap.core.pipeline import Pipeline

    if not input_path.exists():
        typer.echo(f"✗ 错误：文件未找到 {input_path}", err=True)
        raise typer.Exit(1)

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    pipeline = Pipeline(config, work_dir=work_dir)
    pipeline.workspace.ensure_dirs()

    if use_tui:
        from subtap.ui.tui import TUIRunner
        runner = TUIRunner(use_tui=True)
    else:
        from subtap.ui.tui import PlainRunner
        runner = PlainRunner()

    try:
        runner.run_pipeline(
            pipeline, input_path, output_dir, fmt=fmt,
            skip_clean=skip_clean, skip_align=skip_align,
        )
    except SystemExit:
        raise
    except Exception as e:
        typer.echo(f"\n✗ 处理失败：{e}", err=True)
        raise typer.Exit(1)


# ── 单阶段命令 ─────────────────────────────────────────────

@app.command()
def prepare(
    input_path: Path = typer.Argument(..., help="输入媒体文件路径"),
    output: Path = typer.Option(Path("./work"), "-o", "--output", help="工作目录"),
) -> None:
    """提取音频并切段（单阶段执行）"""
    from subtap.schemas.config import load_config
    from subtap.core.pipeline import Pipeline

    if not input_path.exists():
        typer.echo(f"✗ 文件未找到：{input_path}", err=True)
        raise typer.Exit(1)

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    pipeline = Pipeline(config, work_dir=output)

    typer.echo("▸ 音频标准化...")
    result = pipeline.run_stage("prepare", input_path=input_path)
    typer.echo(f"  ✓ {result['media_info']['duration']:.1f}s, {result['media_info']['sample_rate']}Hz")

    typer.echo("▸ 音频切段...")
    result = pipeline.run_stage("chunk")
    typer.echo(f"  ✓ {result['chunk_count']} 段 → {result['chunks_jsonl']}")

    typer.echo(typer.style("\n✓ 完成", fg=typer.colors.GREEN))


@app.command()
def transcribe(
    audio_path: Path = typer.Argument(..., help="音频文件路径"),
    work_dir: Path = typer.Option(Path("./work"), "-w", "--work-dir", help="工作目录"),
    backend: str | None = typer.Option(None, "-b", "--backend", help="ASR 后端覆盖"),
) -> None:
    """语音识别（单阶段执行）"""
    from subtap.schemas.config import load_config
    from subtap.core.pipeline import Pipeline

    if not audio_path.exists():
        typer.echo(f"✗ 文件未找到：{audio_path}", err=True)
        raise typer.Exit(1)

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    pipeline = Pipeline(config, work_dir=work_dir)
    pipeline.workspace.ensure_dirs()

    typer.echo(f"▸ 语音识别（{backend or config.asr.backend}）...")
    try:
        result = pipeline.run_stage("asr", backend_name=backend)
    except (ImportError, NotImplementedError) as e:
        typer.echo(f"✗ 错误：{e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"  ✓ {result['segment_count']} 条 → {result['asr_jsonl']}")
    typer.echo(typer.style("\n✓ 完成", fg=typer.colors.GREEN))


@app.command()
def clean(
    asr_path: Path = typer.Argument(..., help="asr.jsonl 路径"),
    work_dir: Path = typer.Option(Path("./work"), "-w", "--work-dir", help="工作目录"),
    llm: str | None = typer.Option(None, "--llm", help="LLM 后端（如 ollama:qwen3-coder）"),
    glossary: Path | None = typer.Option(None, "--glossary", help="术语表 YAML 路径"),
    output: Path | None = typer.Option(None, "-o", "--output", help="输出 cleaned.jsonl 路径"),
) -> None:
    """文本清洗：术语替换 + LLM 纠错（单阶段执行）"""
    from subtap.schemas.config import load_config
    from subtap.core.pipeline import Pipeline

    if not asr_path.exists():
        typer.echo(f"✗ 文件未找到：{asr_path}", err=True)
        raise typer.Exit(1)

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    pipeline = Pipeline(config, work_dir=work_dir)
    pipeline.workspace.ensure_dirs()

    if output:
        pipeline.workspace.cleaned_jsonl = output

    typer.echo(f"▸ 文本清洗（{llm or config.clean.backend}）...")
    try:
        result = pipeline.run_stage("clean", llm_backend=llm, glossary_path=str(glossary) if glossary else None)
    except ValueError as e:
        typer.echo(f"✗ 错误：{e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"  ✓ {result['segment_count']} 条 → {result['cleaned_jsonl']}")
    typer.echo(typer.style("\n✓ 完成", fg=typer.colors.GREEN))


@app.command()
def segment(
    cleaned_path: Path = typer.Argument(..., help="cleaned.jsonl 路径"),
    work_dir: Path = typer.Option(Path("./work"), "-w", "--work-dir", help="工作目录"),
    output: Path | None = typer.Option(None, "-o", "--output", help="输出 sentences.jsonl 路径"),
) -> None:
    """智能断句（单阶段执行）"""
    from subtap.schemas.config import load_config
    from subtap.core.pipeline import Pipeline

    if not cleaned_path.exists():
        typer.echo(f"✗ 文件未找到：{cleaned_path}", err=True)
        raise typer.Exit(1)

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    pipeline = Pipeline(config, work_dir=work_dir)
    pipeline.workspace.ensure_dirs()

    if output:
        pipeline.workspace.sentences_jsonl = output

    typer.echo("▸ 智能断句...")
    try:
        result = pipeline.run_stage("segment")
    except ValueError as e:
        typer.echo(f"✗ 错误：{e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"  ✓ {result['sentence_count']} 句 → {result['sentences_jsonl']}")
    typer.echo(typer.style("\n✓ 完成", fg=typer.colors.GREEN))


@app.command()
def align(
    sentences_path: Path = typer.Argument(..., help="sentences.jsonl 路径"),
    work_dir: Path = typer.Option(Path("./work"), "-w", "--work-dir", help="工作目录"),
    backend: str | None = typer.Option(None, "-b", "--backend", help="对齐后端覆盖"),
    output: Path | None = typer.Option(None, "-o", "--output", help="输出 aligned.jsonl 路径"),
) -> None:
    """时间轴对齐（单阶段执行）"""
    from subtap.schemas.config import load_config
    from subtap.core.pipeline import Pipeline

    if not sentences_path.exists():
        typer.echo(f"✗ 文件未找到：{sentences_path}", err=True)
        raise typer.Exit(1)

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    pipeline = Pipeline(config, work_dir=work_dir)
    pipeline.workspace.ensure_dirs()

    if output:
        pipeline.workspace.aligned_jsonl = output

    typer.echo(f"▸ 时间轴对齐（{backend or config.align.backend}）...")
    try:
        result = pipeline.run_stage("align", backend_name=backend)
    except (ImportError, ValueError) as e:
        typer.echo(f"✗ 错误：{e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"  ✓ {result['aligned_count']} 条 → {result['aligned_jsonl']}")
    typer.echo(typer.style("\n✓ 完成", fg=typer.colors.GREEN))


@app.command()
def export(
    aligned_path: Path = typer.Argument(..., help="aligned.jsonl 路径"),
    output_dir: Path = typer.Option(Path("./output"), "-o", "--output-dir", help="输出目录"),
    fmt: str = typer.Option("srt", "--format", "-f", help="导出格式：srt / ass / txt"),
    stem: str = typer.Option("output", "--stem", help="输出文件名前缀"),
) -> None:
    """导出字幕文件（单阶段执行）"""
    from subtap.core.export import run_export

    if not aligned_path.exists():
        typer.echo(f"✗ 文件未找到：{aligned_path}", err=True)
        raise typer.Exit(1)

    typer.echo(f"▸ 字幕导出（{fmt.upper()}）...")
    try:
        result = run_export(aligned_path, output_dir, fmt=fmt, stem=stem)
    except ValueError as e:
        typer.echo(f"✗ 错误：{e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"  ✓ {result['output_path']}（{result['segment_count']} 条）")
    typer.echo(typer.style("\n✓ 完成", fg=typer.colors.GREEN))


# ── Demo 命令 ──────────────────────────────────────────────

@app.command()
def demo() -> None:
    """运行演示：使用内置测试音频展示完整流程

    自动查找 ~/Downloads/ASR-SRT测试音频/ 下的音频文件，
    执行完整 pipeline 并输出示例 SRT。
    """
    from subtap.schemas.config import load_config
    from subtap.core.pipeline import Pipeline

    # 查找测试音频
    demo_dir = Path.home() / "Downloads" / "ASR-SRT测试音频"
    test_files = [
        demo_dir / "高质量中文语音.mp3",
        demo_dir / "数字测试.mp3",
    ]
    input_file = None
    for f in test_files:
        if f.exists():
            input_file = f
            break

    if input_file is None:
        typer.echo("✗ 未找到测试音频文件", err=True)
        typer.echo(f"  请确认目录存在：{demo_dir}", err=True)
        raise typer.Exit(1)

    typer.echo("═══ Subtap 演示 ═══")
    typer.echo(f"  输入：{input_file.name}")
    typer.echo()

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    pipeline = Pipeline(config, work_dir=Path("./demo_work"))
    pipeline.workspace.ensure_dirs()

    from subtap.ui.tui import TUIRunner
    runner = TUIRunner(use_tui=True)

    try:
        runner.run_pipeline(
            pipeline, input_file, Path("./demo_output"), fmt="srt",
            skip_clean=True, skip_align=True,
        )
    except SystemExit:
        raise
    except Exception as e:
        typer.echo(f"\n✗ 演示失败：{e}", err=True)
        raise typer.Exit(1)

    # 显示示例 SRT 内容
    srt_path = Path("./demo_output/output.srt")
    if srt_path.exists():
        typer.echo()
        typer.echo("═══ 示例 SRT（前 20 行）═══")
        lines = srt_path.read_text(encoding="utf-8").splitlines()
        for line in lines[:20]:
            typer.echo(f"  {line}")
        if len(lines) > 20:
            typer.echo(f"  ...（共 {len(lines)} 行）")


# ── Models 子命令组 ────────────────────────────────────────

models_app = typer.Typer(help="模型管理", no_args_is_help=True)
app.add_typer(models_app, name="models")


@models_app.command("status")
def models_status() -> None:
    """查看所有模型状态"""
    from subtap.schemas.config import load_config
    from subtap.core.models import ModelRegistry

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    registry = ModelRegistry(config)

    for ms in registry.status():
        if ms.installed:
            status = typer.style("✓ 已安装", fg=typer.colors.GREEN)
        else:
            missing = ", ".join(ms.missing_files)
            status = typer.style(f"✗ 缺失（{missing}）", fg=typer.colors.RED)
        typer.echo(f"  {ms.name:12s} {status}  {ms.path}")


@models_app.command("install")
def models_install(
    model_name: str = typer.Argument(..., help="要安装的模型（asr / aligner / all）"),
) -> None:
    """安装模型文件到本地"""
    from subtap.schemas.config import load_config
    from subtap.core.models import ModelDownloader, MODEL_REGISTRY

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    downloader = ModelDownloader(config)

    targets = list(MODEL_REGISTRY.keys()) if model_name == "all" else [model_name]

    for name in targets:
        typer.echo(f"▸ 安装 {name}...")
        try:
            path = downloader.download(name)
            typer.echo(f"  → {path}")
        except ValueError as e:
            typer.echo(f"  ✗ 错误：{e}", err=True)
            raise typer.Exit(1)
        except NotImplementedError as e:
            typer.echo(f"  {e}")
            typer.echo(typer.style(f"  → 请将模型文件放入：{downloader.root / MODEL_REGISTRY[name]['subdir']}", fg=typer.colors.YELLOW))


@models_app.command("verify")
def models_verify() -> None:
    """验证模型完整性"""
    from subtap.schemas.config import load_config
    from subtap.core.models import ModelVerifier

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    verifier = ModelVerifier(config)

    all_ok = True
    for name in ["asr", "aligner"]:
        result = verifier.verify(name)
        if result["status"] == "ok":
            typer.echo(typer.style(f"  ✓ {name}: 正常", fg=typer.colors.GREEN))
        else:
            typer.echo(typer.style(f"  ✗ {name}: {result['status']}", fg=typer.colors.RED))
            all_ok = False

    if all_ok:
        typer.echo(typer.style("\n✓ 所有模型验证通过", fg=typer.colors.GREEN))
    else:
        typer.echo(typer.style("\n✗ 部分模型异常，请检查", fg=typer.colors.YELLOW))
