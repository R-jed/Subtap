# Phase 14: Subtap 安装与用户交付系统设计

## 概述

定义用户如何安装、依赖如何管理、模型如何加载，使 Subtap 成为可交付产品。

## CLI 命令结构

```
subtap run      # 运行字幕生成
subtap setup    # 用户初始化向导
subtap doctor   # 系统诊断
subtap models   # 模型管理
subtap init     # 开发级初始化（隐藏）
```

## 职责边界

| 命令 | 职责 | 可调用 | 禁止调用 |
|------|------|--------|----------|
| `setup` | 用户首次初始化 | init, models, doctor | - |
| `init` | 创建目录结构 | - | models, doctor |
| `doctor` | 系统诊断 | - | init, models, setup |
| `models` | 模型管理 | - | init, doctor, setup |
| `run` | 执行 pipeline | - | init, setup, models |

### 调用关系

```
用户
  │
  ▼
subtap setup ──┬── init (创建目录)
               ├── models install (下载模型)
               └── doctor (验证环境)
               
subtap run ──── 直接执行 pipeline
subtap doctor ─ 只读诊断
subtap models ─ 模型 CRUD
subtap init ─── 目录创建（隐藏）
```

### 边界规则

1. **单向调用**：setup → init/models/doctor，其他命令不互相调用
2. **职责单一**：每个命令只做一件事
3. **无副作用**：doctor 只读，不修改状态
4. **幂等性**：init 可重复执行，不破坏现有数据

---

## `subtap setup` 设计

### 命令格式

```bash
subtap setup                    # 交互式向导（默认）
subtap setup --quick            # 快速模式（只下载 0.6B）
subtap setup --full             # 完整模式（下载所有模型）
subtap setup --skip-models      # 跳过模型下载
subtap setup --mode fast        # 指定模式（影响 ASR 模型选择）
```

### 执行流程

```
Step 1: 系统检查
├── 检查 ffmpeg
├── 检查 Python 版本
└── 失败则提示安装方法

Step 2: 配置初始化
├── 检查 ~/.subtap/ 是否存在
├── 不存在则调用 init
└── 存在则跳过

Step 3: 模型安装
├── 对齐模型（1.4GB）：自动下载
├── ASR 模型：
│   ├── --mode fast → asr_0.6b
│   ├── --mode quality → asr_1.7b
│   ├── --quick → asr_0.6b
│   ├── --full → 两个都下载
│   └── 默认：提示用户选择
└── --skip-models → 跳过

Step 4: 环境验证
├── 调用 doctor 检查
└── 输出系统状态
```

### 交互式选择

```
═══ Subtap 初始化向导 ═══

▸ Step 1: 系统检查
  ✓ ffmpeg 已安装
  ✓ Python 3.10+

▸ Step 2: 初始化配置
  ✓ ~/.subtap/ 已创建
  ✓ config.yaml 已生成

▸ Step 3: 模型安装
  对齐模型（1.4GB）：自动下载 ✓
  ASR 模型：
    [1] asr_0.6b (964MB) — 快速模式推荐
    [2] asr_1.7b (2.3GB) — 高质量模式推荐
    [3] 两个都下载
  请选择 [1/2/3]: 1
  ✓ asr_0.6b 已下载

▸ Step 4: 环境验证
  ✓ 所有检查通过

═══ 初始化完成 ═══
下一步：subtap run <音频文件>
```

---

## `subtap init` 设计（开发级）

### 职责

仅创建目录结构，不下载模型

### 执行内容

```
subtap init
├── 创建 ~/.subtap/
├── 初始化 config.yaml
├── 初始化 glossary/
└── 初始化 subtap.db
```

### 不包含

- 系统依赖检查
- 模型下载
- 环境验证

---

## `subtap doctor` 增强

### 新增检查项

- 模型完整性验证
- 配置文件有效性
- Pipeline 健康状态

### 输出格式

```
═══ 系统诊断 ═══

▸ 系统依赖
  ✓ ffmpeg 6.0
  ✓ Python 3.11.5

▸ 配置状态
  ✓ ~/.subtap/config.yaml 有效
  ✓ 术语表已初始化

▸ 模型状态
  ✓ aligner (1.4GB)
  ✓ asr_0.6b (964MB)
  ○ asr_1.7b 未安装

▸ Pipeline 状态
  ✓ 所有阶段可执行

═══ 诊断完成 ═══
```

---

## `subtap models` 增强

### 命令扩展

```bash
subtap models status            # 查看状态
subtap models install <name>    # 安装模型
subtap models verify            # 验证完整性
subtap models list              # 列出可用模型（新增）
subtap models remove <name>     # 移除模型（新增）
```

---

## 配置系统统一

### ~/.subtap/config.yaml 结构

```yaml
# 模式配置
mode: hybrid  # fast / quality / hybrid

# ASR 配置
asr:
  backend: mlx-qwen-asr
  model: asr_0.6b  # 或 asr_1.7b

# 对齐配置
align:
  backend: mlx-qwen-align
  model: aligner

# 输出配置
output:
  format: srt  # srt / ass / txt
  directory: ./output

# 术语表
glossary:
  path: ~/.subtap/glossary/global.yaml
```

---

## 模型管理规则

### 存储位置

```
~/.subtap/models/
├── asr/
│   ├── asr_0.6b/
│   └── asr_1.7b/
└── aligner/
```

### 下载规则

- 对齐模型：setup 时自动下载
- ASR 模型：根据模式选择下载
- 至少需要一个 ASR 模型

### 验证规则

- 文件完整性检查
- 模型加载测试
- 定期健康检查

---

## 模型大小

| 模型 | 大小 |
|------|------|
| aligner | 1.4GB |
| asr_0.6b | 964MB |
| asr_1.7b | 2.3GB |

---

## 验收标准

1. ✔ `subtap setup` 可完整完成用户初始化
2. ✔ `subtap init` 不影响 setup
3. ✔ `subtap models` 可被 setup 调用
4. ✔ `subtap doctor` 可验证 setup 结果
5. ✔ 至少下载一个 ASR 模型
6. ✔ 对齐模型自动下载
7. ✔ 所有用户输出为中文
