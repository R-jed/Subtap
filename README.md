# Subtap

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platform: macOS](https://img.shields.io/badge/platform-macOS%2013.5+-lightgrey.svg)](https://www.apple.com/macos/)

**本地优先的 AI 字幕生成引擎** — 基于 MLX Qwen3 的端到端字幕工具，完全离线运行。

> ⚠️ 开发中，尚未发布。

## 支持范围

Subtap 当前支持 Apple Silicon Mac，使用 MLX 在本地生成字幕。项目仍处于开发阶段，Homebrew 正式分发尚未完成。

## 开发环境使用

```bash
uv sync --extra dev
uv run subtap setup
uv run subtap doctor
uv run subtap run input.mp3 --mode quality --enhance local --local-only
```

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
