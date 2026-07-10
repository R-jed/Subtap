# Subtap — Session Handoff

> 上次更新：2026-07-10
> 交接人：当前会话 → 新会话

## 当前状态

**1029 测试全部通过，4 skipped，0 失败。** Pipeline 11/11 阶段可用。

**分支：** `main`（`feat/smart-split-v2` 已合并）

## 全 Pipeline 实测 Review（2026-07-10）

**测试素材：** 高质量中文语音.mp3（264.6s，科技产品评测——理光GR4）
**模式：** `--mode quality --enhance local --local-only`（1.7B 模型，离线）
**总耗时：** 42.0s（RTF 0.16），14 chunks → 56 segments

### Pipeline 各阶段问题清单

以下按严重程度排序，所有问题均来自实际 pipeline 输出。

---

#### BUG-01 `_inject_punct` 文本完整性校验失败（P0 · 质量）

**现象：** 12 条 `_inject_punct: 文本完整性校验失败` 警告。reconstructed 文本比原始 text 少字符。
**根因：** ASR 返回的 word list 缺少部分字符（英文单词、空格、连字符等），`_filter_words_to_text` 按字匹配时丢失位置。典型丢字模式：
- 空格：`"monochrome"` → ASR word `"monochrome"` 与 text 中 `" monochrome"` 位置不匹配
- 英文词组：`"iPhone Pocket"` → ASR 拆成 `"iPhone"` `"Pocket"` 但 text 中无空格
- 句首虚词：`"那"` `"正"` `"反"` `"开"` 等单字被 ASR 遗漏
**影响文件：** `src/subtap/core/export.py:257` (`_inject_punct`)、`src/subtap/core/export.py:248` (`_filter_words_to_text`)
**修复方向：** `_filter_words_to_text` 的字匹配逻辑需要容忍 ASR word list 的字符缺失，改用子序列匹配而非精确 `in` 检查。

---

#### BUG-02 `aligned_text` 字段始终为空（P0 · 数据完整性）

**现象：** `aligned_subtitles.jsonl` 中所有 segment 的 `aligned_text` 字段为空字符串。
**影响：** `export.py:907` (`_process_segment`) 中 `word_filter_text = getattr(seg, "aligned_text", None) or seg.text` 实际永远回退到 `seg.text`，align 阶段的词级对齐信息未被传递到导出层。
**影响文件：** `src/subtap/core/align.py`（未写入 `aligned_text`）、`src/subtap/schemas/models.py`（AlignedSegment 定义）
**修复方向：** align 阶段应将 forced aligner 的文本写入 `aligned_text` 字段。

---

#### BUG-03 SRT vs VTT 分段不一致（P1 · 产品行为）

**现象：** 同一 pipeline 产出两个不同分段策略的结果：
- `高质量中文语音.srt`（根目录）：97 行，分段更粗，合并了相邻句子
- `output/final.srt`：56 segments，分段更细
- `output/final.vtt`：进一步细拆，每行更短
**根因：** 根目录 SRT 使用 `_smart_split_v2`（DP 最优断句），`output/` 目录使用旧的 `_smart_split` 或不同的 max_chars 参数。
**影响：** 用户看到两套不一致的输出，混淆。
**修复方向：** 统一输出策略，根目录 SRT 应与 `output/final.srt` 完全一致。

---

#### BUG-04 过短 segment（P1 · 字幕质量）

**现象：** Seg 9 `"我们。"` 仅 0.10 秒（`30.92-31.02`），观众根本看不清。
**根因：** 断句阶段未过滤过短 segment。ASR chunk 边界切到了一个单字句。
**修复方向：** `_smart_split_v2` 后增加 post-filter：合并 duration < 0.5s 的 segment 到相邻 segment。

---

#### BUG-05 ASR 词分割问题——"二十八"→["二十","八"]（P1 · ITN）

