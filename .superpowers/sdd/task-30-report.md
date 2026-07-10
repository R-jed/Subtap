# Task 30: 提取 doctor 命令到独立模块

## 状态: DONE

## 完成内容

1. **创建新模块**: `src/subtap/cli/doctor_cli.py`
   - 包含 `doctor` 函数（系统诊断命令）
   - 包含 `_doctor_workspace` 函数（工作区状态检查）

2. **修改主 CLI 文件**: `src/subtap/cli/__init__.py`
   - 删除已提取的 `doctor` 和 `_doctor_workspace` 函数
   - 添加从 `subtap.cli.doctor_cli` 导入 `doctor`
   - 注册命令到 app: `app.command("doctor")(doctor)`

## 修改的文件

- `src/subtap/cli/doctor_cli.py` (新建)
- `src/subtap/cli/__init__.py` (修改)

## 测试结果

```
tests/test_cli.py::test_doctor PASSED
tests/test_cli.py::test_doctor_workspace PASSED
tests/test_cli.py::test_doctor_json_outputs_machine_readable_status PASSED
tests/test_cli.py::test_doctor_enhanced_checks PASSED
tests/test_cli.py::test_doctor_release_fails_when_models_missing PASSED
tests/test_doctor_model_panel.py::test_doctor_json_reports_models_quantization_and_residency PASSED
tests/test_doctor_panel.py::test_doctor_panel_reports_runtime_privacy_and_output PASSED

7 passed, 4 skipped, 1022 deselected
```

## 验证

- CLI 模块导入成功
- doctor 命令正确注册到 app
- 所有 doctor 相关测试通过
