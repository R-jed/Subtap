# Subtap

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platform: macOS](https://img.shields.io/badge/platform-macOS%2013.5+-lightgrey.svg)](https://www.apple.com/macos/)
[![Tests](https://img.shields.io/badge/tests-752%20passed-brightgreen.svg)]()

**本地优先的 AI 字幕生成引擎** — 基于 MLX Qwen3 的端到端字幕工具，完全离线运行。

> 当前版本面向 macOS 开发版源码安装，支持策略为 macOS 13.5+ Apple Silicon。Intel x86_64 暂未验证，不作为当前开发版支持范围。当前不提供 Developer ID 签名、公证或正式二进制分发。

## 特性

- **完整 Pipeline** — 音频标准化 → 切段 → 语音识别 → 文本清洗 → 智能断句 → 文稿匹配（可选）→ 时间轴对齐 → 字幕导出
- **文稿匹配** — 支持 txt/srt/md/docx/xlsx 格式文稿，智能对齐+纠错，提升转录准确率
- **真实模型推理** — Qwen3-ASR（0.6B/1.7B）+ Qwen3-ForcedAligner，基于 Apple MLX 优化
- **中文优先** — 全部界面和状态提示均为中文
- **TUI 可视化** — 实时阶段进度、模型状态、执行摘要
- **插拔式架构** — ASR / LLM / Aligner 后端可替换
- **中间产物落盘** — 所有阶段输出 JSONL，支持断点续跑

## 隐私与本地优先

- **默认本地运行**：ASR 转录和时间轴对齐均在本地完成，音频不会发送到外部。
- **LLM 增强可选**：字幕文本增强支持本地规则或 LLM API，用户可自由选择。
- **`--local-only` 模式**：一键禁止所有外部 API 调用，确保完全离线。
- 项目管理只使用本地文件系统，不做账号、云同步、商业激活或权限系统。

## 快速开始

### 环境要求

- Python 3.10+
- macOS 13.5+（Apple Silicon）
- 约 4 GB 磁盘空间（用于模型）

### 安装

```bash
# 克隆项目
git clone https://github.com/R-jed/Subtap.git
cd Subtap

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装
pip install -e .

# 初始化（交互式模型下载）
subtap setup

# 检查环境
subtap doctor
```

### 模型安装

模型统一放在项目根目录 `models/`：

- `models/asr_0.6b` — 快速语音识别（约 960 MB，必需）
- `models/asr_1.7b` — 高质量语音识别（约 2.3 GB，可选）
- `models/aligner` — 时间轴精对齐（约 1.2 GB，默认流程必需；`--no-align` 可跳过）

`subtap setup` 支持四种下载方式：

1. Hugging Face 直连
2. Hugging Face 国内镜像（`https://hf-mirror.com`）
3. ModelScope（`modelscope.cn`）
4. 手动下载后放入 `models/`

### 基本用法

```bash
# 生成字幕
subtap run video.mp3

# 运行演示
subtap demo
```

## Pipeline

```mermaid
graph LR
    A[音频] --> B[切段]
    B --> C[语音识别]
    C --> D[文本清洗]
    D --> E[智能断句]
    E --> F[文稿匹配（可选）]
    F --> G[时间轴对齐（默认，可关闭）]
    G --> H[字幕导出]
    E --> I[Draft 导出（--no-align）]
```

每个阶段输出 JSONL 中间产物到 `work/` 目录，支持断点续跑。
默认会执行 ForcedAligner 精对齐并生成 `final.*`；使用 `--no-align` 会跳过精对齐，只生成 `draft.srt` 和 `draft.json`，适合粗剪预览，不作为最终交付字幕。

### 文稿匹配

文稿匹配是可选阶段，用于提升转录准确率。当提供参考文稿时，系统会：

1. **智能对齐** — 使用 difflib 行级序列对齐，处理 ASR 与文稿的行数差异
2. **句内纠错** — 使用 rapidfuzz 字符级纠错，相似度 ≥ 0.7 时自动修正
3. **自动格式化** — 去除注释（`#`、`//`、`【备注】`）、空行、合并空格

**支持的文稿格式：**

| 格式 | 说明 |
|------|------|
| `.txt` | 纯文本（推荐） |
| `.srt` | SRT 字幕文件（自动去除序号和时间轴） |
| `.md` | Markdown 文件（自动去除标记） |
| `.docx` | Word 文档 |
| `.xlsx` | Excel 文件（读取第一列） |

**匹配模式：**

- `follow_script`（默认）— 完整对齐+纠错，文稿行数与 ASR 行数不同时自动处理
- `correct_only` — 只纠错不重排，适合 ASR 行数与文稿一致的场景

## CLI 命令

```bash
# 运行完整流程（默认本地模式）
subtap run video.mp3

# 完全离线模式（禁止所有外部 API）
subtap run video.mp3 --local-only

# 关闭字幕增强
subtap run video.mp3 --enhance off

# 使用 LLM API 增强字幕
subtap run video.mp3 --enhance api

# 翻译字幕
subtap run video.mp3 --translate-to en

# 高质量模式（使用 1.7B 模型）
subtap run video.mp3 --mode quality

# 使用文稿匹配（提升转录准确率）
subtap run video.mp3 --script 文稿.txt

# 文稿匹配 + 纠错模式（只纠错，不重排）
subtap run video.mp3 --script 文稿.txt --script-mode correct_only

# 跳过精对齐，只生成 draft.srt / draft.json 粗剪预览
subtap run video.mp3 --no-align

# 运行演示
subtap demo

# 管理术语表
subtap glossary list
subtap glossary add --input "错词=正确词"
subtap glossary remove 错词

# 文稿匹配（独立命令）
subtap script match -i sentences.jsonl --script 文稿.txt --mode follow_script

# 文稿格式化（清理注释、空行）
subtap script format --script 文稿.txt

# 导入人工修正字幕到本地学习档案（写入前必须确认）
subtap learn import corrected.srt --yes
subtap profile export

# 检查环境
subtap doctor
subtap doctor --release    # 发布验收检查
subtap doctor --json       # 机器可读输出

# 管理模型
subtap models list
subtap models install asr_0.6b
subtap models verify

# 初始化向导
subtap setup
```

## 输出位置

默认输出到 `output/`。精对齐开启时生成：

- `final.srt`
- `final.vtt`
- `final.json`
- `final.tsv`
- `report.md`
- `metrics.json`
- `artifacts/`

使用 `--no-align` 时只生成 `draft.srt` 和 `draft.json`，报告会标明“未精对齐”。

## Mac 配置建议

- 入门：Apple Silicon，16 GB 内存，使用 `--mode fast`
- 更稳：Apple Silicon，24 GB 以上内存，使用 `--mode quality`
- 磁盘：至少预留 4 GB 给本地模型和中间产物

## 常见问题

**音频会上传吗？**  
不会。默认 ASR 和对齐都在本地执行，`--local-only` 会禁止所有外部 API。

**什么时候会联网？**  
`subtap setup` 下载模型时会联网；`subtap run --enhance api` 只会发送字幕文本给你配置的 LLM API，不发送音频。

**fast 和 quality 怎么选？**  
`fast` 使用 0.6B 模型，速度优先；`quality` 使用 1.7B 模型，质量优先但更吃内存。

**为什么有 draft 和 final？**  
`final.*` 只来自精对齐结果，适合交付；`draft.*` 是关闭精对齐时的粗时间轴预览。

**文稿匹配有什么用？**  
文稿匹配可以提升转录准确率。当有参考文稿时，系统会自动修正 ASR 转录中的错字、同音字、专业术语等问题。支持 txt/srt/md/docx/xlsx 格式。

## 配置

配置文件位置：`~/.subtap/config.yaml`

```yaml
# ASR 配置
asr:
  backend: mlx-qwen-asr
  model: asr_0.6b

# 对齐配置
align:
  backend: mlx-qwen-aligner

# 输出配置
output:
  timestamp: true
  keep_versions: 5
```

## 项目结构

```
Subtap/
├── src/subtap/           # 源代码
│   ├── core/             # 核心模块
│   │   ├── pipeline.py   # 流水线编排
│   │   ├── models.py     # 模型管理
│   │   └── setup.py      # 初始化向导
│   ├── backends/         # 后端实现
│   │   ├── asr/          # ASR 后端
│   │   ├── llm/          # LLM 后端
│   │   └── aligner/      # 对齐后端
│   ├── schemas/          # 数据模型
│   ├── ui/               # 用户界面
│   └── cli.py            # CLI 入口
├── configs/              # 配置文件
├── tests/                # 测试
├── models/               # 模型文件（gitignore）
└── pyproject.toml        # 项目配置
```

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest -v

# 运行单个测试
pytest tests/test_cli.py -v

# 代码检查
ruff check src/
mypy src/

# 发布验收
bash scripts/release-check.sh
```

## 贡献

欢迎提交 Issue 和 Pull Request。

1. Fork 项目
2. 创建特性分支（`git checkout -b feature/amazing-feature`）
3. 提交更改（`git commit -m 'feat: 添加某功能'`）
4. 推送到分支（`git push origin feature/amazing-feature`）
5. 创建 Pull Request

请确保：
- 所有测试通过（`pytest -v`）
- 代码通过 lint 检查（`ruff check`）
- 提交信息遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范

## 许可证

[MIT](./LICENSE)
