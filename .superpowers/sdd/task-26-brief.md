# Task 26: 提取 pipeline_cli.py

## 目标
将 cli.py 中的 pipeline 核心命令提取到独立模块 `src/subtap/cli/pipeline_cli.py`。

## 需要提取的函数
1. `run` — 主运行命令
2. `prepare` — 媒体准备
3. `transcribe` — 语音识别
4. `clean` — 文本清洗
5. `segment` — 字幕分段
6. `align` — 强制对齐
7. `export` — 字幕导出
8. `resume` — 恢复执行
9. `retry` — 重试失败阶段
10. `demo` — 演示模式
11. `clean_workspace` — 清理工作区

## 依赖
- `_apply_cli_overrides` — CLI 参数覆盖函数
- `_handle_error` — 错误处理函数
- `_open_file_cross_platform` — 文件打开函数（已提取到 hotword_cli.py）

## 约束
1. 保持所有命令路径不变
2. 保持所有函数签名和帮助文本不变
3. 保持延迟导入模式
4. 不修改任何现有测试

## 验证
- `pytest tests/ -v` 通过
- `subtap run --help` 正常工作
- `subtap prepare --help` 正常工作
- `subtap export --help` 正常工作
