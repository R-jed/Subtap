# Subtap 本地智能断句算法文档

> 最后更新：2026-06-29
> 分支：`feat/word-level-alignment` → 已合并至 `main`
> 测试覆盖：641 个测试全绿

## 一、算法概述

Subtap 的本地智能断句算法是一个**纯离线、基于规则**的中文/英文字幕断句系统。核心设计原则：

- **绝不丢字**：输入的每个字都必须出现在输出中，算法只做分割和移动，不做删除
- **max_chars / min_chars 可配置**：用户可通过 CLI 参数控制断句宽度
- **三层架构**：短语边界（phrases）→ 小句边界（clauses）→ 断句导出（export）

## 二、处理链路

Pipeline 完整链路：

```
prepare → chunk → asr → clean → segment → align → export
```

智能断句发生在 **export 阶段**，对齐后的 `aligned.jsonl` 是断句算法的输入。

### 2.1 三层处理架构

```
┌─────────────────────────────────────────────────────────┐
│                    export.py: _smart_split               │
│                                                         │
│  输入: words[], text, max_chars, min_chars              │
│                                                         │
│  Step 1: mark_phrase_boundaries(words)                  │
│          ↓ phrases.py: 标记不可拆分的语法结构            │
│          输出: marked_words (增加 phrase_role 字段)      │
│                                                         │
│  Step 2: identify_clause_boundaries(words, marked)      │
│          ↓ clauses.py: 识别每个词位置的断句评分          │
│          输出: boundaries[] (boundary_type, score)       │
│                                                         │
│  Step 3: Greedy split using boundaries                  │
│          ↓ 按分数贪心断句 + 尾虚词剥离 + 碎片合并       │
│          输出: lines[] (text, start_sec, end_sec)       │
└─────────────────────────────────────────────────────────┘
```

### 2.2 phrases.py — 短语边界标记

标记不可拆分的语法结构，返回每个词的 `phrase_role`：

| role | 含义 | 说明 |
|------|------|------|
| `phrase_start` | 短语开始 | 的/得/地 结构的起始 |
| `phrase_mid` | 短语中间 | **不可在此断开** |
| `phrase_end` | 短语结束 | 的/得/地 结构的结束 |
| `particle` | 语气词 | 仅在词列表末尾标记 |
| `None` | 普通词 | 无特殊约束 |

**保护的语法结构：**

1. **关联词对**：虽然…但是、因为…所以、不仅…而且、即使…也 等 11 组
2. **的/得/地 结构**：向左扫描修饰语，向右扫描中心词，整个结构标记为 `phrase_mid` 保护区
   - 的字结构：在标点、语气词、常见副词/助动词处停止
   - 得字结构：仅在标点、语气词处停止（补语范围更宽）
3. **语气词**：仅在词列表末尾时标记为 `particle`

### 2.3 clauses.py — 小句边界识别

识别每个词位置是否是小句边界，返回 `boundary_type` 和 `score`：

| boundary_type | score | 触发条件 |
|---------------|-------|----------|
| `sentence_end` | 100 | 句末标点（。！？.!?） |
| `comma` | 80 | 逗号/分号（，、,;） |
| `pause` | 60 | 停顿 ≥ 0.2 秒 |
| `conjunction` | 55 | 双字连词起始（但是、所以、因为 等 30+ 个） |
| `particle` | 50 | 语气词之后的位置（了、呢、吧、啊 等） |

**保护区逻辑：**
- `sentence_end` 和 `comma` 不受保护区限制（强边界）
- `conjunction` 在保护区内部也会触发（连词必须从短语中间开始）
- `pause` 和 `particle` 跳过 `phrase_mid` 保护区

### 2.4 export.py — 断句导出

`_smart_split` 是核心断句函数，贪心算法：

```
for each word in words:
    1. 应用 pending_prefix（上一行剥离的尾虚词）
    2. 句末标点 → 立即 flush
    3. 数字序列保护 → 整体跳过或提前 flush
    4. max_chars 检查 → 超限则提前 flush
    5. 断句边界检查（pause/conjunction/particle）→ 在词前断开
    6. 将词加入当前行
    7. 断句边界检查（sentence_end/comma/max_chars）→ 在词后断开

最终兜底: return lines if lines else [原始文本]
```

**尾虚词剥离机制：**

`_flush_line` 在输出一行前，检查行尾是否是尾虚词（连词/语气词/代词/指示词）：
- 如果是，剥离尾虚词存入 `_pending_prefix`
- 下一行开始时，将 `_pending_prefix` 拼回行首
- 最终 flush 时跳过剥离（防止数据丢失）

