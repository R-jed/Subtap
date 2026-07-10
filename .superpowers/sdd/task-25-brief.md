# Task 25: 提取 models_cli.py

## 目标
将 cli.py 中的模型管理命令提取到独立模块 `src/subtap/cli/models_cli.py`。

## 需要提取的函数
1. `models_status` — 模型状态检查
2. `models_install` — 模型安装
3. `models_verify` — 模型验证
4. `models_list` — 列出可用模型
5. `models_remove` — 移除模型

## 依赖
- `models_app = typer.Typer(help="模型管理")` — 模型子命令组
- `app.add_typer(models_app, name="models")` — 注册到 app
- `_handle_error` — 错误处理函数（保留在 cli/__init__.py）

## 约束
1. 保持 `subtap models status/install/verify/list/remove` 命令路径不变
2. 保持所有函数签名和帮助文本不变
3. 保持延迟导入模式
4. 不修改任何现有测试

## 验证
- `pytest tests/ -k "models" -v` 通过
- `subtap models --help` 显示子命令
- `subtap models list` 正常工作