**现象：** SRT 中出现 `"都是二。\n八毫米的"` 而非 `"都是28mm的"`。
**根因：** ASR 将"二十八"识别为两个 word `"二十"` `"八"`，ITN 只处理连续数字 word 但 ASR 的分词边界不连续（跨了 segment 边界）。在 SRT 输出中这两个 word 被分到不同行。
**影响文件：** `src/subtap/core/itn.py`（`chinese_to_num` 函数）、`src/subtap/core/export.py`（ITN 转换时机）
**修复方向：** ITN 转换应在 segment 级别而非 word 级别进行；或在 ASR 后处理阶段合并连续数字 word。

---

#### BUG-06 中文文本中混入英文空格（P2 · 排版）

**现象：** 4 个 segment 包含英文单词周围的空格：
- `"这个iPhone pocket里面"` → `"这个iPhone Pocket里面"`（有空格）
- `"模拟胶片的 app 有多大的区别"` → `"模拟胶片的app有多大的区别"`
- `"Highlight Diffusion Filter啊"` → `"Highlight Diffusion Filter啊"`
**根因：** `_inject_punct` 的 text_pos 跟踪器无法正确跳过 ASR word 与 text 之间的空格差异。
**修复方向：** `_inject_punct` 中 text 匹配时应跳过空白字符。

---

#### BUG-07 部分 segment 缺少句末标点（P2 · 标点完整性）

**现象：** Seg 35/40/47 末尾无标点：
- `"…内置了一个特殊的镜片"`（缺句号）
- `"…售价一千多块钱"`（缺句号）
- `"…它也内置了一个独特的滤镜"`（缺句号）
**根因：** `_smart_split_v2` 在这些位置断句时，原始文本的标点被分到了下一个 segment。
**修复方向：** 断句时如果切点在非标点位置，应自动补全句末标点（中文补`。`，英文补`.`）。

---

#### BUG-08 `_inject_punct` 警告信息中"正正好好"丢字（P2 · 边缘案例）

**现象：** 原始 text `"正正好好能够把它放进去。"` → reconstructed `"好好能够把它放进去。"`，丢失了前两个字。
**根因：** ASR word list 中缺少 `"正正"` 对应的 word，`_filter_words_to_text` 按字匹配时跳过了。
**修复方向：** 同 BUG-01，改进 `_filter_words_to_text` 的匹配策略。

---

#### BUG-09 `sentences.jsonl` 时间戳全为 0（P2 · 数据质量）

**现象：** `sentences.jsonl` 中所有 segment 的 `start_ms` 和 `end_ms` 均为 0。
**影响：** 下游消费者无法使用时间信息。
**影响文件：** `src/subtap/core/segment.py`（未传递时间戳到 sentences 输出）
**修复方向：** segment 阶段应从 aligned_subtitles 继承时间戳。

---

#### BUG-10 `batch-transcribe` 交互式向导覆盖 CLI 参数（P2 · UX）

**现象：** `subtap batch-transcribe --files a.mp3,b.mp3 --mode quality -y` 仍然弹出交互式配置向导，要求手动选择模式。
**根因：** `batch_transcribe()` 在 `-y` 模式下仍调用 `click.prompt()`，未检查 CLI 参数是否已提供。
**影响文件：** `src/subtap/cli.py:1206` (`batch_transcribe`)
**修复方向：** 当 `--mode`/`--enhance` 已通过 CLI 传入时，跳过交互式向导。

---

#### BUG-11 `cleaned.jsonl` 的 `text` 字段为空（P2 · 数据完整性）

**现象：** `cleaned.jsonl` 中所有 segment 的 `text` 为空字符串，但 `original_text` 有内容。
**影响：** clean 阶段的输出无法被下游正确消费。
**影响文件：** `src/subtap/core/clean.py`（`run_clean` 返回格式问题）
**修复方向：** `run_clean` 应将清洗后的文本写入 `text` 字段。

---

#### BUG-12 `--local-only` 与 `--translate-to` 互斥但错误信息不友好（P3 · UX）

**现象：** `subtap run --local-only --translate-to en` 报错 `"--local-only 模式下不能使用 --translate-to"`，但未说明原因（翻译需要 API）。
**修复方向：** 改进错误信息：`"翻译功能需要 LLM API 支持，请去掉 --local-only 或配置 API Key"`。

---

### 已验证正常的功能

