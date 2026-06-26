# Subtap

**本地优先的 AI 字幕生成引擎** — 基于 MLX Qwen3 的端到端字幕工具，完全离线运行。

## 特性

- **完整 Pipeline**：音频标准化 → 切段 → 语音识别 → 文本清洗 → 智能断句 → 时间轴对齐 → 字幕导出
- **真实模型推理**：Qwen3-ASR (0.6B/1.7B) + Qwen3-ForcedAligner，基于 Apple MLX 优化
- **中文优先**：全部界面和状态提示均为中文
- **TUI 可视化**：实时阶段进度、模型状态、执行摘要
- **插拔式架构**：ASR / LLM / Aligner 后端可替换
- **中间产物落盘**：所有阶段输出 JSONL，支持断点续跑

## 安装

```bash
# 克隆项目
git clone <repo-url>
cd Subtap

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装
pip install -e .

# 初始化
subtap setup

# 检查环境
subtap doctor
```

### 模型下载

```bash
# ASR 模型（Qwen3-ASR-0.6B-8bit，约 960 MB）
huggingface-cli download aufklarer/Qwen3-ASR-0.6B-MLX-8bit --local-dir models/asr_0.6b

# ASR 模型（Qwen3-ASR-1.7B-8bit，约 2.3 GB，可选）
huggingface-cli download aufklarer/Qwen3-ASR-1.7B-MLX-8bit --local-dir models/asr_1.7b

# 对齐模型（Qwen3-ForcedAligner-0.6B-8bit，约 1.2 GB）
huggingface-cli download mlx-community/Qwen3-ForcedAligner-0.6B-8bit --local-dir models/aligner
```

## 快速开始

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
    E --> F[时间轴对齐]
    F --> G[字幕导出]
```

## TUI 示例

![TUI 示例](docs/tui-screenshot.png)

## 模型说明

| 模型 | 大小 | 用途 |
|------|------|------|
| Qwen3-ASR-0.6B | 约 960 MB | 快速语音识别 |
| Qwen3-ASR-1.7B | 约 2.3 GB | 高质量语音识别 |
| Qwen3-ForcedAligner-0.6B | 约 1.2 GB | 时间轴对齐 |

## CLI 命令

```bash
# 运行完整流程
subtap run video.mp3

# 运行演示
subtap demo

# 检查环境
subtap doctor

# 管理模型
subtap models list
subtap models install asr
subtap models verify

# 初始化
subtap setup
```

## 配置

配置文件位置：`~/.subtap/config.yaml`

```yaml
# 模式配置
mode: hybrid  # fast / quality / hybrid

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

## 许可证

MIT License