**尾虚词列表 (`_TRAILING_WORDS`)：**

```python
{
    # 连词（双字）
    "但是", "所以", "因为", "而且", "不过", "可是", "然后", "或者", "于是", "因此", "虽然",
    # 单字连词
    "因", "则", "但", "所", "以", "才", "会", "又", "也",
    # 语气词
    "呃", "呢", "啊", "呀", "吧", "嘛", "哦", "嗯", "哈", "哎",
    # 代词/主语
    "我们", "它们", "它能", "它还", "他还", "她还",
    # 指示词
    "这个", "那个", "这些", "那些", "那这", "那还",
}
```

**碎片合并：**
- ≤1 字符的碎片：总是合并到上一行
- ≤2 字符的碎片：除非上一行是硬断句（sentence_end / comma），否则合并
- 合并后不能超过 max_chars

**跨行断词修复 (`_fix_split_words`)：**
- 检测行尾文本是否是某个双字词的前半部分
- 如果是，将行尾词移到下一行
- 仅在时间间隔 < 0.3 秒时触发
- 英文单词（含 Latin 字符）仅在同一句子内合并

## 三、ITN 中文数字规范化

`core/itn.py` — 在 SRTExporter.render() 最终阶段应用，不影响断句判断。

### 3.1 转换策略（按数量级）

| 数量级 | 策略 | 示例 |
|--------|------|------|
| 个/十/百/千 | 全量转换 | 六千四百九十九 → 6499 |
| 万级 | 保留单位 | 一万两千 → 1.2 万，十二万 → 12 万 |
| 亿级 | 保留单位 | 一亿两千万 → 1.2 亿 |
| 万亿级 | 保留单位 | 一万亿 → 1 万亿 |

### 3.2 保护机制

| 类型 | 策略 | 示例 |
|------|------|------|
| 概数后缀 | 不转换 | 一万多元 → 一万多元（不转为 10000 多元） |
| 成语/复合词 | 不转换 | 百万富翁、万元户 |
| 纯数字序列 | 转换 | 二零二五 → 2025 |
| 概数前缀 | 转换后保留中文 | 上千张 → 上千张（1000→千→千） |
| 比值 | 转换 | 三十二比九 → 32:9 |
| 小数点 | 保护 | 0.6 秒 → 0.6 秒（不被标点清理破坏） |

### 3.3 特殊处理

- `_DECIMAL_DOT_RE`：保护小数点（`\d.\d` 模式）
- `_RATIO_RE`：比值转换（`X比Y` → `X:Y`）
- `_APPROX_RE`：概数前缀 + 中文数字 → 阿拉伯数字 + 中文简写
- `_is_idiom`：成语检测（"百万富翁"、"万元户"）
- `_strip_punct`：清理标点时保护小数点和比值冒号

## 四、CLI 配置参数

```bash
subtap run <input> [选项]

--max-chars   -M   INT   每行字幕最大字符数  [默认: 25; 10-60]
--min-chars   -m   INT   每行字幕最小字符数  [默认: 10; 4-30]
```

**配置层级：**
- CLI 参数 → `SubtapConfig.output.max_chars` / `min_chars`
- Pydantic 校验：`max_chars: int = Field(default=25, ge=10, le=60)`
- typer 校验：`min=10, max=60`

**传递链路：**
```
CLI → config.output.max_chars/min_chars
  → Pipeline._stage_export() → run_export(max_chars, min_chars)
    → SRTExporter(max_chars, min_chars) → _smart_split(max_chars, min_chars)
```

## 五、输出规范

- **输出格式**：仅 SRT（其他格式如 VTT/JSON/TSV 已从默认输出移除）
- **诊断文件**：metrics.json、debug.json、run.log.jsonl 写入 `work/` 目录，不污染 output 目录
- **文件命名**：`{源文件名}.srt`（如 `数字测试.srt`）
- **时间戳**：float 秒，负值 clamp 到 0.0
- **标点规范化**：中文语境使用全角标点

## 六、已知问题与改进方向

### 6.1 已知问题

| 编号 | 严重度 | 问题 | 位置 |
|------|--------|------|------|
| I1 | Important | 数字序列超过 max_chars 时强制单行，可能突破限制 | export.py:346-364 |
| I2 | Important | Aligner 可见字符匹配可能错配（ASR 与对齐文本微小差异） | mlx_qwen_align.py:160-178 |
| I3 | Important | VTT 导出重复了 `_smart_split` 调用逻辑 | export.py:769-770 |
| I4 | Important | `_SPLIT_WORD_PATTERNS` 硬编码覆盖不足（约 20 个词对） | export.py:107-119 |
| I6 | Important | Pipeline 从不调用 `run_final_exports`（只有 CLI export 子命令调用） | pipeline.py:163 |
| M1 | Minor | `_CONJ_STARTERS` 已从 export.py 移除导入（不再使用） | — |
| M2 | Minor | `_filter_words_to_text` fallback 逻辑可能过于宽松 | export.py:185-191 |
| M3 | Minor | `_TRAILING_WORDS` 中 "它能""它还" 等粒度存疑 | export.py:34 |

