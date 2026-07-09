# Subtap — 项目上下文

> 本地优先的 AI 字幕生成引擎，基于 MLX Qwen3，完全离线运行。

## 核心术语

| 术语 | 英文 | 一句话解释 |
|------|------|-----------|
| 热词 | Hotword | ASR 经常转错的词，用户校正后存入术语表，下次自动替换 |
| 文稿匹配 | Script Match | 用参考文稿（txt/srt/md/docx/xlsx）校正 ASR 输出，提升准确率 |
| VAD | Voice Activity Detection | 语音活动检测，把音频切成"有人说话"的片段 |
| Chunk | — | VAD 切出来的音频片段，是 ASR 的输入单位 |
| ASR Segment | — | ASR 识别出的文本片段，带词级时间戳 |
| Clean Segment | — | Clean 阶段输出的文本片段，已做文本增强（typo 修复、标点规范化、LLM 润色）。有两个变体：`RawCleanSegment`（pipeline 内部，无 timing）和 `CleanSegment`（enhancement 模块，带 timing 不可变约束） |
| Sentence Segment | — | 分句后的片段，按语义断句 |
| Aligned Segment | — | 对齐后的最终片段，时间戳精准到词 |
| 术语表 | Glossary | 存储热词和替换规则，`~/.subtap/glossary/` |
| 学习档案 | Learning Profile | 用户偏好的 YAML 存储（`~/.subtap/profile/`），包含术语表、纠错对、分句偏好、翻译术语 |
| TextCleaner | — | LLM Protocol：segment 级 ASR 纠错（`clean_segments()`） |
| TextProofreader | — | LLM Protocol：可疑片段检测+修复（`select_suspicious_segments()` + `repair_segments()`），dict I/O |
| HotwordSuggester | — | LLM Protocol：热词替换建议（`replace_hotwords()`），dict I/O |
| TextTranslator | — | LLM Protocol：SRT 翻译（`translate_srt()`），支持自定义 prompt |

## 数据流

```
音频文件
  ↓ prepare
work/audio/source.wav
  ↓ chunk (VAD)
work/chunks/chunks.jsonl
  ↓ asr
work/asr/asr.jsonl
  ↓ clean (本地规则 + LLM 增强)
work/cleaned.jsonl
  ↓ segment (分句)
work/sentences.jsonl
  ↓ script_match (可选，文稿校正)
work/script_matched.jsonl
  ↓ align (强制对齐)
work/aligned.jsonl
  ↓ hotword (热词替换，原地修改)
work/aligned.jsonl
  ↓ translate (可选，添加翻译字段)
work/aligned.jsonl
  ↓ export
output/output.srt

全程伴随：RunLog → work/run_YYYYMMDD_HHMMSS.log
```

**旁路：** learn → 读 `llm_hotword_ops.jsonl` → 写 `~/.subtap/glossary/hotwords_zh.txt`

**完整阶段列表（11 个）：** prepare → chunk → asr → clean → segment → script_match → align → hotword → translate → learn → export

**日志输出：** 每次运行生成 `work/run_YYYYMMDD_HHMMSS.log`，`run_latest.log` 符号链接指向最新

## 模块职责

