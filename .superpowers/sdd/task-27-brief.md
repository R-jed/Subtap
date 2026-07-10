# Task 27: 提取 batch_cli.py

## 目标
将 cli.py 中的批量处理命令提取到独立模块 `src/subtap/cli/batch_cli.py`。

## 需要提取的函数
1. `batch_transcribe` — 批量转录
2. `compose_subtitle` — 字幕合成
3. `batch_compose_subtitle` — 批量字幕合成

## 依赖
- 无独立子命令组，这些函数直接注册到 `app`
- `_handle_error` — 错误处理函数（保留在 cli/__init__.py）

## 约束
1. 保持 `subtap batch-transcribe/compose/batch-compose` 命令路径不变
2. 保持所有函数签名和帮助文本不变
3. 保持延迟导入模式
4. 不修改任何现有测试

## 验证
- `pytest tests/ -k "batch" -v` 通过
- `subtap batch-transcribe --help` 正常工作
- `subtap compose --help` 正常工作
- `subtap batch-compose --help` 正常工作
