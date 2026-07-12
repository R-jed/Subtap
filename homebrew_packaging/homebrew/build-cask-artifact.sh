#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# build-cask-artifact.sh — 构建 arm64 自包含归档（不含 models）
# 产出: dist/subtap-${VERSION}-macos-arm64.tar.gz + .sha256
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

# ---------------------------------------------------------------------------
# Guard: 必须在 macOS arm64 上运行
# ---------------------------------------------------------------------------

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "ERROR: must run on macOS arm64" >&2
  exit 2
fi

# ---------------------------------------------------------------------------
# 从 pyproject.toml 提取版本号
# ---------------------------------------------------------------------------

VERSION=$(grep -E '^version\s*=' pyproject.toml | head -1 | sed 's/.*"\([^"]*\)".*/\1/')
if [[ -z "$VERSION" ]]; then
  echo "ERROR: could not extract version from pyproject.toml" >&2
  exit 1
fi

ARTIFACT_NAME="subtap-${VERSION}-macos-arm64"
DIST_DIR="$PROJECT_ROOT/dist"
STAGING="$DIST_DIR/staging-${ARTIFACT_NAME}"

echo ">>> Building $ARTIFACT_NAME"

# ---------------------------------------------------------------------------
# 清理旧的 staging 和产出
# ---------------------------------------------------------------------------

rm -rf "$STAGING"
mkdir -p "$STAGING" "$DIST_DIR"

# ---------------------------------------------------------------------------
# 使用 uv sync --frozen 构建运行时环境
# ---------------------------------------------------------------------------

echo ">>> Syncing dependencies with uv"
uv sync --frozen

# ---------------------------------------------------------------------------
# 复制应用与依赖到 staging
# ---------------------------------------------------------------------------

echo ">>> Copying application to staging"

# 复制 Python 虚拟环境（包含已安装的包和 bin/ 入口）
VENV_DIR="$PROJECT_ROOT/.venv"
if [[ ! -d "$VENV_DIR" ]]; then
  echo "ERROR: .venv not found at $VENV_DIR" >&2
  exit 1
fi

cp -a "$VENV_DIR" "$STAGING/subtap"

# 确保 bin/ 存在
if [[ ! -x "$STAGING/subtap/bin/subtap" ]]; then
  echo "ERROR: staging binary not found at $STAGING/subtap/bin/subtap" >&2
  exit 1
fi

# 修补 shebang：将开发机路径改为相对路径
# uv 生成的 bin/subtap shebang 会指向 .venv 的绝对路径，搬移后失效
# 用 env python3 替代，让 bin/subtap 通过 PATH 查找自己的 Python
if [[ -f "$STAGING/subtap/bin/subtap" ]]; then
  # 检查 shebang 是否包含绝对路径
  first_line=$(head -1 "$STAGING/subtap/bin/subtap")
  if [[ "$first_line" == "#!/"* ]]; then
    sed -i '' "1s|^#!.*|#!/usr/bin/env python3|" "$STAGING/subtap/bin/subtap"
    echo ">>> Patched shebang in bin/subtap"
  fi
fi

# ---------------------------------------------------------------------------
# 清理：缓存、测试、__pycache__、models/
# ---------------------------------------------------------------------------

echo ">>> Cleaning caches, tests, and models"

find "$STAGING" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$STAGING" -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
find "$STAGING" -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
find "$STAGING" -name "*.pyc" -delete 2>/dev/null || true

# 删除 models/ 目录（自包含归档不含模型）
find "$STAGING" -type d -name "models" -exec rm -rf {} + 2>/dev/null || true

# 删除测试文件
find "$STAGING" -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
find "$STAGING" -name "test_*.py" -delete 2>/dev/null || true
find "$STAGING" -name "*_test.py" -delete 2>/dev/null || true

# ---------------------------------------------------------------------------
# 打包：将 staging 目录重命名为 subtap/ 作为归档顶层目录
# Homebrew Cask 解压后需要 subtap/bin/subtap 路径
# ---------------------------------------------------------------------------

echo ">>> Creating archive"
TARBALL="$DIST_DIR/${ARTIFACT_NAME}.tar.gz"
ARCHIVE_SRC="$DIST_DIR/subtap"
rm -rf "$ARCHIVE_SRC"
mv "$STAGING" "$ARCHIVE_SRC"
(cd "$DIST_DIR" && tar -czf "${ARTIFACT_NAME}.tar.gz" "subtap")
mv "$ARCHIVE_SRC" "$STAGING"

# 计算 SHA256
shasum -a 256 "$TARBALL" | awk '{print $1}' > "$DIST_DIR/${ARTIFACT_NAME}.sha256"

echo ">>> Archive: $TARBALL"
echo ">>> SHA256:  $(cat "$DIST_DIR/${ARTIFACT_NAME}.sha256")"

# ---------------------------------------------------------------------------
# 隔离环境验收：使用 env -i 确保不依赖开发机环境变量
# ---------------------------------------------------------------------------

echo ">>> Running relocatable validation"

TEST_HOME=$(mktemp -d /tmp/subtap-build-validate.XXXXXX)
trap 'if [[ $? -ne 0 ]]; then
  echo "FAIL: preserved staging=$STAGING validate_dir=$TEST_HOME" >&2
else
  rm -rf "$TEST_HOME" "$STAGING"
fi' EXIT

# 解压到临时目录模拟安装
VALIDATE_DIR="$TEST_HOME/install"
mkdir -p "$VALIDATE_DIR"
tar -xzf "$TARBALL" -C "$VALIDATE_DIR"

# 用 env -i 创建完全隔离的环境运行 subtap version
# 如果原生库（MLX 等）无法加载，subtap 会直接 crash，脚本应失败
env -i HOME="$TEST_HOME" PATH="/usr/bin:/bin" \
  "$VALIDATE_DIR/subtap/bin/subtap" version

echo ">>> Validation passed: subtap version runs in isolated environment"

# ---------------------------------------------------------------------------
# 清理 staging（验证成功后）
# ---------------------------------------------------------------------------

rm -rf "$STAGING"
echo ">>> Done. Artifact at $TARBALL"