### 6.2 未来拓展方向

1. **分词库替代硬编码**
   - 当前 `_SPLIT_WORD_PATTERNS` 只有约 20 个词对
   - 可考虑引入轻量分词库（如 `pkuseg` 或 jieba）做运行时判断
   - 权衡：引入依赖 vs 覆盖率提升

2. **统一导出逻辑**
   - 将 `_inject_punct` + `_smart_split` + ITN + 标点处理提取为 `render_subtitle_lines()` 函数
   - SRT/VTT 共用，避免 I3 的重复问题

3. **数字序列保护上界**
   - 当数字序列超过 `max_chars * 1.5` 时，允许在序列内部拆分
   - 宁可拆数字也不让字幕行过长影响可读性

4. **Aligner 错配检测**
   - 增加 sanity check：如果分配给某句子的可见字符数与句子文本的可见字符数差值超过阈值（如 2），则回退到句子级时间戳

5. **自适应断句参数**
   - 根据语速自动调整 `pause_threshold`（当前固定 0.2 秒）
   - 根据内容类型（演讲/对话/解说）调整断句策略

6. **跨行断词模式扩展**
   - 当前 `_SPLIT_WORD_PATTERNS` 只覆盖少量高频词
   - 可通过统计分析 ASR 输出，自动发现高频跨行断词模式

## 七、测试覆盖

| 测试文件 | 测试数 | 覆盖范围 |
|----------|--------|----------|
| test_smart_split.py | 595 行 | 基本断句、停顿断句、宽度限制、数字保护、尾虚词剥离、碎片合并 |
| test_phrases.py | 295 行 | 的/得/地 结构、关联词对、语气词标记 |
| test_clauses.py | 72 行 | 句末标点、逗号、停顿、连词、语气词边界 |
| test_itn.py | 79 行 | 全量级数字转换、概数保护、比值转换、小数点保护 |
| test_export.py | 277 行 | SRT/ASS/TXT 导出、max_chars 限制、ITN 集成 |
| test_no_text_loss.py | — | 核心约束：绝不丢字 |

**关键测试：**
- `test_no_text_loss`：验证断句后所有字都保留，无丢失
- `test_smart_split_max_chars_strict`：验证严格 max_chars 限制
- `test_smart_split_trailing_words`：验证尾虚词剥离 + pending_prefix

## 八、关键文件索引

| 文件 | 职责 |
|------|------|
| `src/subtap/core/phrases.py` | 短语边界标记（的/得/地、关联词对、语气词） |
| `src/subtap/core/clauses.py` | 小句边界识别（6 级断句点评分） |
| `src/subtap/core/export.py` | 断句引擎 + 导出（_smart_split + SRTExporter） |
| `src/subtap/core/itn.py` | 中文数字→阿拉伯数字转换 |
| `src/subtap/schemas/config.py` | 配置模型（max_chars / min_chars） |
| `src/subtap/cli.py` | CLI 入口（--max-chars / --min-chars） |
| `src/subtap/core/pipeline.py` | Pipeline 编排（_stage_export） |

## 九、设计决策记录

1. **为什么 ITN 在渲染阶段应用？**
   - 避免 ITN 转换后的阿拉伯数字长度变化影响断句判断
   - 例如 "六千四百九十九"（6 字）→ "6499"（4 字），如果在断句阶段转换，max_chars 计算会出错

2. **为什么用 pending_prefix 而不是直接保留尾虚词？**
   - 尾虚词放在行尾会破坏字幕阅读体验（"但是"、"因为" 不应出现在行尾）
   - pending_prefix 机制将尾虚词移到下一行行首，语义更自然

3. **为什么最终 flush 跳过 _flush_line？**
   - 防止数据丢失：如果最后一行只有尾虚词，_flush_line 会剥离并存入 pending_prefix，但没有下一行来消费它
   - 直接 append 保证所有字都输出

4. **为什么数字序列整体跳过？**
   - 数字序列（如 "二零二五"）内部不应被断句打断
   - 整体跳过避免在数字中间插入断句

以上，爹。🫡