```
src/subtap/
├── core/           # Pipeline 主路径
│   ├── pipeline.py   # 阶段编排器（11 阶段，含 script_match）
│   ├── workspace.py  # 工作区文件管理（含 run_latest_log 属性）
│   ├── media.py      # prepare 阶段（ffmpeg 音频提取+重采样）
│   ├── vad.py        # chunk 阶段（Silero VAD）
│   ├── asr.py        # asr 阶段（MLX Qwen3，词级时间戳）
│   ├── clean.py      # clean 阶段（含 resolve_llm_flags，batch_size=50）
│   ├── segment.py    # segment 阶段（source_text = 子句自身文本）
│   ├── align.py      # align 阶段（优先读 script_matched.jsonl）
│   ├── hotword.py    # hotword 阶段（直接使用 HotwordGlossary.replace_in_text）
│   ├── translate.py  # translate 阶段（分块翻译，30 句/块，上下文滑动）
│   ├── export.py     # export 阶段（多格式：srt/vtt/json/tsv）
│   └── text_utils.py # 共享文本工具（标点规范化、CJK 空格）
├── backends/       # 可插拔后端
│   ├── asr/          # ASR 后端（MLX Qwen3、HTTP API）
│   ├── llm/          # LLM 后端（OpenAI 兼容，4 个 Protocol，指数退避重试，batch_size=50）
│   └── align/        # 对齐后端（MLX Qwen3、Mock）
├── schemas/        # 数据模型
│   ├── models.py     # 主力 schema（遗留，广泛使用）
│   ├── asr.py        # ASRDraft（局部使用）
│   ├── enhancement.py # CleanSegment（enhancement 模块专用）
│   ├── alignment.py  # AlignedSubtitle
│   ├── segmentation.py # SentenceCandidate
│   ├── subtitle.py   # FinalSubtitle
│   ├── glossary.py   # Glossary、GlossaryTerm
│   └── config.py     # 配置参数
├── engine/         # 执行引擎层
│   ├── controller.py # 任务生命周期
│   ├── state.py      # 状态机
│   ├── policy.py     # 执行策略（local/fast/quality）
│   ├── cleanroom.py  # 工作区卫生
│   └── git_guard.py  # Git 安全
├── enhancement/    # LLM 增强
│   ├── api_llm.py    # 远程 LLM 增强（含 SYSTEM_PROMPT/TASK_PROMPTS/build_prompt，单文件）
│   ├── local_rules.py # 本地规则增强
│   ├── validator.py  # 增强验证
│   └── tasks.py      # 增强任务枚举
├── ai/             # AI 辅助
│   ├── glossary_learner.py # 术语学习
│   ├── asr_postprocess.py  # ASR 后处理
│   ├── segmenter.py        # 智能分句
│   └── align_refiner.py    # 对齐优化
├── glossary/       # 术语表管理
│   ├── hotword.py    # HotwordGlossary（存储+替换+replace_in_text，自包含，22 条热词）
│   └── cli.py        # CLI 命令（add/list/remove）
├── learning/       # 学习导入
│   ├── importer.py   # 导入校正 SRT
│   └── profile_store.py # 学习档案存储
├── script/         # 文稿匹配
│   ├── match.py      # 匹配主入口（分块调用 LLM，30 句/块，上下文滑动）
│   ├── aligner.py    # 序列对齐（difflib.SequenceMatcher）
│   ├── corrector.py  # 文本纠错（rapidfuzz 相似度 >= 0.7）
│   ├── formatter.py  # 文稿格式化
│   └── loader.py     # 文稿加载（txt/srt/md/docx/xlsx）
├── batch/          # 批量处理
│   ├── batch.py      # 批量任务清单生成
│   ├── batch_config.py # 批量配置
│   ├── batch_progress.py # 进度追踪
│   ├── batch_dashboard.py # 仪表盘 UI
│   ├── batch_interactive.py # 交互式批量处理
│   └── batch_abort.py # 中止处理
├── metrics/        # 性能指标 + 运行日志
│   ├── events.py     # EventBus 事件系统
│   ├── run_log.py    # RunLog（人类可读执行日志，带时间戳）
│   ├── chunk_trace.py # ChunkTracer
│   ├── performance.py # 性能指标计算
│   └── profiler.py   # PipelineProfiler
└── ui/             # TUI 界面（过渡方案，GUI 在开发中）
```

## 三层学习闭环

```
learning/                ai/                    glossary/
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│ importer.py │    │ glossary_    │    │ hotword.py      │
│             │───▶│ learner.py   │───▶│ (HotwordGlossary│
│ 导入校正SRT │    │              │    │  load/save)     │
└─────────────┘    │ 检测重复错误 │    ├─────────────────┤
                   │ 提取术语     │    │ engine.py       │
                   │ 学习纠错模式 │    │ (替换引擎)      │
                   └──────────────┘    ├─────────────────┤
                                       │ cli.py          │
                                       │ (查看/编辑)     │
                                       └─────────────────┘

数据流：用户校正 → AI 学习 → 存入术语表 → 下次自动替换
```

## 设计约束

| 约束 | 说明 |
|------|------|
| **本地优先** | 默认不走远程，用户主动开启（`--enable-remote`） |
| **中文优先** | CLI、TUI、错误提示全部中文，内部日志可英文 |
| **JSONL 持久化** | 每个阶段输出 JSONL，支持断点续跑，文件可直接检查 |
| **可插拔后端** | ASR/LLM/Aligner 可替换，支持混合模式（本地+远程 fallback） |
| **UI 解耦** | Pipeline 核心不依赖 TUI/GUI，通过 EventBus 通信 |
| **macOS 优先** | 当前主要支持 macOS Apple Silicon（MLX 依赖） |
| **Run Log** | 每次运行生成 `run_YYYYMMDD_HHMMSS.log`，`run_latest.log` 符号链接指向最新 |

