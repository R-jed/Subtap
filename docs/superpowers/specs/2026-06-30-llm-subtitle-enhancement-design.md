# 第三方 LLM 字幕增强与翻译设计

## 目标

接入 OpenAI-compatible 第三方 LLM API，为 Subtap 增加字幕质检纠错、AI 热词替换、翻译和双语字幕导出能力。

第一期只支持 OpenAI-compatible `/chat/completions`。不实现原生 Anthropic/Gemini，不引入 LiteLLM，不做 API fallback，不做 UI 编辑器。

## 背景与约束

Subtap 当前主流程是：

```text
prepare -> chunk -> asr -> clean -> segment -> align -> hotword -> export
```

本设计调整为：

```text
prepare -> chunk -> asr
  -> clean       # 本地清洗、确定性术语、API 质检、API 修复、API 热词
  -> segment     # 基于增强后的源语言文本断句
  -> align       # 基于增强后的源语言文本对齐
  -> translate   # align 后翻译
  -> export      # 源语言 / 目标语言 / 双语导出
```

核心边界：

- ASR 不发送到第三方音频 API。
- 第三方 API 只接收字幕文本，不接收音频。
- 翻译输入必须是纠错和热词替换后的源语言字幕，不是原始 ASR 文本。
- 时间轴只来自源语言对齐结果，译文不参与 align。
- API 失败不静默回退原文，必须失败并暴露错误。
- `--local-only` 禁止所有外部 LLM API 调用。
- 第一阶段后不再运行现有 align 后 `hotword` 阶段，避免同一热词在 clean 阶段和 align 后被重复替换。

## 外部方案参考

参考方向：

- haoone-app：功能边界参考，包括 AI 校正、AI 热词、翻译、双语字幕。
- pyVideoTrans / VideoCaptioner：字幕翻译和 LLM 校正流程参考。
- LLM-Subtrans / subtitle-translator：SRT 翻译和多格式校验参考。

采纳项：

- 分块处理字幕文本。
- 翻译阶段以 SRT 为输入输出，便于保留序号、时间轴、分段结构。
- 对 LLM 输出做结构校验。

不采纳项：

- 不复制 GPL 项目代码。
- 不引入大而全 provider 网关。
- 不做独立编辑器。

## 数据流

原始 ASR 输出：

```text
asr.jsonl: ASRSegment.text
```

清洗增强输出：

```text
cleaned.jsonl: CleanSegment.cleaned_text
```

`cleaned_text` 包含：

1. 本地 unicode / 空白规范化。
2. 确定性 glossary 替换。
3. API 质检筛选后的可疑句修复。
4. API 上下文热词替换。

对齐输出：

```text
aligned.jsonl: AlignedSegment.text
```

`AlignedSegment.text` 必须来自增强后的 `cleaned_text`。

翻译输出：

第一期直接在 `AlignedSegment` 增加：

```python
translated_text: str | None = None
```

翻译阶段固定使用：

```text
translation_source = aligned.text
```

不允许使用：

```text
ASRSegment.text
CleanSegment.original_text
```

## CLI 行为

保留现有入口：

```bash
subtap run input.mp3 --enhance api
subtap run input.mp3 --enhance api --translate-to en
subtap run input.mp3 --enhance api --translate-to en --bilingual source-first
subtap run input.mp3 --enhance api --translate-to en --bilingual target-first
```

参数语义：

- `--enhance off`：不调用 LLM；只做必要本地清洗。
- `--enhance local`：只做本地清洗、本地 glossary、本地热词；不调用 LLM。
- `--enhance api`：调用 OpenAI-compatible API 做质检筛选、可疑句修复、AI 热词。
- `--translate-to <lang>`：调用 OpenAI-compatible API 翻译最终源语言 SRT。
- `--bilingual off`：有翻译时输出目标语言字幕。
- `--bilingual source-first`：双语字幕源语言在上，译文在下。
- `--bilingual target-first`：双语字幕译文在上，源语言在下。
- `--local-only`：禁止 `--enhance api` 和 `--translate-to`。

非法组合：

- `--local-only --enhance api`：失败。
- `--local-only --translate-to en`：失败。
- `--bilingual source-first` 但没有 `--translate-to`：失败。
- `--bilingual target-first` 但没有 `--translate-to`：失败。

## 配置

复用现有 `remote_api`：

