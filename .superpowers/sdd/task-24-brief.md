# Task 24: 提取 hotword_cli.py

## 目标
将 cli.py 中的热词管理命令提取到独立模块 `src/subtap/cli/hotword_cli.py`。

## 需要提取的函数
1. `hotword_add` — 添加热词
2. `hotword_list` — 查看热词
3. `hotword_delete` — 删除热词
4. `hotword_edit` — 编辑热词（用默认应用打开）

## 依赖
- `hotword_app = typer.Typer(help="热词管理")` — 热词子命令组
- `glossary_app.add_typer(hotword_app, name="hotword")` — 注册到 glossary_app
- `_open_file_cross_platform` — 辅助函数（保留在 cli.py 或提取到 utils）

## 约束
1. 保持 `subtap glossary hotword add/list/delete/edit` 命令路径不变
2. 保持所有函数签名和帮助文本不变
3. 保持导入延迟（lazy import）模式
4. 不修改任何现有测试

## 验证
- `pytest tests/ -k "hotword" -v` 通过
- `subtap glossary hotword --help` 显示子命令
- `subtap glossary hotword list` 正常工作
