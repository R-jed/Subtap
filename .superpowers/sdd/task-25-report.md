# Task 25: 提取 models_cli.py — 完成报告

## 状态
DONE

## 修改的文件
| 文件 | 操作 |
|------|------|
| `src/subtap/cli/models_cli.py` | 新建 — 包含 `models_app` 及 5 个子命令（status/install/verify/list/remove） |
| `src/subtap/cli/__init__.py` | 删除内联 models 代码块，替换为 `from subtap.cli.models_cli import models_app` |

## 提取内容
- `models_app = typer.Typer(help="模型管理", no_args_is_help=True)`
- `models_status` — 查看模型状态
- `models_install` — 安装模型（支持 rich 进度条）
- `models_verify` — 验证模型完整性
- `models_list` — 列出可用模型
- `models_remove` — 移除模型
- `_handle_error` — 错误处理函数（模块内独立副本）

## 验证结果
- `pytest tests/ -k "models" -v` — 47 passed
- `subtap models --help` — 正常显示 5 个子命令
- 命令路径不变：`subtap models status/install/verify/list/remove`

## 基线 commit
cdca4361
