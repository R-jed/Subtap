"""Setup 命令：用户初始化向导."""

from __future__ import annotations

import typer
from pathlib import Path


def setup(
    skip_models: bool = typer.Option(False, "--skip-models", help="跳过模型下载"),
    download_source: str = typer.Option(
        "ask",
        "--download-source",
        help="模型下载方式：ask / hf / hf-mirror / modelscope / manual",
    ),
    include_optional: bool = typer.Option(
        False, "--include-optional", help="同时下载可选大模型"
    ),
    asr_model: str | None = typer.Option(
        None,
        "--asr-model",
        help="首次安装的 ASR：asr_0.6b / asr_1.7b（默认沿用配置）",
    ),
    model_endpoint: str | None = typer.Option(
        None, "--model-endpoint", help="自定义 Hugging Face 镜像地址"
    ),
    remote_api: bool = typer.Option(False, "--remote-api", help="配置远程 API"),
    remote_provider: str = typer.Option(
        "openai-compatible",
        "--remote-provider",
        help="远程 API 格式：openai-compatible / anthropic",
    ),
    remote_base_url: str | None = typer.Option(
        None, "--remote-base-url", help="远程 API Base URL"
    ),
    remote_api_key_env: str = typer.Option(
        "SUBTAP_API_KEY",
        "--remote-api-key-env",
        help="保存到配置的 API Key 环境变量名",
    ),
) -> None:
    """用户初始化向导"""
    from subtap.core.setup import SetupWizard

    wizard = SetupWizard()

    if asr_model is not None and asr_model not in ("asr_0.6b", "asr_1.7b"):
        raise typer.BadParameter(
            "必须是 asr_0.6b 或 asr_1.7b", param_hint="--asr-model"
        )

    typer.echo("═══ Subtap 初始化向导 ═══\n")

    # Step 1: System check
    typer.echo("▸ Step 1: 系统检查")
    deps = wizard.check_system_deps()

    for name, ok in deps.items():
        icon = (
            typer.style("✓", fg=typer.colors.GREEN)
            if ok
            else typer.style("✗", fg=typer.colors.RED)
        )
        label = {
            "ffmpeg": "ffmpeg",
            "ffprobe": "ffprobe",
            "python": "Python 3.10+",
            "venv": "Python 虚拟环境",
            "mlx": "MLX / Metal",
            "models": "本地 models/",
            "output": "输出目录权限",
        }.get(name, name)
        typer.echo(f"  {icon} {label}")

    if not all(deps.values()):
        typer.echo(
            typer.style("\n✗ 系统检查未通过，请安装缺失依赖", fg=typer.colors.RED)
        )
        raise typer.Exit(1)

    # Step 2: Config init
    typer.echo("\n▸ Step 2: 初始化配置")
    if not wizard.check_config_exists():
        wizard.run_init()
        typer.echo("  ✓ ~/.subtap/ 已创建")
    else:
        typer.echo("  ✓ ~/.subtap/ 已存在")

    if asr_model is not None:
        from subtap.ui.config_manager import ConfigManager

        config_manager = ConfigManager(Path.home() / ".subtap" / "config.yaml")
        selected_config = config_manager.to_subtap_config()
        selected_config.asr.model = asr_model
        config_manager.sync_from_config(selected_config)

    # Step 3: Model setup
    if skip_models:
        typer.echo("\n▸ Step 3: 模型安装（已跳过）")
    else:
        typer.echo("\n▸ Step 3: 模型安装")
        ok = wizard.setup_models(
            source=download_source,
            include_optional=include_optional,
            endpoint=model_endpoint,
        )
        if ok:
            typer.echo("  ✓ 模型安装完成")
        elif (
            download_source == "manual"
            or getattr(wizard, "last_model_source", None) == "manual"
        ):
            # manual 模式下用户选择手动安装，正常结束
            typer.echo("  ⚠ 模型安装待手动完成")
        else:
            typer.echo("  ✗ 模型安装失败")
            raise typer.Exit(1)

    if remote_api:
        typer.echo("\n▸ Step 4: 远程 API 配置")
        if not wizard.configure_remote_api(
            provider=remote_provider,
            base_url=remote_base_url,
            api_key_env=remote_api_key_env,
        ):
            raise typer.Exit(1)

    typer.echo(typer.style("\n═══ 初始化完成 ═══", fg=typer.colors.GREEN))
    typer.echo("下一步：subtap run <音频文件>")
