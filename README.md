# Subtap

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platform: macOS](https://img.shields.io/badge/platform-macOS%2013.5+-lightgrey.svg)](https://www.apple.com/macos/)
[![Tests](https://img.shields.io/badge/tests-752%20passed-brightgreen.svg)]()

**本地优先的 AI 字幕生成引擎** — 基于 MLX Qwen3 的端到端字幕工具，完全离线运行。

> 当前版本面向 macOS 开发版源码安装，支持策略为 macOS 13.5+ Apple Silicon。

## 特性

- **文稿匹配** — 支持 txt/srt/md/docx/xlsx 格式，智能对齐+纠错，提升转录准确率
- **真实模型推理** — Qwen3-ASR + Qwen3-ForcedAligner，基于 Apple MLX 优化
- **中文优先** — 全部界面和状态提示均为中文
- **插拔式架构** — ASR / LLM / Aligner 后端可替换
- **中间产物落盘** — 所有阶段输出 JSONL，支持断点续跑

## 快速开始

```bash
git clone https://github.com/R-jed/Subtap.git
cd Subtap
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
subtap setup    # 下载模型
subtap run audio.mp3
```

## 文稿匹配

提供参考文稿可提升转录准确率：

```bash
subtap run audio.mp3 --script 文稿.txt
```

支持格式：`.txt`、`.srt`、`.md`、`.docx`、`.xlsx`

## CLI 命令

```bash
subtap run audio.mp3              # 生成字幕
subtap run audio.mp3 --script 文稿.txt  # 文稿匹配
subtap demo                       # 运行演示
subtap doctor                     # 检查环境
subtap setup                      # 初始化向导
subtap glossary list              # 管理术语表
subtap learn import corrected.srt # 导入修正字幕
subtap profile export             # 导出学习档案
```

## 开发

```bash
pip install -e ".[dev]"
pytest -v
```

## 许可证

[MIT](./LICENSE)