| 功能 | 状态 | 备注 |
|---|---|---|
| 音频标准化 | ✅ | 48kHz → 16kHz 单声道 |
| VAD 切段 | ✅ | 14 chunks，边界合理 |
| ASR 语音识别 | ✅ | 1.7B 模型，RTF 0.16 |
| 文本清洗 | ⚠️ | 基本可用，但 cleaned.jsonl text 为空 |
| 智能断句 | ⚠️ | DP 断句可用，但有过短 segment |
| 时间轴对齐 | ⚠️ | 词级对齐可用，但 aligned_text 为空 |
| 热词替换 | ✅ | glossary 系统正常 |
| 字幕导出 SRT | ⚠️ | 基本可用，有丢字和标点缺失 |
| 字幕导出 VTT | ✅ | 格式正确 |
| 字幕导出 JSON | ✅ | 结构完整 |
| `subtap doctor` | ✅ | 所有检查通过 |
| `subtap models` | ✅ | 3 个模型已安装 |
| `subtap glossary` | ✅ | add/list/batch-add 正常 |
| 测试套件 | ✅ | 1029 passed, 4 skipped |

### 性能基线

| 指标 | 值 |
|---|---|
| 音频时长 | 264.6s |
| 总耗时 | 42.0s |
| RTF | 0.16 |
| ASR 耗时 | 35.5s（占 85%） |
| Align 耗时 | 5.8s（占 14%） |
| Segments 数 | 56 |

## 本次 Session 完成的工作

### 新增功能：Run Log 系统
- 人类可读的 pipeline 执行日志，`run_YYYYMMDD_HHMMSS.log`（带时间戳）
- `run_latest.log` 符号链接指向最新
- 源文件路径顶部醒目显示
- 文件：`metrics/run_log.py`，`cli.py`（集成），`tests/test_run_log.py`（11 个测试）

### Bug 修复（TDD，4 个）
| Bug | 修复 | 文件 |
|---|---|---|
| `--format` 不生效 | `formats={fmt}` | `tui.py` × 3 |
| 热词表 loaded=否 | `.entries` → `.hotwords` | `cli.py` |
| source_text 粒度 | `source_text=text` | `segmentation.py` |
| run.log 路径硬编码 | `{stem}.{fmt}` | `cli.py` |

### LLM 批量处理优化（Phase 1）
| 优化 | 变更 | 文件 |
|---|---|---|
| 翻译分块 | 30 句/块，前后各 3 句上下文滑动 | `translate.py` |
| API 重试 | 指数退避（1s/2s/4s）+ 随机 jitter，最多 3 次 | `openai_compat.py` |
| 批量大小 | batch_size 20→50，减少 60% API 调用 | `openai_compat.py`, `config.py` |

### 真实素材测试（10 个场景）
全部通过，除 agnes-2.0-flash 长视频翻译（API 不稳定，非代码问题）。

### 项目审查
完成全面功能审查，发现 5 个 P0 + 8 个 P1 + 6 个 P2 问题。

## 待修复问题（按优先级）

### P0 — 已全部修复 ✅
1. ~~**hotword 阶段是死代码**~~ — RichRunner/TUIRunner/PlainRunner 均已激活 `pipeline.run_stage("hotword")`，热词替换现在真正执行
2. ~~**STAGES 列表缺 `learn`**~~ — `Pipeline.STAGES` 已添加 `learn`（在 `translate` 之后），`state.py` 的 `STAGE_CN` 和 `STAGE_ORDER` 已同步
3. ~~**`min_chars` 默认值不一致**~~ — `export.py` `_smart_split` 默认值从 8 统一为 10，与 `SubtapConfig` 和 `BaseExporter` 一致
4. ~~**`command_deck.py` 源文件缺失**~~ — 从 pyc 字节码重建源文件，添加 `SUBTAP_ASCII` 到 `observer.py`，清理过期 pyc
5. ~~**TUI 配置同步率 44%**~~ — `ConfigManager` 新增 `to_subtap_config()` 和 `sync_from_config()` 方法，实现双向联动

