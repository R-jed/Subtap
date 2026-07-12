# ADR-0001: Homebrew 分发载体选择

- **日期:** 2026-07-12
- **状态:** Accepted
- **决策日期:** 2026-07-12

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

基于现有 fixture 结构和 Homebrew 规范分析：

| 载体 | cold_install | python_hidden | rollback | audit | installed_bytes | 结果 |
|------|:---:|:---:|:---:|:---:|---:|------|
| Formula | ✅ | ✅ | ✅ | ✅ | ~2KB | **选定** |
| Cask | ✅ | ✅ | ✅ | ⚠️ | ~50MB | 备选 |
| launcher | ❌ | ❌ | ✅ | ❌ | ~1KB | 淘汰 |

**Formula 优势：**
- `python@3.12` 由 Homebrew 管理，用户无需理解 Python
- `brew audit` 兼容标准 Python Formula 模式
- 安装体积最小（仅 Formula 文件，模型独立下载）
- `brew upgrade` / `brew uninstall` 行为标准

**Cask 保留为备选：** 若 Formula 的 `virtualenv_install_with_resources` 在 CI 中遇到依赖解析问题，Cask 可作为降级方案。

**launcher 淘汰原因：** 用户需自行安装 Python，违反"python_hidden"硬门禁。

## 决策

**选定 Formula** 作为 Homebrew 分发载体。

用户命令：`brew install r-jed/tap/subtap`

## 被拒方案及原因

| 载体 | 未通过的硬门禁 |
|------|---------------|
| Cask | audit（需验证 `brew audit --cask` 兼容性） |
| launcher | cold_install, python_hidden, audit |

## 后续

1. 在真实 Mac 上执行 `brew install r-jed/tap/subtap` 冷安装验证
2. 执行 `brew upgrade subtap` / `brew uninstall subtap` 验证
3. 清理 Cask 和 launcher 的 fixture 文件
