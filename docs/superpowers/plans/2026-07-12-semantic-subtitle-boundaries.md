# 语义优先字幕断句实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 统一字幕长度配置，并确保句末标点与带停顿的完整短句优先于最短字数合并规则。

**架构：** `OutputConfig.max_chars/min_chars` 作为 segment 与 export 的唯一阈值来源。初次分句接收显式参数；最终导出按单个 `AlignedSegment` 完成碎片整理，禁止跨句末边界合并；同一句内部仅在逗号边界存在明显停顿时保留短尾句。

**技术栈：** Python 3.14、Pydantic、pytest、现有 `_smart_split_v2`、jieba、word timestamps。

---

## 文件结构

- 修改 `src/subtap/core/segmentation.py`：移除固定阈值依赖，接收显式 `max_chars/min_chars`。
- 修改 `src/subtap/core/segment.py`：从 workspace config 读取并传递唯一阈值。
- 修改 `src/subtap/core/export.py`：保护句末硬边界与逗号停顿短句。
- 修改 `src/subtap/schemas/config.py`：增加 `min_chars <= max_chars` 的组合校验。
- 修改 `tests/test_segment.py`：验证自定义阈值进入初次分句。
- 修改 `tests/test_smart_split_v2.py`：验证三个用户反馈场景和普通短碎片行为。
- 修改 `tests/test_cli.py`：验证非法阈值快速失败。

### 任务 1：让一组阈值贯穿初次分句

**文件：**
- 修改：`src/subtap/core/segmentation.py`
- 修改：`src/subtap/core/segment.py`
- 测试：`tests/test_segment.py`

- [ ] **步骤 1：编写失败的配置传递测试**

```python
def test_run_segment_uses_output_character_limits(test_config, tmp_path, monkeypatch):
    test_config.output.max_chars = 18
    test_config.output.min_chars = 6
    captured = {}

    def fake_segment(segments, chunk_start, chunk_end, language="zh", *, max_chars, min_chars):
        captured.update(max_chars=max_chars, min_chars=min_chars)
        return []

    monkeypatch.setattr("subtap.core.segment.segment_clean_segments", fake_segment)
    # 使用现有 Workspace fixture 写入 cleaned/chunks 后调用 run_segment。
    assert captured == {"max_chars": 18, "min_chars": 6}
```

- [ ] **步骤 2：运行测试验证失败**

运行：`uv run pytest -q tests/test_segment.py::test_run_segment_uses_output_character_limits`

预期：FAIL，`segment_clean_segments` 尚未收到 `max_chars/min_chars`。

- [ ] **步骤 3：实现显式参数传递**

```python
def segment_clean_segments(
    segments: list[RawCleanSegment],
    chunk_start: float = 0.0,
    chunk_end: float = 1.0,
    language: str = "zh",
    *,
    max_chars: int = 25,
    min_chars: int = 10,
) -> list[SentenceSegment]:
    ...
```

将 `_split_sentences_zh`、`_split_at_comma` 的 `_MAX_CHARS/_MIN_CHARS` 读取改为显式参数，并在 `run_segment` 两个调用分支传入：

```python
max_chars=workspace.config.output.max_chars,
min_chars=workspace.config.output.min_chars,
```

- [ ] **步骤 4：验证初次分句测试**

运行：`uv run pytest -q tests/test_segment.py tests/test_segment_chunk_boundaries.py`

预期：全部 PASS。

- [ ] **步骤 5：提交**

```bash
git add src/subtap/core/segmentation.py src/subtap/core/segment.py tests/test_segment.py
git commit -m "fix: 统一初次分句字符阈值"
```

### 任务 2：保护句末硬边界

**文件：**
- 修改：`src/subtap/core/export.py:1028-1040`
- 测试：`tests/test_smart_split_v2.py`

- [ ] **步骤 1：编写失败的公开导出测试**

```python
def test_export_never_merges_across_sentence_segments(tmp_path):
    segments = [
        aligned("这台相机从2025年8月发布到今天，一直是一机难求的状态。"),
        aligned("它叫做理光GR4。"),
    ]
    text_lines = render_srt_text(segments, max_chars=25, min_chars=10)
    assert text_lines == [
        "这台相机从2025年8月发布到今天",
        "一直是一机难求的状态",
        "它叫做理光GR4",
    ]
```

- [ ] **步骤 2：运行测试验证失败**

运行：`uv run pytest -q tests/test_smart_split_v2.py::test_export_never_merges_across_sentence_segments`

预期：FAIL，后两句当前被跨 `AlignedSegment` 合并。

- [ ] **步骤 3：限制后处理边界**

在 `SRTExporter.render` 中逐个 segment 完成 `_post_process_fragments`，再追加到总列表：

```python
for seg in sorted_segs:
    sub_lines = _process_segment(seg, self.max_chars, self.min_chars)
    all_subs.extend(_post_process_fragments(sub_lines, self.max_chars, self.min_chars))
merged_subs = all_subs
```

这样保留现有碎片修复，但不允许它跨原始句末边界工作。

- [ ] **步骤 4：验证硬边界测试**

运行：`uv run pytest -q tests/test_smart_split_v2.py tests/test_export.py`

预期：全部 PASS。

- [ ] **步骤 5：提交**

