# Task 33 Report: 修复代码质量小问题

## 状态: DONE_WITH_CONCERNS

## 修改的文件

| 文件 | 修改内容 |
|------|---------|
| `src/subtap/core/export.py` | 1/3/5: 重构 `_is_incomplete_word` 为 dataclass、提升常量、清理无用导入 |
| `src/subtap/cli/pipeline_cli.py` | 2: 提取 `_show_srt_preview` 函数 |

## 修复详情

### 1. `_is_incomplete_word` 参数过多 -> DONE
- 引入 `IncompleteWordQuery` dataclass，将 4 个参数封装为字段
- 原函数改为 `is_incomplete()` 方法
- 调用处 `_fix_split_words` 已更新为 `IncompleteWordQuery(...).is_incomplete()`
- 行数：4 -> 2（方法内部逻辑不变）

### 2. `_demo` 函数过长 -> DONE
- 提取 SRT 展示逻辑为独立函数 `_show_srt_preview(output_dir)`
- `_demo` 从 58 行减至约 45 行

### 3. 向后兼容别名 `_ALL_PUNCT_RE` -> DONE (部分)
- `_ALL_PUNCT_RE` 已删除（无任何调用者）
- `_normalize_punct`、`_remove_cjk_spaces`、`_strip_punct` **保留** -- 它们在模块内部有 13 处调用，不能删除
- 删除了未使用的 `ALL_PUNCT_RE` 导入

### 4. `hotword_edit` 重复导入 -> N/A
- 检查发现 `hotword_cli.py` 中只有顶部 1 处 `import subprocess`，函数内无重复导入
- 该问题在当前代码中不存在

### 5. 常量定义提升 -> DONE
- `_SENT_END`、`_NUM_CHARS`、`_COMMA_PUNCT` 从 3 个函数内部提升为模块级 `frozenset` 常量
- 涉及函数：`_greedy_split`、`_smart_split_v2`、`_merge_short_fragments`
- 使用 `frozenset` 替代 `set`（不可变，语义更清晰）

## Concerns

- **别名清理范围受限**：`_strip_punct` 等别名在模块内广泛使用（13 处），若要彻底清理需全量替换为直接调用 `strip_punct()`，涉及大量行改动，不在本次范围内
- **Fix #4 不适用**：task brief 描述的重复导入问题在当前代码中不存在

## 测试结果

- `tests/test_export.py`: 45/45 PASSED
- `tests/test_smart_split.py`: 11/11 PASSED
- `tests/test_smart_split_v2.py`: 35/35 PASSED
- `tests/test_cli.py`: 7 个预存失败（import path 问题，非本次修改引入）

## 提交哈希

(待提交)
