#!/usr/bin/env bash
# 一键冷安装验证脚本
# 用法: ./scripts/cold_install_test.sh [wheel_path]
# 在全新 Apple Silicon Mac 上验证完整安装流程

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[cold-install]${NC} $*"; }
error() { echo -e "${RED}[cold-install]${NC} $*" >&2; }
warn()  { echo -e "${YELLOW}[cold-install]${NC} $*"; }

# 隔离环境
TMP_DIR="$(mktemp -d)"
MOCK_HOME="$TMP_DIR/home"
MOCK_BREW="$TMP_DIR/brew-prefix"
WHEEL_PATH="${1:-}"

cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

info "临时目录: $TMP_DIR"
info "隔离 HOME: $MOCK_HOME"

# ── 前置检查 ──────────────────────────────────────────────
if [[ "$(uname -m)" != "arm64" ]]; then
    error "需要 Apple Silicon (arm64)，当前: $(uname -m)"
    exit 1
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
    error "需要 macOS，当前: $(uname -s)"
    exit 1
fi

# ── 准备隔离环境 ──────────────────────────────────────────
mkdir -p "$MOCK_HOME"
export HOME="$MOCK_HOME"

# ── 构建 wheel（如未提供）──────────────────────────────────
if [[ -z "$WHEEL_PATH" ]]; then
    info "构建 wheel..."
    uv build --out-dir "$TMP_DIR/dist" >/dev/null 2>&1
    WHEEL_PATH=$(ls "$TMP_DIR/dist/"*.whl | head -1)
fi

if [[ ! -f "$WHEEL_PATH" ]]; then
    error "找不到 wheel: $WHEEL_PATH"
    exit 1
fi

info "安装 wheel: $WHEEL_PATH"

# ── 安装到隔离 venv ──────────────────────────────────────
VENV="$TMP_DIR/venv"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet "$WHEEL_PATH"

info "安装完成，验证命令可用..."

# ── 验证基础命令 ──────────────────────────────────────────
"$VENV/bin/subtap" version
info "✓ subtap version 通过"

# ── 验证 doctor ──────────────────────────────────────────
if "$VENV/bin/subtap" doctor --json > "$TMP_DIR/doctor.json" 2>&1; then
    info "✓ subtap doctor 通过"
else
    warn "subtap doctor 退出非零（可能模型未安装，属正常）"
fi

# ── 验证 TUI 启动 ──────────────────────────────────────────
if "$VENV/bin/subtap" tui --help > /dev/null 2>&1; then
    info "✓ subtap tui --help 通过"
else
    error "✗ subtap tui --help 失败"
    exit 1
fi

# ── 验证首次运行目录创建 ──────────────────────────────────────
"$VENV/bin/subtap" run --help > /dev/null 2>&1 || true

if [[ -d "$MOCK_HOME/.subtap" ]]; then
    info "✓ ~/.subtap 目录已创建"
else
    warn "⚠ ~/.subtap 目录未创建（可能需要实际运行触发）"
fi

# ── 验证 doctor --release（预期失败，模型未下载）────────────
if "$VENV/bin/subtap" doctor --release --json > "$TMP_DIR/doctor-release.json" 2>&1; then
    info "✓ doctor --release 通过（模型已存在）"
else
    RELEASE_EXIT=$?
    if [[ $RELEASE_EXIT -eq 1 ]]; then
        info "✓ doctor --release 正确返回 1（模型未下载，属预期）"
    else
        error "✗ doctor --release 异常退出: $RELEASE_EXIT"
        exit 1
    fi
fi

info "═══ 冷安装验证全部通过 ═══"