```yaml
remote_api:
  provider: openai-compatible
  base_url: https://api.openai.com/v1
  api_key_env: SUBTAP_API_KEY
  model: gpt-4o-mini
  timeout_sec: 60
```

第一期不新增 `translation` 配置。翻译目标语言由 CLI `--translate-to` 控制。

`--enhance api` 和 `--translate-to` 必须强制使用 `remote_api` 配置创建 OpenAI-compatible 客户端。不能继续沿用 `CleanConfig.backend` 的默认 `ollama:qwen3-coder`，否则用户选择 API 增强时会误走本地 Ollama 或配置语义不一致。

`CleanConfig.backend` 在第一期只作为显式覆盖项保留：

- 未传显式 LLM 后端时，`--enhance api` 使用 `remote_api.model`。
- 传入 `openai:<model>` 时，使用该 model 覆盖 `remote_api.model`。
- `--enhance off/local` 不读取 `CleanConfig.backend` 发起 LLM 请求。

## API 任务

### 1. 质检筛选

按用户确认的 prompt 使用：

```text
你是一个字幕质检助，你的任务：

1. 阅读给定的字幕 segments。

2. 只返回“可能有问题”的句子：

- 语义错误

- 表达不通顺

- 专业名词 / 品牌 / 产品名可能识别错

3. 正常句子不要返回。

4. 不要改写原句，不要解释原因。

5. 只输出 JSON，格式必须严格为：

{"segments":[{"i":0}]}

6. 每个输入项包含：
- i: 原始索引
- t: 字幕文本

7. 只返回原始输入里的索引 i。

8. 如果没有可疑句子，返回 {"segments":[]}
```

输入：

```json
{"segments":[{"i":0,"t":"字幕文本"}]}
```

输出：

```json
{"segments":[{"i":0}]}
```

校验：

- 必须是合法 JSON。
- `segments` 必须是列表。
- 每个 `i` 必须来自输入。
- 不允许重复 `i`。

`{"segments":[]}` 表示没有可疑句，跳过修复。

### 2. 可疑句修复

质检 prompt 不返回修正文案，因此增加修复 prompt：

```text
你是一个字幕纠错助手。请只修正给定字幕中的明显错误。

规则：
1. 只修正语义错误、表达不通顺、专业名词 / 品牌 / 产品名识别错误。
2. 不要翻译。
3. 不要总结、扩写或删除信息。
4. 保持原句意思和字幕口语风格。
5. 只输出 JSON，格式严格为：
{"segments":[{"i":0,"t":"修正后的字幕文本"}]}
6. 每个输出 i 必须来自输入。
7. 不需要修改的句子不要返回。

待处理内容：
{{segments}}
```

校验：

- 必须是合法 JSON。
- 每个输出 `i` 必须来自质检筛选结果。
- `t` 不能为空。
- 未返回的可疑句保持质检前文本。

### 3. AI 热词替换

输入使用修复后的源语言文本和现有热词表。

规则：

- 只在上下文明确指向热词时替换。
- 不确定时保持原文。
- 不翻译。
- 不合并、删除、新增字幕行。

输出格式：

```json
{"segments":[{"i":0,"t":"替换后的字幕文本"}]}
```

校验同修复任务。

### 4. SRT 翻译

按用户确认的 prompt 使用：

```text
你是一名经验丰富的影视字幕翻译专家。请将下面的 SRT 字幕翻译为{{target_language}}。

翻译目标：
1. 保留原字幕的序号、时间轴、分段结构与换行结构，不要新增或删除字幕块。
2. 译文要自然、口语化、准确、简洁，符合真实字幕阅读习惯，而不是生硬直译。
3. 优先传达说话者真实意图、语气与信息重点；有口头语时可自然化处理，但不要无故扩写。
4. 人名、地名、品牌名、产品名、专业术语要结合上下文统一翻译；无法确认时优先保留原文或使用更稳妥写法。
5. 数字、年份、日期、时间、百分比、货币、型号、专有缩写等信息必须准确保留，不要误改。
6. 如果原文有上下句承接关系，请确保译文衔接自然，不要把句意翻断。
7. 每条字幕尽量控制在适合阅读的长度，避免过长、过书面或过于机器化。
8. 不要输出解释、备注、分析、前言、后记，只输出合法的 SRT 内容。

待翻译内容：
{{text}}
```

翻译流程：

