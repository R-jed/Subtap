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

2026-07-13 在 Apple Silicon Mac 执行 `./scripts/homebrew_acceptance.sh`：

```text
brew tap R-jed/tap
Repository not found: https://github.com/R-jed/homebrew-tap/
```

因此尚无候选通过全部门禁，也不能发布 `brew install` 命令。此前基于 fixture
结构将 Formula 标记为通过属于无效证据，相关 Cask、launcher 和占位 Formula
已删除。

## 决策

载体选择保持 **Proposed**。创建真实 Tap、生成无占位依赖与校验值的候选后，必须在
一次性 CI 用户环境执行 `scripts/homebrew_acceptance.sh`。只有该脚本完整通过，才能：

- 将本 ADR 改为 `Accepted` 并记录日志链接；
- 启用 Tap 自动更新；
- 在 README 展示 `brew install`。
