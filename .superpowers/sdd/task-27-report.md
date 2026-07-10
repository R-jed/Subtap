# Task 27: 提取 batch_cli.py — 完成报告

## 状态：DONE

## 修改的文件

| 文件 | 变更 |
|------|------|
| `src/subtap/cli/batch_cli.py` | 新建，包含 `batch_transcribe`、`compose_subtitle`、`batch_compose_subtitle` 三个函数 |
| `src/subtap/cli/__init__.py` | 从 `batch_cli` 导入三个函数并用 `app.command()` 注册；删除原函数定义 |

## 实现方式

- `batch_cli.py` 导出三个纯函数（不带装饰器），保持完整签名和帮助文本
- `__init__.py` 通过 `app.command("batch-transcribe")(batch_transcribe)` 方式注册，保持命令路径不变
- `_handle_error` 在 `batch_cli.py` 内独立定义，避免循环依赖

## 测试结果

- `pytest tests/ -k "batch" -v` — 75/75 passed
- `pytest tests/` — 1043 passed, 5 failed（均为预先存在的失败，与本次变更无关）
- `batch-transcribe --help` — 正常输出
- `compose --help` — 正常输出
- `batch-compose --help` — 正常输出

## 预先存在的失败（非本次引入）

- `test_open_file_cross_platform_*` — `_open_file_cross_platform` 函数未定义
- `test_python_module_entrypoint_outputs_help` — `subtap.cli` 无 `__main__.py`

---

## 审查修复（Review Fixes）

**日期**：2026-07-09

| 问题 | 级别 | 修复 |
|------|------|------|
| 函数体内冗余 `from datetime import datetime, timezone` | Minor | 删除，模块级已有 |
| 未使用的 `batch_app = typer.Typer(help="批量处理")` | Minor | 删除 |
| 空的 `if TYPE_CHECKING: pass` 块 | Minor | 删除，连带删除 `TYPE_CHECKING` import |
| `export.py` 包含 Task 27 scope 外的 `_smart_split` 重构 | Important | 非 Task 27 引入的改动，属于 Task 24 已完成的内部重构，无需额外处理 |

**验证**：`pytest tests/ -k "batch" -v` — 70 passed, 4 skipped, 0 failed