```text
aligned.jsonl
-> render temporary source.srt from aligned.text
-> API translate SRT
-> parse translated SRT
-> validate index/time/block count
-> attach translated_text
-> export
```

校验：

- 返回必须是合法 SRT。
- 字幕块数量必须不变。
- 序号必须不变。
- 时间轴必须不变。
- 分段结构必须不变。

## 输出矩阵

| 参数 | final.source.srt | final.srt |
|---|---|---|
| 无翻译 | 不生成 | 源语言字幕 |
| `--translate-to en` | 源语言字幕 | 英文字幕 |
| `--translate-to en --bilingual source-first` | 源语言字幕 | 源语言 + 英文双语 |
| `--translate-to en --bilingual target-first` | 源语言字幕 | 英文 + 源语言双语 |

双语字幕规则：

- 双语只在 export 阶段组合。
- 每个字幕块固定两行。
- `source-first`：第一行源语言，第二行译文。
- `target-first`：第一行译文，第二行源语言。
- 双语字幕不交给 LLM 排版。

## 错误处理

直接失败：

- API key 环境变量缺失。
- `base_url` 缺失。
- 网络请求失败。
- API 返回非 2xx。
- JSON 解析失败。
- 质检返回非法索引。
- 修复返回不存在的索引。
- 修复返回空文本。
- 热词替换返回空文本。
- 翻译返回非法 SRT。
- 翻译返回字幕块数量不一致。
- 翻译返回序号不一致。
- 翻译返回时间轴不一致。

允许继续：

- 质检返回 `{"segments":[]}`。
- AI 热词没有命中。
- 翻译后人名、品牌名、型号与原文相同。

## 文件边界

复用：

- `src/subtap/backends/llm/openai_compat.py`
- `src/subtap/core/clean.py`
- `src/subtap/core/hotword.py`
- `src/subtap/core/export.py`

新增：

- `src/subtap/core/translate.py`

修改：

- `src/subtap/schemas/models.py`
- `src/subtap/core/pipeline.py`
- `src/subtap/ui/tui.py`
- `src/subtap/cli.py`
- `tests/`

暂不扩展：

- `src/subtap/enhancement/*`

原因：当前主 pipeline 使用 `schemas.models.CleanSegment.cleaned_text`，`enhancement` 子系统使用另一套 `CleanSegment.text/start_sec/end_sec`。第一期不继续扩散双模型。

## 测试策略

必须覆盖：

1. `--enhance local` 不触发 API。
2. `--enhance api` 会先调用质检筛选。
3. 质检返回空列表时不调用修复。
4. 质检返回可疑索引时只修复这些索引。
5. 修复结果只覆盖对应 `cleaned_text`。
6. 非法 JSON / 非法索引 / 空文本直接失败。
7. AI 热词替换发生在翻译前。
8. 翻译输入来自增强后的 `aligned.text`，不是原始 ASR。
9. 翻译 SRT 块数量、序号、时间轴必须保持一致。
10. `--translate-to en --bilingual source-first` 输出源语言在上、译文在下。
11. `--translate-to en --bilingual target-first` 输出译文在上、源语言在下。
12. 翻译时额外输出 `final.source.srt`。
13. `--local-only --translate-to en` 阻断。
14. `--local-only --enhance api` 阻断。
15. 未指定 `--translate-to` 时使用 `--bilingual` 直接失败。
16. 双语字幕每个字幕块保持同一序号和时间轴。
17. 观察者 TUI 子进程继续传递 `--translate-to` / `--bilingual`。

## 成功标准

```bash
subtap run input.mp3 --enhance api
```

输出源语言字幕，文本经过本地清洗、质检筛选、可疑句修复和 AI 热词替换。

```bash
subtap run input.mp3 --enhance api --translate-to en
```

输出：

```text
final.source.srt
final.srt
```

其中 `final.source.srt` 是增强后的源语言字幕，`final.srt` 是目标语言字幕。

```bash
subtap run input.mp3 --enhance api --translate-to en --bilingual source-first
```

输出：

```text
final.source.srt
final.srt
```

其中 `final.srt` 是源语言在上、目标语言在下的双语字幕。

## 明确不做

- 不改 ASR。
- 不改 align 模型。
- 不新增 LiteLLM。
- 不新增原生 Anthropic/Gemini。
- 不做 API fallback。
- 不做自动重试。
- 不改 TUI 观察者进程架构。
- 不新增字幕编辑器。
