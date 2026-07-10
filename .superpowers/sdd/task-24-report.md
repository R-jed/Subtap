# Task 24: 提取 hotword_cli.py — 报告

## 状态
DONE

## 修改的文件列表

| 文件 | 操作 |
|------|------|
| `src/subtap/cli/hotword_cli.py` | 新建 — 热词管理子命令组 |
| `src/subtap/cli/__init__.py` | 新建 — 原 `cli.py` 的 `app` 定义和入口逻辑 |
| `src/subtap/cli.py` | 删除 — 内容迁移至 `cli/__init__.py` |

### 关键说明

由于 `subtap.cli` 既是包名又是模块名，创建 `src/subtap/cli/` 目录后，原 `cli.py` 文件会与 `cli/__init__.py` 冲突。解决方案是将 `cli.py` 的全部内容迁移到 `cli/__init__.py`，删除原文件。

## 提取内容

- `hotword_app` Typer 实例定义
- `hotword_add` / `hotword_list` / `hotword_delete` / `hotword_edit` 四个命令函数
- `_open_file_cross_platform` 辅助函数
- 命令路径保持不变：`subtap glossary hotword add/list/delete/edit`

## 测试结果

```
57 passed, 4 skipped, 972 deselected, 1 warning
```

## 验证

- `subtap glossary hotword --help` 输出正确的子命令列表
- 全部 hotword 相关测试通过
