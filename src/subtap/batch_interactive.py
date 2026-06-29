"""Batch interactive config wizard."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import typer

from subtap.batch_config import BatchConfig, load_batch_config, save_batch_config

MEDIA_EXTENSIONS = {".mp3", ".mp4", ".wav", ".mkv", ".avi", ".mov", ".flac", ".m4a", ".aac"}


def scan_directory(directory: Path) -> list[Path]:
    """Scan directory for media files."""
    files = []
    for f in sorted(directory.iterdir()):
        if f.is_file() and f.suffix.lower() in MEDIA_EXTENSIONS:
            files.append(f)
    return files


def validate_files(files: list[Path]) -> tuple[list[Path], list[Path]]:
    """Validate files exist."""
    valid = []
    invalid = []
    for f in files:
        if f.exists():
            valid.append(f)
        else:
            invalid.append(f)
    return valid, invalid


def confirm_files(files: list[Path]) -> bool:
    """Show file list and ask for confirmation."""
    typer.echo(f"\n▸ 扫描到 {len(files)} 个文件：")
    for i, f in enumerate(files, 1):
        typer.echo(f"  {i}. {f.name}")

    choice = input("\n▸ 确认开始处理？[Y/n]: ").strip().lower()
    return choice in ("", "y", "yes", "是")


def collect_files(
    args: list[str] | None = None,
    directory: str | None = None,
) -> list[Path]:
    """Collect files from arguments or directory."""
    files = []

    # From arguments (drag-and-drop or manual paths)
    if args:
        for arg in args:
            p = Path(arg)
            if p.is_file():
                files.append(p)
            elif p.is_dir():
                files.extend(scan_directory(p))

    # From directory option
    if directory:
        dir_path = Path(directory)
        if dir_path.is_dir():
            files.extend(scan_directory(dir_path))

    # Deduplicate
    seen = set()
    unique = []
    for f in files:
        resolved = f.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(f)

    return unique


def prompt_choice(
    label: str,
    options: list[str],
    default: str | None = None,
) -> str:
    """Prompt user to select from a list of options."""
    while True:
        typer.echo(f"\n▸ {label}")
        for i, opt in enumerate(options, 1):
            marker = " (默认)" if opt == default else ""
            typer.echo(f"  [{i}] {opt}{marker}")

        choice = input("  请选择: ").strip()

        if not choice and default:
            return default

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                return options[idx]
        except ValueError:
            pass

        typer.echo("  ⚠ 无效选择，请重试")


def prompt_int(
    label: str,
    default: int,
    min_val: int,
    max_val: int,
) -> int:
    """Prompt user for an integer value."""
    while True:
        value = input(f"\n▸ {label} [{default}]: ").strip()

        if not value:
            return default

        try:
            num = int(value)
            if min_val <= num <= max_val:
                return num
            typer.echo(f"  ⚠ 值必须在 {min_val}-{max_val} 之间")
        except ValueError:
            typer.echo("  ⚠ 请输入数字")


def prompt_bool(label: str, default: bool = False) -> bool:
    """Prompt user for a yes/no value."""
    hint = "[y/N]" if not default else "[Y/n]"
    value = input(f"\n▸ {label} {hint}: ").strip().lower()

    if not value:
        return default

    return value in ("y", "yes", "是", "true", "1")


def run_config_wizard(config_path: Path) -> BatchConfig:
    """Run interactive config wizard."""
    typer.echo("\n═══════════════════════════════════════")
    typer.echo("        Subtap 批量转录配置向导")
    typer.echo("═══════════════════════════════════════")

    # Load existing config as defaults
    existing = load_batch_config(config_path)

    # Mode
    mode = prompt_choice(
        "模式",
        ["fast", "quality"],
        default=existing.mode,
    )

    # Enhance
    enhance = prompt_choice(
        "字幕增强",
        ["off", "local", "api"],
        default=existing.enhance,
    )

    # Translate
    translate_options = ["不翻译", "英文 (en)", "日文 (ja)", "中文 (zh)"]
    translate_map = {"不翻译": None, "英文 (en)": "en", "日文 (ja)": "ja", "中文 (zh)": "zh"}
    translate_default = "不翻译"
    if existing.translate_to:
        for k, v in translate_map.items():
            if v == existing.translate_to:
                translate_default = k
                break
    translate_choice = prompt_choice(
        "翻译",
        translate_options,
        default=translate_default,
    )
    translate_to = translate_map[translate_choice]

    # Bilingual
    bilingual_options = ["关闭", "原文优先", "译文优先"]
    bilingual_map = {"关闭": "off", "原文优先": "source-first", "译文优先": "target-first"}
    bilingual_default = "关闭"
    for k, v in bilingual_map.items():
        if v == existing.bilingual:
            bilingual_default = k
            break
    bilingual_choice = prompt_choice(
        "双语字幕（仅翻译时有效）",
        bilingual_options,
        default=bilingual_default,
    )
    bilingual = bilingual_map[bilingual_choice]

    # Max chars
    max_chars = prompt_int(
        "最大字符数",
        default=existing.max_chars,
        min_val=10,
        max_val=60,
    )

    # Min chars
    min_chars = prompt_int(
        "最小字符数",
        default=existing.min_chars,
        min_val=4,
        max_val=30,
    )

    # Punctuation
    punctuation = prompt_bool(
        "是否带标点",
        default=existing.punctuation,
    )

    # Subtitle language
    lang_options = ["zh", "en", "ja"]
    subtitle_language = prompt_choice(
        "字幕语言",
        lang_options,
        default=existing.subtitle_language,
    )

    config = BatchConfig(
        mode=mode,
        enhance=enhance,
        translate_to=translate_to,
        bilingual=bilingual,
        max_chars=max_chars,
        min_chars=min_chars,
        punctuation=punctuation,
        subtitle_language=subtitle_language,
    )

    # Save config
    save_batch_config(config, config_path)
    typer.echo(f"\n✓ 配置已保存到 {config_path}")

    return config
