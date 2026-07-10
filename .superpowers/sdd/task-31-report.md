# Task 31 Report: 提取 setup 命令到独立模块

## 状态: DONE

## 修改的文件
- `src/subtap/cli/setup_cli.py` — 新建，包含 `setup` 函数（原 `__init__.py` 中的完整实现）
- `src/subtap/cli/__init__.py` — 删除内联 `setup` 定义，改为 `from subtap.cli.setup_cli import setup` + `app.command("setup")(setup)` 注册

## 测试结果
- `pytest tests/ -k "setup"` — **35 passed, 4 skipped**
- `setup --help` 输出正确，所有选项参数保留完整

## 提交哈希
`da0a3e2b` — `refactor(cli): 提取 setup 命令到独立模块 setup_cli.py`
