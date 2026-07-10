# Segmentation Benchmark

多方案断句效果对比工具，用于评估不同断句策略的 SRT 质量。

## 方案列表

| 编号 | 方案 | 说明 | 依赖 |
|------|------|------|------|
| A | baseline | 现有正则三层 + jieba | 无 |
| B | funasr_punct | FunASR CT-Transformer 标点恢复 | funasr |
| C | regroup | stable-ts 风格可配置管线 | 无 |
| D | conjunctions | WhisperX 多语言连词表兜底 | 无 |
| E | anomaly | faster-whisper 异常检测 | 无 |
| F | combined | B+C 组合 | funasr |

## 快速开始

```bash
# 1. 安装依赖（可选）
pip install funasr onnxruntime  # 方案 B/F 需要

# 2. 运行 benchmark
cd benchmarks
python generate_srt.py

# 3. 查看结果
ls results/srt/
```

## 测试数据

### 现有素材
- 高质量中文语音.mp3
- 短的演讲音频.wav
- 长视频素材.mp4

### 边界场景
- 无标点文本
- 超长句（100+字）
- 口语化文本
- 中英混排
- 数字/专有名词

## 评估维度

### 核心维度（人工 Review）
- 嘴型对齐（40%）
- 断句自然度（35%）
- 语义完整性（25%）

### 辅助指标
- 句子长度标准差
- 处理耗时

## 目录结构

```
benchmarks/
├── implementations/    # 各方案实现
├── utils/              # 公共工具
├── data/               # 测试数据
├── results/            # 输出目录
├── generate_srt.py     # 生成 SRT
└── README.md           # 本文件
```
