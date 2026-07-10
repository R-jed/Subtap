# Task 28: 提取 script_cli.py

## 目标
将 cli.py 中的文稿匹配命令提取到独立模块 `src/subtap/cli/script_cli.py`。

## 需要提取的函数
1. `script_match` — 文稿匹配
2. `script_format` — 文稿格式化

## 依赖
- `script_app = typer.Typer(help="文稿匹配")` — 文稿子命令组
- `app.add_typer(script_app, name="script")` — 注册到 app

## 约束
1. 保持 `subtap script match/format` 命令路径不变
2. 保持所有函数签名和帮助文本不变
3. 保持延迟导入模式
4. 不修改任何现有测试

## 验证
- `pytest tests/ -k "script" -v` 通过
- `subtap script --help` 显示子命令
- `subtap script match --help` 正常工作
