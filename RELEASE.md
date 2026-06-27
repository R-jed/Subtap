# Release v0.1.0

**发布日期：** 2026-06-27

## 支持范围

当前版本面向 macOS 开发版源码安装，已在 Apple Silicon 环境验证。当前不提供 Developer ID 签名、公证或正式二进制分发。

## 🎉 新特性

- **Output Engine** — 统一输出管理，支持版本控制
- **TUI 颜色方案** — 统一管理界面颜色
- **CLI `--timestamp/--no-timestamp` 参数** — 控制输出目录是否带时间戳
- **命名策略系统** — 管理输出文件命名
- **版本管理系统** — 支持版本递增、latest 符号链接、旧版本清理

## 🐛 Bug 修复

- 修复 `.gitignore` 规则，避免误忽略 `src/subtap/output/` 目录
- 修复 `NamingStrategy` 多余参数和方法

## 📚 文档

- 添加 Phase 15+16 Output Engine 设计规格
- 添加 Phase 15+16 Output Engine 实现计划
- 添加 Phase 17 Release Engineering 设计规格

## ✅ 测试

- 280 个测试全部通过
- 输出系统 26 个测试全部通过

## 📦 安装

```bash
# 克隆项目
git clone <repo-url>
cd Subtap

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装
pip install -e .

# 初始化
subtap setup

# 检查环境
subtap doctor
```

## 🚀 快速开始

```bash
# 生成字幕
subtap run video.mp3

# 运行演示
subtap demo
```
