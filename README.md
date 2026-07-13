# Subtap

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platform: macOS](https://img.shields.io/badge/platform-macOS%2013.5+-lightgrey.svg)](https://www.apple.com/macos/)

**本地优先的 AI 字幕生成引擎** — 基于 MLX Qwen3 的端到端字幕工具，完全离线运行。

> ⚠️ 开发中，尚未正式发布。

## 支持范围

Subtap 当前支持 Apple Silicon Mac（macOS 13.5+），使用 MLX 在本地生成字幕。

## 安装

<!-- TODO: 待真实 Tap 冷安装验证通过后，替换为以下命令 -->
<!-- ```bash -->
<!-- brew install r-jed/tap/subtap -->
<!-- subtap -->
<!-- ``` -->

当前仅支持开发环境使用，详见下方。

> 卸载 Subtap 不会删除 `~/.subtap` 中的模型、热词、文稿和历史任务。

## 开发环境使用

```bash
uv sync --extra dev
uv run subtap setup
uv run subtap doctor
uv run subtap run input.mp3 --mode quality --enhance local --local-only
```

## 开发指南

```bash
# 启用 pre-commit hook（black + mypy + shellcheck）
git config core.hooksPath .githooks
```

启用后，每次 `git commit` 会自动检查暂存文件的格式和类型。工具未安装时自动跳过，CI 是最终兜底。

## 常用命令

- `subtap run`：运行完整字幕流程
- `subtap setup`：初始化配置与模型
- `subtap doctor`：检查本地环境
- `subtap demo`：运行演示
- `subtap glossary`：管理热词
- `subtap learn`：学习人工修正
- `subtap profile`：查看本地学习档案

## 许可证

[MIT](./LICENSE)
