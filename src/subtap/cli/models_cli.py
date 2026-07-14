"""模型管理子命令组."""

from __future__ import annotations

from pathlib import Path

import typer

from subtap.cli._utils import _handle_error

models_app = typer.Typer(help="模型管理", no_args_is_help=True)


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
            issues = ", ".join(ms.missing_files)
            status = typer.style(f"✗ 异常（{issues}）", fg=typer.colors.RED)
        typer.echo(f"  {ms.name:12s} {status}  {ms.path}")


@models_app.command("install")
def models_install(
    model_name: str = typer.Argument(
        ..., help="要安装的模型（asr_0.6b / asr_1.7b / aligner / all）"
    ),
    download_source: str = typer.Option(
        "hf", "--source", "-s", help="下载源：hf / hf-mirror / modelscope"
    ),
    model_endpoint: str | None = typer.Option(
        None, "--endpoint", "-e", help="自定义 Hugging Face 镜像地址"
    ),
) -> None:
    """安装模型文件到本地"""
    from subtap.schemas.config import load_config
    from subtap.core.models import ModelDownloader, MODEL_REGISTRY
    from rich.progress import (
        Progress,
        SpinnerColumn,
        BarColumn,
        TextColumn,
        DownloadColumn,
        TransferSpeedColumn,
    )

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    if model_endpoint:
        config.models.hf_mirror_endpoint = model_endpoint
    downloader = ModelDownloader(config)

    targets = list(MODEL_REGISTRY.keys()) if model_name == "all" else [model_name]

    for name in targets:
        typer.echo(f"▸ 安装 {name}（{download_source}）...")
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
            ) as progress:
                task_id = progress.add_task(name, total=None)

                def update_progress(filename: str, downloaded: int, total: int) -> None:
                    if downloaded == 0:
                        progress.reset(
                            task_id, total=total, description=f"{name}/{filename}"
                        )
                    progress.update(task_id, completed=downloaded)

                path = downloader.download(
                    name, source=download_source, progress=update_progress
                )
            typer.echo(f"  ✓ {path}")
        except ValueError as e:
            _handle_error(f"错误：{e}")
        except NotImplementedError as e:
            typer.echo(f"  {e}")
            typer.echo(
                typer.style(
                    f"  → 请将模型文件放入：{downloader.root / MODEL_REGISTRY[name]['subdir']}",
                    fg=typer.colors.YELLOW,
                )
            )


@models_app.command("verify")
def models_verify() -> None:
    """验证模型完整性"""
    from subtap.schemas.config import load_config
    from subtap.core.models import ModelVerifier

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    verifier = ModelVerifier(config)

    from subtap.core.models import MODEL_REGISTRY

    all_ok = True
    for name in MODEL_REGISTRY:
        result = verifier.verify(name)
        if result["status"] == "ok":
            typer.echo(typer.style(f"  ✓ {name}: 正常", fg=typer.colors.GREEN))
        else:
            typer.echo(
                typer.style(f"  ✗ {name}: {result['status']}", fg=typer.colors.RED)
            )
            all_ok = False

    if all_ok:
        typer.echo(typer.style("\n✓ 所有模型验证通过", fg=typer.colors.GREEN))
    else:
        typer.echo(typer.style("\n✗ 部分模型异常，请检查", fg=typer.colors.YELLOW))


@models_app.command("list")
def models_list() -> None:
    """列出可用模型"""
    from subtap.schemas.config import load_config
    from subtap.core.models import ModelRegistry

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    registry = ModelRegistry(config)

    typer.echo("═══ 可用模型 ═══")
    for name in registry.list_available():
        typer.echo(f"  • {name}")


@models_app.command("remove")
def models_remove(
    model_name: str = typer.Argument(..., help="要移除的模型名称"),
) -> None:
    """移除已安装的模型"""
    from subtap.schemas.config import load_config
    from subtap.core.models import ModelRemover

    config = load_config(Path.home() / ".subtap" / "config.yaml")
    remover = ModelRemover(config)

    try:
        result = remover.remove(model_name)
        if result:
            typer.echo(f"✓ 已移除 {model_name}")
        else:
            typer.echo(f"⚠ {model_name} 不存在")
    except ValueError as e:
        _handle_error(f"错误：{e}")
    except OSError as e:
        _handle_error(f"删除失败：{e}")