## LLM 批量处理策略

| 参数 | 值 | 说明 |
|------|---|------|
| 翻译分块 | 30 句/块 | 前后各 3 句上下文滑动，保持翻译连贯性 |
| API 重试 | 3 次 | 指数退避（1s/2s/4s）+ 随机 jitter |
| 校对 batch_size | 50 | 每批 50 句，减少 API 调用次数 |
| 可重试错误 | timeout, 429, 500, 502, 503, 504 | 不可重试错误直接抛出 |

**文件位置**：`backends/llm/openai_compat.py`（重试 + batch_size），`core/translate.py`（分块翻译）

## Run Log 系统

每次 pipeline 运行生成人类可读的日志文件，用于调试和问题排查。

**日志位置**：`work/run_YYYYMMDD_HHMMSS.log`（带时间戳），`work/run_latest.log` 符号链接指向最新。

**日志内容**：
- 系统环境（OS、Python、MLX 版本）
- 源文件信息（路径、大小、格式、时长、采样率、声道）— 顶部醒目显示
- 运行配置快照（mode、enhance、model、translate_to 等）
- 热词表信息（路径、条目数、加载状态）
- 阶段执行记录（成功/失败、耗时、详情）
- 错误 traceback（异常时记录完整堆栈）

**文件位置**：`metrics/run_log.py`（RunLog 类），`cli.py`（集成）

## 后端选择策略

三种执行模式，由 `engine/policy.py` 管理：

| 模式 | ASR 模型 | LLM | 对齐 | 用途 |
|------|----------|-----|------|------|
| `local` | asr_0.6b | ❌ | mlx-qwen-aligner | 纯本地，无外部依赖 |
| `fast` | asr_0.6b | ❌ | mlx-qwen-aligner | 最快速度 |
| `quality` | asr_1.7b | ✅ | mlx-qwen-aligner | 高质量，完整流程 |

## Schema 新旧两套

- **`models.py`** — 主力 schema，广泛使用（ASRSegment、RawCleanSegment、Chunk、AlignedSegment）
- **`asr.py`** — ASRDraft，仅 `core/asr.py` 使用
- **`enhancement.py`** — CleanSegment（带 timing 不可变约束），仅 enhancement 模块内部使用
- **`alignment.py`** — AlignedSubtitle，align 阶段输出
- **`segmentation.py`** — SentenceCandidate，segment 阶段输出
- **`subtitle.py`** — FinalSubtitle，export 阶段输出（只能从 AlignedSubtitle 创建）

**注意：** `CleanSegment` 有两个定义。`models.py:RawCleanSegment` 是轻量版（pipeline 内部，无 timing），`enhancement.py:CleanSegment` 带增强字段（enhancement_mode、changed、change_reasons + timing 不可变约束）。`models.py` 保留 `CleanSegment = RawCleanSegment` 向后兼容别名。

## 时间戳二分法

- **参考时间戳** — `ASRDraft.is_reference_only()` 硬编码返回 `True`，来自 ASR 的粗略时间
- **最终时间戳** — 只有 `AlignedSubtitle`（align 阶段）才是最终时间源
- **FinalSubtitle** — 只能通过 `from_aligned()` 工厂方法创建，不能从 ASR 直接生成

## 用户群体

- **视频创作者/UP主** — 快速给视频加字幕，追求准确率和易用性
- **字幕组/翻译团队** — 批量处理、术语一致、多语言支持
- **开发者/技术用户** — CLI 自动化、集成到工作流

## 相关文档

- `docs/agents/issue-tracker.md` — Issue Tracker 配置
- `docs/agents/triage-labels.md` — Triage 标签配置
- `docs/agents/domain.md` — Domain Docs 配置
- `docs/adr/` — 架构决策记录
- `docs/development-status.md` — 开发完成度报告（98%）
- `docs/fix-plan-2026-07-08.md` — Bug 修复方案
- `docs/fix-plan-llm-batch.md` — LLM 批量处理修复方案