### P1 — 短期修复（8 项）
6. ~~translate 原地覆盖 aligned.jsonl，无原子写入保护~~ — ✅ 已修复：先写临时文件再 rename，异常时清理
7. segment `source_text` 赋值逻辑有误（已修复为 `text`，但审查报告认为语义不符）
8. ~~batch-transcribe 缺少 `fmt`/`translate_to`/`bilingual` 参数传递~~ — ✅ 已修复：两处 run_pipeline 调用补全参数
9. ~~glossary 词表加载静默吞错~~ — ✅ 已修复：仅捕获 UnicodeDecodeError，其他异常自然抛出
10. ~~4 处未使用导入~~ — ✅ 已修复：移除 export.py `import re`、clean.py `ALL_PUNCT_RE`、hotword.py `from typing import Any`（tui.py 经 AST 分析确认无未使用导入）
11. ~~tui_app.py 18 处重复超时值~~ — ✅ 已修复：提取 `KEY_READ_TIMEOUT = 0.05` 常量，15 处替换
12. 29 个模块无测试（尤其 batch 6 个 + VAD 2 个）
13. ~~`hotword edit` 硬编码 `open -a Numbers`~~ — ✅ 已修复：新增 `_open_file_cross_platform()` 函数，支持 macOS/Linux/Windows

### P2 — 中期优化（6 项）
14. ~~export 缺 aligned.jsonl 存在性检查~~ — ✅ 已修复：`run_export` 和 `run_final_exports` 均添加文件存在性检查，抛出 `FileNotFoundError`
15. ~~segment `language` 参数未从配置读取~~ — ✅ 已修复：`_stage_segment` 从 `config.output.subtitle_language` 读取语言
16. ~~cli.py 12+ 处重复 `except ValueError` 模式~~ — ✅ 已修复：提取 `_handle_error()` 辅助函数，替换 20+ 处
17. 集成测试仅 1 个（0.8%）
18. `glossary import` 命令名不副实（只加载计数，不从外部导入）
19. 配置路径 CLI/TUI 不一致（CLI 直接构造 SubtapConfig，TUI 通过 ConfigManager → YAML → load_config）

## 建议修复顺序

**Phase 1（P0 核心功能）：**
- #1 hotword 死代码 → 让 RichRunner 真正调用 hotword 阶段
- #2 STAGES 缺 learn → 加入 STAGES 列表
- #3 min_chars 不一致 → 统一为 10
- #4 command_deck.py 缺失 → 恢复源文件或移除依赖

**Phase 2（TUI 优化）：**
- #5 TUI 配置同步 → ConfigManager 与 SubtapConfig 联动
- #6 translate 原子写入 → 先写临时文件再 rename
- #12 测试盲区 → 补充 batch + VAD 测试

## 关键文件

- `src/subtap/core/pipeline.py` — 阶段编排器（STAGES 列表 + handler 映射）
- `src/subtap/ui/tui.py` — RichRunner（实际执行逻辑）
- `src/subtap/ui/tui_app.py` — TUI 应用（状态机 + 视图）
- `src/subtap/ui/config_manager.py` — TUI 配置管理
- `src/subtap/core/export.py` — 导出（min_chars 不一致）
- `src/subtap/metrics/run_log.py` — Run Log 系统
- `src/subtap/core/translate.py` — 翻译分块
- `src/subtap/backends/llm/openai_compat.py` — API 重试 + batch_size

## 测试命令

```bash
python3 -m pytest tests/ -q
```

预期：1029 passed, 4 skipped, 0 failed。

## API 配置

- API Key: `sk-E22YhwyqhE1LKwXUEh1TADAOF5xGN6p14cBp6JlouRyQLPnn`
- Base URL: `https://apihub.agnes-ai.com/v1`
- Model: `agnes-2.0-flash`
- 注意：agnes-2.0-flash 长视频翻译不稳定，会断连

## 测试素材

路径：`/Users/qunqing/Downloads/ASR-SRT测试音频/`
- 短中文：`数字测试.mp3`（21s）
- 中文：`高质量中文语音.mp3`（264s）
- 英文：`高质量英文语音.mp3`（188s）
- 长视频：`[10]--DLC.如何从前期到后期获得好声音.mp4`（1220s, 488MB）
