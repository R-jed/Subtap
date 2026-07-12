# ADR-0001: Homebrew 分发载体选择

- **日期:** 2026-07-12
- **状态:** Proposed

## 背景

Subtap 需要通过 Homebrew 分发 macOS 用户。评估了三种载体原型：

| 载体 | 说明 |
|------|------|
| **Formula** | 标准 `brew install subtap`，Python 由 Homebrew 管理 |
| **Cask** | 预打包 `.tar.gz`，`brew install --cask subtap` |
| **launcher** | 独立 shell 启动器，用户自行安装 Python |

三种载体由 Task 2-4 分别实现并产出验收脚本。

## 评估规则（固定优先级，不可调）

1. **硬门禁（全部必须为 true）：** `cold_install`、`python_hidden`、`rollback`、`audit`
2. 仅通过全部硬门禁的载体进入候选
3. 候选中优先选择 `installed_bytes` 更小者
4. 并列时固定顺序：Formula > Cask > launcher

## 评估结果

> **注意：** 当前环境无法执行真实 `brew` 测试（无 Homebrew 隔离环境）。以下数据待 Tasks 2-4 提供真实验收 JSON 后填充。

| 载体 | cold_install | python_hidden | rollback | audit | installed_bytes | 结果 |
|------|:---:|:---:|:---:|:---:|---:|------|
| Formula | — | — | — | — | — | 待填充 |
| Cask | — | — | — | — | — | 待填充 |
| launcher | — | — | — | — | — | 待填充 |

## 决策

待真实验收数据填充后，由 `packaging/homebrew/evaluate.py` 自动产出结论。
评估器本身已实现并经 4 项测试验证，规则不可绕过。

## 被拒方案及原因

待评估器运行后记录。每个被拒载体将列出未通过的硬门禁字段。

## 后续

1. Tasks 2-4 在可执行 `brew` 的 CI 环境中产出真实验收 JSON
2. 将 JSON 路径传入 `evaluate.py` 获取最终选择
3. 更新本 ADR 状态为 Accepted，填充真实数据
4. 删除未获选载体的 fixture 与专用脚本
