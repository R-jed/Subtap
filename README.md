# Subtap

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platform: macOS](https://img.shields.io/badge/platform-macOS%2013.5+-lightgrey.svg)](https://www.apple.com/macos/)
[![Tests](https://img.shields.io/badge/tests-968%20passed-brightgreen.svg)]()

**本地优先的 AI 字幕生成引擎** — 基于 MLX Qwen3 的端到端字幕工具，完全离线运行。

> 当前版本面向 macOS 开发版源码安装，支持策略为 macOS 13.5+ Apple Silicon。

## 特性

- **本地优先** — 默认不走远程，用户主动开启（`--enhance api`）
- **中文优先** — CLI、TUI、错误提示全部中文
- **可插拔后端** — ASR / LLM / Aligner 可替换，支持混合模式
- **JSONL 持久化** — 每个阶段输出 JSONL，支持断点续跑
- **多格式导出** — SRT / VTT / JSON / TSV
- **热词替换** — 本地术语表自动校正常见 ASR 错误
- **文稿匹配** — 参考文稿校正 ASR 输出，提升准确率
- **智能断句** — DP 最优拆分 + jieba 分词 + 短碎片保护
- **数字转换** — 中文数字 → 阿拉伯数字（ITN），Latin+中文数字混合规范化
- **Run Log** — 每次运行生成人类可读的执行日志

## Pipeline 管道图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Subtap Pipeline                                │
│                        11 个阶段，串行执行                                │
└─────────────────────────────────────────────────────────────────────────┘

  音频文件（mp3 / wav / mp4）
       │
       ▼
  ┌─────────┐   ffmpeg 音频提取 + 重采样 16kHz
  │ prepare │   ────────────────────────────► work/audio/source.wav
  └────┬────┘
       │
       ▼
  ┌─────────┐   Silero VAD 语音活动检测
  │  chunk  │   ────────────────────────────► work/chunks/chunks.jsonl
  └────┬────┘   智能静音检测，切出"有人说话"的片段
       │
       ▼
  ┌─────────┐   MLX Qwen3 语音识别
  │   asr   │   ────────────────────────────► work/asr/asr.jsonl
  └────┬────┘   0.6b（快）/ 1.7b（准），词级时间戳
       │
       ▼
  ┌─────────┐   本地规则清洗 + LLM 增强（可选）
  │  clean  │   ────────────────────────────► work/cleaned.jsonl
  └────┬────┘   Unicode NFKC / 全角→半角 / 重复词去除
       │         标点规范化 / Latin+中文数字混合规范化
       │         热词表替换 / LLM 校对（--enhance api）
       ▼
  ┌─────────┐   智能断句（jieba 分词 + 标点边界）
  │ segment │   ────────────────────────────► work/sentences.jsonl
  └────┬────┘
       │
       ▼
  ┌──────────────┐   文稿匹配（可选）
  │ script_match │   ──────────────────────► work/script_matched.jsonl
  └──────┬───────┘   rapidfuzz 相似度匹配，参考文稿校正 ASR
         │           支持 txt / srt / md / docx / xlsx
         ▼
  ┌─────────┐   MLX 强制对齐
  │  align  │   ────────────────────────────► work/aligned.jsonl
  └────┬────┘   Qwen3-ForcedAligner，精确到词级时间戳
       │
       ▼
  ┌─────────┐   热词替换（原地修改 aligned.jsonl）
  │ hotword │   ────────────────────────────► work/aligned.jsonl
  └────┬────┘   本地术语表 ~/.subtap/glossary/hotwords_zh.txt
       │         保留 aligned_text 用于词级时间戳匹配
       ▼
  ┌───────────┐   AI 翻译（可选）
  │ translate │   ──────────────────────────► work/aligned.jsonl
  └─────┬─────┘   分块翻译，30 句/块，上下文滑动
        │         目标语言：--translate-to en / ja / ko
        ▼
  ┌─────────┐   热词学习（旁路）
  │  learn  │   ────────────────────────────► ~/.subtap/glossary/hotwords_zh.txt
  └────┬────┘   从 LLM 发现的新热词写入本地术语表
       │
       ▼
  ┌─────────┐   字幕导出
  │  export │   ────────────────────────────► output/<输入文件名>.srt
  └─────────┘   SRT / VTT / JSON / TSV 多格式
                断句：DP 最优拆分 + jieba 词边界 + 短碎片保护
                ITN：中文数字 → 阿拉伯数字

  ─────────────────────────────────────────────────────
  全程伴随：RunLog → work/run_YYYYMMDD_HHMMSS.log
```

## 安装

当前首发支持：macOS 13.5+ Apple Silicon。默认 ASR / 对齐依赖本地 MLX 模型；首次运行前执行 `subtap setup`。Linux / Windows 和离线免模型包不属于当前首发范围。

### 方式零：一键安装（自动选择最佳方式）

```bash
curl -sSL https://raw.githubusercontent.com/R-jed/Subtap/main/scripts/install.sh | bash
```

> 自动检测环境：macOS 优先 Homebrew；失败时依次尝试 uv、pipx、pip。安装后会执行 `subtap version` 和 `subtap doctor`。

### 方式一：Homebrew（推荐 macOS 用户）

```bash
brew tap R-jed/tap
brew install subtap
```

### 方式二：uv

```bash
# 临时运行
uvx subtap

# 全局安装
uv tool install subtap
```

> [uv](https://docs.astral.sh/uv/) 会自动管理 Python 环境和依赖，零配置。

### 方式三：源码安装

```bash
git clone https://github.com/R-jed/Subtap.git
cd Subtap
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

## 快速开始

```bash
subtap setup    # 下载模型
subtap run audio.mp3
```

## CLI 命令

```bash
subtap run audio.mp3                     # 生成字幕
subtap run audio.mp3 --script 文稿.txt   # 文稿匹配
subtap run audio.mp3 --format vtt        # 指定格式
subtap run audio.mp3 --translate-to en   # 翻译
subtap run audio.mp3 --enhance api       # 启用 LLM 校对
subtap batch-transcribe --dir /path/to/media/folder  # 批量处理
subtap demo                              # 运行演示
subtap doctor                            # 检查环境
subtap setup                             # 初始化向导
subtap glossary list                     # 管理术语表
subtap learn import corrected.srt        # 导入修正字幕
subtap profile export                    # 导出学习档案
```

## 后端选择

| 模式 | ASR 模型 | LLM | 对齐 | 用途 |
|------|----------|-----|------|------|
| `fast` | asr_0.6b | ❌ | mlx-qwen-aligner | 最快速度 |
| `quality` | asr_1.7b | ❌ | mlx-qwen-aligner | 高精度 ASR |
| `--enhance api` | — | ✅ | — | 启用 LLM 校对 |

ASR 模型和 LLM 开关是独立的，可以自由组合。

## 配置

配置文件路径：`~/.subtap/config.yaml`

```yaml
mode: offline
asr:
  model: asr_0.6b
output:
  subtitle_punctuation: false
  subtitle_language: zh
  max_chars: 25
  min_chars: 10
  subtitle_formats:
    - srt
```

## 热词表

路径：`~/.subtap/glossary/hotwords_zh.txt`

格式：`正确形式=ASR错误形式1,ASR错误形式2`

```
理光GR4=理光吉亚四,李光机亚四
GR3=G R三,G三
GR=吉亚斯,吉亚,G R,G二
Monochrome=Mono Com,MonoCom
防滴溅=防低键
进光量=进组
APS-C=APC
```

## 开发

```bash
pip install -e ".[dev]"
pytest -q

# 代码图谱
graphify query "热词替换流程"
graphify path "run_hotword" "HotwordGlossary"
```

## 许可证

[MIT](./LICENSE)
