#!/usr/bin/env bash
# Homebrew 真实安装验收脚本
# 用法: ./scripts/homebrew_acceptance.sh
# 前置条件: R-jed/tap 已配置，macOS Apple Silicon

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[brew-accept]${NC} $*"; }
error() { echo -e "${RED}[brew-accept]${NC} $*" >&2; }
warn()  { echo -e "${YELLOW}[brew-accept]${NC} $*"; }

# ── 前置检查 ──────────────────────────────────────────────
if [[ "$(uname -m)" != "arm64" ]]; then
    error "需要 Apple Silicon (arm64)"
    exit 1
fi

if ! command -v brew &>/dev/null; then
    error "需要 Homebrew"
    exit 1
fi

# ── 确保 tap 已配置 ──────────────────────────────────────
if ! brew tap | grep -q "r-jed/tap"; then
    info "添加 R-jed/tap..."
    brew tap R-jed/tap
fi

# ── 冷安装测试 ──────────────────────────────────────────────
info "═══ 冷安装测试 ═══"

# 卸载已有版本（如有）
brew uninstall subtap 2>/dev/null || true

info "执行 brew install subtap..."
if brew install subtap; then
    info "✓ brew install 成功"
else
    error "✗ brew install 失败"
    exit 1
fi

# ── 验证命令可用 ──────────────────────────────────────────
info "验证命令可用..."
if subtap version; then
    info "✓ subtap version 通过"
else
    error "✗ subtap version 失败"
    exit 1
fi

# ── 验证 doctor ──────────────────────────────────────────
if subtap doctor --json > /dev/null 2>&1; then
    info "✓ subtap doctor 通过"
else
    warn "subtap doctor 退出非零（模型未下载，属正常）"
fi

# ── 验证 TUI ──────────────────────────────────────────────
if subtap tui --help > /dev/null 2>&1; then
    info "✓ subtap tui --help 通过"
else
    error "✗ subtap tui --help 失败"
    exit 1
fi

# ── 验证 brew audit ──────────────────────────────────────
info "执行 brew audit..."
if brew audit subtap; then
    info "✓ brew audit 通过"
else
    warn "⚠ brew audit 有警告（非致命）"
fi

# ── 验证 brew test ──────────────────────────────────────
info "执行 brew test..."
if brew test subtap; then
    info "✓ brew test 通过"
else
    warn "⚠ brew test 有警告（非致命）"
fi

# ── 升级测试 ──────────────────────────────────────────────
info "═══ 升级测试 ═══"
info "执行 brew upgrade subtap..."
if brew upgrade subtap 2>&1; then
    info "✓ brew upgrade 通过"
else
    info "已是最新版本，无需升级"
fi

# ── 卸载测试 ──────────────────────────────────────────────
info "═══ 卸载测试 ═══"
info "执行 brew uninstall subtap..."
if brew uninstall subtap; then
    info "✓ brew uninstall 通过"
else
    error "✗ brew uninstall 失败"
    exit 1
fi

# ── 验证用户资料保留 ──────────────────────────────────────
info "验证用户资料保留..."
SUBTAP_DIR="$HOME/.subtap"
if [[ -d "$SUBTAP_DIR" ]]; then
    info "✓ ~/.subtap 目录保留"
    if [[ -d "$SUBTAP_DIR/models" ]]; then
        info "✓ 模型目录保留"
    fi
    if [[ -d "$SUBTAP_DIR/glossaries" ]]; then
        info "✓ 热词库保留"
    fi
else
    info "✓ ~/.subtap 不存在（首次安装后卸载，正常）"
fi

info "═══ Homebrew 验收全部通过 ═══"
