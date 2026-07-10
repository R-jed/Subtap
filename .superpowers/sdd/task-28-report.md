# Task 28: 提取 script_cli.py — 完成报告

## 状态
DONE

## 修改的文件
1. `src/subtap/cli/script_cli.py` — 新建，包含 `script_app`、`script_match`、`script_format`、`_handle_error`
2. `src/subtap/cli/__init__.py` — 新增 `from subtap.cli.script_cli import script_app`，删除 `script_match` 和 `script_format` 函数体

## 测试结果
- `pytest tests/ -k "script" -v`：**54 passed, 994 deselected**
- `script --help`：显示 match / format 两个子命令
- `script match --help`：参数和帮助文本完整

## 提交哈希
未提交（cli/ 目录为 untracked 状态，需由父任务统一提交）