```bash
git add src/subtap/core/export.py tests/test_smart_split_v2.py
git commit -m "fix: 禁止字幕后处理跨句合并"
```

### 任务 3：保留带停顿的逗号短尾句

**文件：**
- 修改：`src/subtap/core/export.py:832-887`
- 测试：`tests/test_smart_split_v2.py`

- [ ] **步骤 1：编写两个失败的真实行为测试**

```python
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("它实际市场售价都已经到万元了，很难原价买到。", ["它实际市场售价都已经到万元了", "很难原价买到"]),
        ("但GR4又加了钱以后还是被抢爆，真的有点看不懂。", ["但GR4又加了钱以后还是被抢爆", "真的有点看不懂"]),
    ],
)
def test_export_keeps_short_clause_after_comma_pause(text, expected):
    words = timed_words(text, pause_after="，", pause_sec=0.3)
    assert split_text(words, text, max_chars=25, min_chars=10) == expected
```

同时保留反例：逗号后没有明显停顿时，短碎片仍可合并。

- [ ] **步骤 2：运行测试验证失败**

运行：`uv run pytest -q tests/test_smart_split_v2.py -k "short_clause_after_comma_pause or short_clause_without_pause"`

预期：带停顿场景 FAIL，无停顿场景保持 PASS。

- [ ] **步骤 3：实现停顿边界保护**

给 `_merge_short_fragments` 增加 `pause_threshold=0.2`，在把短行并入相邻行前检查：

```python
def _has_pause(left: dict, right: dict, threshold: float) -> bool:
    return right["start_sec"] - left["end_sec"] >= threshold

previous_ends_comma = previous["text"].rstrip().endswith(tuple(_COMMA_PUNCT))
if previous_ends_comma and _has_pause(previous, current, pause_threshold):
    preserve_current = True
```

只保护逗号加真实停顿的短句，不添加中文连接词词表。

- [ ] **步骤 4：验证断句规则**

运行：`uv run pytest -q tests/test_smart_split_v2.py tests/test_srt_punctuation_split.py tests/test_export.py`

预期：全部 PASS。

- [ ] **步骤 5：提交**

```bash
git add src/subtap/core/export.py tests/test_smart_split_v2.py
git commit -m "fix: 保留逗号停顿后的完整短句"
```

### 任务 4：阈值组合快速失败

**文件：**
- 修改：`src/subtap/schemas/config.py:125-150`
- 测试：`tests/test_cli.py`

- [ ] **步骤 1：编写失败测试**

```python
def test_output_config_rejects_min_chars_above_max_chars():
    with pytest.raises(ValidationError):
        OutputConfig(max_chars=10, min_chars=11)
```

- [ ] **步骤 2：运行测试验证失败**

运行：`uv run pytest -q tests/test_cli.py::test_output_config_rejects_min_chars_above_max_chars`

预期：FAIL，当前字段范围允许该组合。

- [ ] **步骤 3：增加 Pydantic 组合校验**

```python
@model_validator(mode="after")
def validate_character_limits(self):
    if self.min_chars > self.max_chars:
        raise ValueError("min_chars 不能大于 max_chars")
    return self
```

- [ ] **步骤 4：验证配置与 CLI**

运行：`uv run pytest -q tests/test_cli.py tests/test_config.py`

预期：全部 PASS。

- [ ] **步骤 5：提交**

```bash
git add src/subtap/schemas/config.py tests/test_cli.py
git commit -m "fix: 校验字幕字符阈值组合"
```

### 任务 5：完整验证、真实素材 review 与代码审查

**文件：**
- 更新：`graphify-out/`（由 `graphify update .` 自动维护）
- 产物：`/Users/qunqing/Downloads/ASR-SRT测试音频/subtap-semantic-boundaries-final/`

- [ ] **步骤 1：运行全量测试**

运行：`uv run pytest -q`

预期：全部测试通过，仅保留已知 skip/warning。

- [ ] **步骤 2：更新代码图**

运行：`graphify update .`

预期：AST 更新成功。

- [ ] **步骤 3：完整离线复跑**

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 uv run subtap run \
  '/Users/qunqing/Downloads/ASR-SRT测试音频/高质量中文语音.mp3' \
  --mode quality --enhance local --local-only --subtitle-language zh \
  --max-chars 25 --min-chars 10 \
  --work-dir '/Users/qunqing/Downloads/ASR-SRT测试音频/subtap-semantic-boundaries-final/work' \
  --output-dir '/Users/qunqing/Downloads/ASR-SRT测试音频/subtap-semantic-boundaries-final/output'
```

预期：pipeline 成功，模型为 1.7B q8。

- [ ] **步骤 4：审阅真实字幕**

验证三处目标文本与规格一致；验证字符守恒、词语不拆断、时间戳单调；单独记录热词误替换与英文时间重叠，不在本次 diff 中修复。

- [ ] **步骤 5：两轴 review**

以实现前提交为固定点运行 `/code-review`：Standards 检查 AGENTS.md 与 smell baseline；Spec 检查 `docs/superpowers/specs/2026-07-12-semantic-subtitle-boundaries-design.md`。

- [ ] **步骤 6：最终提交**

仅在 review 无未解决问题且工作树干净时提交剩余修正，中文提交正文包含问题、思路与复现路径。
