# Task 33: 修复代码质量小问题

## 目标
修复代码审查报告中的 5 个 Minor/Important 问题。

## 问题列表

### 1. `_is_incomplete_word` 有 4 个参数（L5标准≤2）
- 文件：`src/subtap/core/export.py`
- 当前签名：`_is_incomplete_word(tail, next_start, cross_sentence=False, prev_char="")`
- 建议：使用 dataclass 封装参数

### 2. `_demo` 58 行（超L3标准8行）
- 文件：`src/subtap/cli/pipeline_cli.py`
- 建议：提取 SRT 展示逻辑为独立函数

### 3. 向后兼容别名 `_ALL_PUNCT_RE` 等
- 文件：`src/subtap/core/export.py`
- 行 23-27：`_ALL_PUNCT_RE = ALL_PUNCT_RE` 等
- 建议：删除这些别名（如果有外部调用者则保留）

### 4. `hotword_edit` 重复导入 `subprocess`
- 文件：`src/subtap/cli/hotword_cli.py`
- 建议：删除函数内的重复导入，使用顶部导入

### 5. `_SENT_END` 等定义在函数内
- 文件：`src/subtap/core/export.py`
- `_SENT_END`、`_COMMA_PUNCT`、`_NUM_CHARS` 定义在 `_greedy_split` 函数内
- 建议：提升为模块级常量

## 约束
1. 不修改任何现有测试
2. 保持所有公共 API 不变
3. 每个修复都运行相关测试验证

## 验证
- `pytest tests/test_export.py -v` 通过
- `pytest tests/test_cli.py -k "demo" -v` 通过
