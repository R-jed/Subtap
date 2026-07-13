# ADR-0001: Homebrew 分发载体选择

- **日期：** 2026-07-12
- **状态：** Proposed

## 背景

Subtap 计划只面向 Apple Silicon macOS，通过 Homebrew 提供安装、升级与卸载。
Formula、Cask 和轻量启动器曾建立原型，但原型和静态分析不能替代真实 Homebrew 验收。

## 固定门禁

候选载体必须全部满足：

1. 全新环境可以安装；
2. 用户不需要管理 Python；
3. `brew audit --strict` 与 `brew test` 通过；
4. 升级与卸载行为正确；
5. 卸载后 `~/.subtap` 用户资料完整保留。

## 当前证据

2026-07-13 已创建公开仓库 `R-jed/homebrew-tap`。标准 Python Formula 随后在官方工具阶段失败：

```text
brew update-python-resources R-jed/tap/subtap
Error: mlx exists on PyPI but lacks a suitable source distribution
```

`v0.1.0rc2` 的 GitHub prerelease、SHA256、构建来源证明和 arm64 wheel smoke 已通过，PyPI 正确跳过。

锁定 wheelhouse Formula 也已终止：SciPy 1.18.0 arm64 wheel 捆绑 LGPL 与 GPL Runtime Exception 组件，项目没有书面法律审批、精确 Corresponding Source 和构建对应材料。工程合规证据见 `docs/research/2026-07-13-wheelhouse-license-review.md`。

因此尚无候选通过全部门禁，也不能发布 `brew install` 命令。此前基于 fixture 结构将 Formula 标记为通过属于无效证据，相关 Cask、launcher 和占位 Formula 已删除。Cask 若继续捆绑相同 SciPy wheel，也不能消除许可证义务。

后续评估的“Homebrew 提供 NumPy/SciPy”候选也在许可证门禁停止：锁定的 SentencePiece 0.2.1 CPython 3.13 arm64 wheel 没有 wheel 内许可证或 PyPI provenance。虽然上游 `v0.2.1` tag 有 GitHub 验证签名，但当前没有证据把该精确二进制 wheel 绑定到对应 source commit。项目不能自写映射冒充上游构建证据；完整记录见 `docs/research/2026-07-13-wheelhouse-license-review.md`。

## 决策

载体选择保持 **Proposed**。标准 Formula 和锁定 wheelhouse Formula 均已淘汰。下一候选必须避免由 Subtap 分发该 SciPy wheel，或先取得书面法律批准并满足相应分发义务；不得通过改用 Cask、CDN 或静默忽略依赖绕过门禁。

新候选必须在一次性 CI 用户环境执行完整验收。只有许可证与验收门禁全部通过，才能：

- 将本 ADR 改为 `Accepted` 并记录日志链接；
- 启用 Tap 自动更新；
- 在 README 展示 `brew install`。
