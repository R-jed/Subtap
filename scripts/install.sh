#!/usr/bin/env bash
# Subtap 一键安装脚本
# 用法: curl -sSL https://raw.githubusercontent.com/R-jed/Subtap/main/scripts/install.sh | bash

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[subtap]${NC} $*"; }
warn()  { echo -e "${YELLOW}[subtap]${NC} $*"; }
error() { echo -e "${RED}[subtap]${NC} $*" >&2; }

# 检测操作系统
detect_os() {
    case "$(uname -s)" in
        Darwin*) echo "macos" ;;
        Linux*)  echo "linux" ;;
        *)       echo "unknown" ;;
    esac
}

# 检测是否安装了 uv
has_uv() {
    command -v uv &>/dev/null
}

# 检测是否安装了 brew
has_brew() {
    command -v brew &>/dev/null
}

# 检测是否安装了 pipx
has_pipx() {
    command -v pipx &>/dev/null
}

ensure_local_bin_on_path() {
    export PATH="$HOME/.local/bin:$PATH"
}

verify_installation() {
    ensure_local_bin_on_path
    info "验证安装..."
    command -v subtap >/dev/null || {
        error "subtap 未出现在 PATH 中，请检查 ~/.local/bin 或包管理器安装目录"
        return 1
    }
    subtap version
    subtap doctor
    info "安装验证通过"
}

install_via_uv() {
    info "通过 uv 安装 subtap..."
    if ! has_uv; then
        info "正在安装 uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        ensure_local_bin_on_path
    fi
    uv tool install subtap
    verify_installation
}

install_via_brew() {
    info "通过 Homebrew 安装 subtap..."
    brew tap R-jed/tap
    brew install subtap
    verify_installation
}

install_via_pipx() {
    info "通过 pipx 安装 subtap..."
    if ! has_pipx; then
        info "正在安装 pipx..."
        pip install pipx
        pipx ensurepath
    fi
    pipx install subtap
    verify_installation
}

install_via_pip() {
    info "通过 pip 安装 subtap..."
    python3 -m pip install --user subtap
    verify_installation
}

main() {
    info "开始安装 Subtap..."
    echo ""

    OS=$(detect_os)

    # macOS 优先 Homebrew
    if [ "$OS" = "macos" ] && has_brew; then
        if install_via_brew; then
            return
        fi
        warn "Homebrew 安装失败，尝试其他方式..."
    fi

    # 优先 uv
    if has_uv; then
        if install_via_uv; then
            return
        fi
        warn "uv 安装失败，尝试其他方式..."
    fi

    # 其次 pipx
    if has_pipx; then
        if install_via_pipx; then
            return
        fi
        warn "pipx 安装失败，尝试其他方式..."
    fi

    # 最后 pip
    if command -v python3 &>/dev/null; then
        install_via_pip
        return
    fi

    error "未找到可用的包管理器"
    echo "请手动安装："
    echo "  brew tap R-jed/tap && brew install subtap  # macOS"
    echo "  uv tool install subtap                    # 跨平台"
    echo "  pipx install subtap                       # 跨平台"
    echo "  pip install --user subtap     # 有 Python 环境"
    exit 1
}

main
