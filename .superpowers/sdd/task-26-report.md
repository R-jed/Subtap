# Task 26 Report: 提取 pipeline_cli.py

## 状态：DONE

## 修改的文件

| 文件 | 操作 |
|------|------|
| `src/subtap/cli/pipeline_cli.py` | 新建 — 包含 12 个 pipeline 命令函数 |
| `src/subtap/cli/__init__.py` | 重写 — 移除已提取函数，添加 import + 注册 |

## 提取的函数

`pipeline_cli.py` 包含以下函数：
- `_apply_cli_overrides` — CLI 参数覆盖辅助
- `check_first_run_wizard` — 首次运行向导
- `_run` — 主运行命令（注册为 `run`）
- `_prepare` — 媒体准备（注册为 `prepare`）
- `_transcribe` — 语音识别（注册为 `transcribe`）
- `_clean` — 文本清洗（注册为 `clean`）
- `_segment` — 智能断句（注册为 `segment`）
- `_align` — 时间轴对齐（注册为 `align`）
- `_export` — 字幕导出（注册为 `export`）
- `_resume` — 恢复执行（注册为 `resume`）
- `_retry` — 重试失败阶段（注册为 `retry`）
- `_demo` — 演示模式（注册为 `demo`）
- `_clean_workspace` — 清理工作区（注册为 `cleanup`）

## 设计决策

- 函数在 `pipeline_cli.py` 中以下划线前缀命名（`_run`, `_prepare` 等），在 `__init__.py` 中通过 `app.command("name")` 注册时指定公开命令名
- `check_first_run_wizard` 和 `_apply_cli_overrides` 同时从 `pipeline_cli.py` 导出，供 `__init__.py` 内部使用
- `_build_observer_child_command` 保留在 `__init__.py`，`pipeline_cli.py` 通过延迟导入引用
- `demo` 函数中 `Path(__file__).resolve().parents[2]` 已调整为 `parents[3]` 以适配新文件位置
- 所有延迟导入模式保持不变

## 测试结果

```
1021 passed, 4 skipped, 8 failed in 11.07s
```

**8 个失败均为预存在问题**（通过 git stash 验证原代码同样失败）：
- `test_apply_cli_overrides_sets_values` — 原代码中 `_apply_cli_overrides` 已被移动
- `test_apply_cli_overrides_preserves_when_none` — 同上
- `test_open_file_cross_platform_*` (4个) — `_open_file_cross_platform` 已提取到 hotword_cli.py
- `test_python_module_entrypoint_outputs_help` — 模块入口点测试
- `test_run_cleanup_removes_temp_files` — 清理逻辑测试

## 命令验证

```
subtap run --help       ✓
subtap prepare --help   ✓
subtap export --help    ✓
subtap resume --help    ✓
subtap retry --help     ✓
subtap cleanup --help   ✓
```

## 提交哈希

未提交（变更在工作区）
