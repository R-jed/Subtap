# Subtap

**本地优先的 AI 字幕生成引擎** — 基于 MLX Qwen3 的端到端字幕工具，完全离线运行。

## ✨ 特性

- 🎯 **完整 Pipeline**：音频标准化 → 切段 → 语音识别 → 文本清洗 → 智能断句 → 时间轴对齐 → 字幕导出
- 🧠 **真实模型推理**：Qwen3-ASR (0.6B/1.7B) + Qwen3-ForcedAligner，基于 Apple MLX 优化
- 🌏 **中文优先**：全部界面和状态提示均为中文
- 📊 **TUI 可视化**：实时阶段进度、模型状态、执行摘要
- 🔌 **插拔式架构**：ASR / LLM / Aligner 后端可替换
- 💾 **中间产物落盘**：所有阶段输出 JSONL，支持断点续跑

## 📦 安装

```bash
# 克隆项目
git clone <repo-url>
cd Subtap

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装（开发模式）
pip install -e .

# 检查环境
subtap doctor --release
```

### 模型下载

```bash
# ASR 模型（Qwen3-ASR-0.6B-8bit，~960MB）
huggingface-cli download aufklarer/Qwen3-ASR-0.6B-MLX-8bit --local-dir models/asr_0.6b

# ASR 模型（Qwen3-ASR-1.7B-8bit，~2.3GB，可选）
huggingface-cli download aufklarer/Qwen3-ASR-1.7B-MLX-8bit --local-dir models/asr_1.7b

# 对齐模型（Qwen3-ForcedAligner-0.6B-8bit，~1.2GB）
huggingface-cli download mlx-community/Qwen3-ForcedAligner-0.6B-8bit --local-dir models/aligner
```

## 🚀 快速开始

```bash
# 一键生成字幕
subtap run video.mp3

# 指定输出格式和目录
subtap run video.mp3 -o ./subtitles --format ass

# 跳过清洗和对齐（快速模式）
subtap run video.mp3 --skip-clean --skip-align

# 纯文本输出（无 TUI）
subtap run video.mp3 --no-tui

# 运行演示
subtap demo
```

## 🔧 Pipeline 流程

```
输入媒体 → [1] 音频标准化 → [2] 音频切段 → [3] 语音识别
                                              ↓
输出字幕 ← [7] 字幕导出 ← [6] 时间轴对齐 ← [5] 智能断句 ← [4] 文本清洗
```

| 阶段 | 说明 | 依赖 |
|------|------|------|
| 音频标准化 | ffmpeg 提取 16kHz mono WAV | ffmpeg |
| 音频切段 | VAD 静音检测，按语义切分 | pydub |
| 语音识别 | Qwen3-ASR 真实推理 | mlx-audio |
| 文本清洗 | 术语替换 + LLM 纠错（可选） | ollama / openai |
| 智能断句 | 规则分句，字符比例时间分配 | 无 |
| 时间轴对齐 | Qwen3-ForcedAligner 字符级对齐 | mlx-audio |
| 字幕导出 | SRT / ASS / TXT 格式输出 | 无 |

## 🖥️ TUI 界面

```
╭──────────────────────────────────────────╮
│         Subtap 字幕生成引擎               │
╰──────────────────────────────────────────╯

▸ [1/7] 音频标准化
  ✓ 264.6s, 48000Hz

▸ [3/7] 语音识别
  共 14 个音频片段
  ✓ 14 条

╭──────────────────────────────────────────╮
│              全流程完成                   │
╰──────────────────────────────────────────╯
  音频标准化      0.3s
  语音识别       17.4s
  总耗时         17.9s
```

## 📋 CLI 命令

| 命令 | 说明 |
|------|------|
| `subtap run <file>` | 运行完整流程 |
| `subtap demo` | 运行演示 |
| `subtap doctor` | 环境检查 |
| `subtap doctor --release` | 发布前完整检查 |
| `subtap version` | 版本信息 |
| `subtap init` | 初始化工作空间 |
| `subtap models status` | 查看模型状态 |
| `subtap models verify` | 验证模型完整性 |
| `subtap prepare <file>` | 单阶段：音频标准化 |
| `subtap transcribe <file>` | 单阶段：语音识别 |
| `subtap clean <file>` | 单阶段：文本清洗 |
| `subtap segment <file>` | 单阶段：智能断句 |
| `subtap align <file>` | 单阶段：时间轴对齐 |
| `subtap export <file>` | 单阶段：字幕导出 |

## 🧩 模型说明

| 模型 | 用途 | 大小 | 量化 |
|------|------|------|------|
| Qwen3-ASR-0.6B | 语音识别（默认） | ~960MB | 8bit |
| Qwen3-ASR-1.7B | 语音识别（高质量） | ~2.3GB | 8bit |
| Qwen3-ForcedAligner-0.6B | 时间轴对齐 | ~1.2GB | 8bit |

模型存放于项目 `models/` 目录，通过 `subtap models status` 查看状态。

## 📁 项目结构

```
subtap/
├── pyproject.toml
├── README.md
├── configs/default.yaml
├── models/                    # 模型文件（gitignore）
│   ├── asr_0.6b/
│   ├── asr_1.7b/
│   └── aligner/
├── src/subtap/
│   ├── __init__.py
│   ├── cli.py                 # CLI 入口（中文）
│   ├── core/
│   │   ├── pipeline.py        # Pipeline 编排器
│   │   ├── media.py           # 音频提取
│   │   ├── vad.py             # VAD 切段
│   │   ├── asr.py             # ASR pipeline stage
│   │   ├── clean.py           # 清洗 pipeline stage
│   │   ├── segment.py         # 断句 pipeline stage
│   │   ├── segmentation.py    # 规则分句引擎
│   │   ├── align.py           # 对齐 pipeline stage
│   │   ├── export.py          # SRT/ASS/TXT 导出
│   │   ├── workspace.py       # 工作空间管理
│   │   └── models.py          # 模型注册/下载/验证
│   ├── schemas/
│   │   ├── models.py          # Pydantic 数据模型
│   │   ├── config.py          # 配置 schema
│   │   └── glossary.py        # 术语表 loader
│   ├── backends/
│   │   ├── asr/               # ASR 后端（MLX/HTTP）
│   │   ├── llm/               # LLM 后端（Ollama/OpenAI/LMStudio）
│   │   └── align/             # 对齐后端（MLX/Mock）
│   ├── ui/
│   │   ├── state.py           # 管道状态系统
│   │   ├── progress.py        # Rich 进度展示
│   │   └── tui.py             # TUI / Plain Runner
│   └── utils/
│       ├── ffmpeg.py          # FFmpeg 封装
│       ├── logging.py         # 日志系统
│       └── logger.py          # 中文日志翻译层
└── tests/                     # pytest 测试（82 项）
```

## ⚙️ 配置

配置文件位于 `~/.subtap/config.yaml`，支持以下选项：

```yaml
audio:
  sample_rate: 16000
  channels: 1
  vad:
    min_silence_sec: 0.4
    min_chunk_sec: 1.0
    max_chunk_sec: 30.0

asr:
  backend: mlx-qwen-asr
  hotwords: []

clean:
  backend: ollama:qwen3-coder

align:
  backend: mlx-qwen-aligner

workspace:
  root: ./work
  keep_intermediate: true
```

## 🧪 测试

```bash
pytest -v          # 运行全部 82 项测试
```

## 📄 许可证

MIT License
