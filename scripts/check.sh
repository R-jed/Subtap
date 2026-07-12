#!/usr/bin/env bash
set -euo pipefail

# 确保在仓库根目录执行，避免误删用户文件
REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"

echo "==> black format check"
uv run black --check src tests

echo "==> mypy type check"
uv run mypy src/subtap

echo "==> pytest unit tests"
uv run pytest -q -p no:cacheprovider

echo "==> build package"
rm -rf dist
uv build

echo "==> release packaging test"
uv run pytest -q tests/test_release_packaging.py

echo "==> check.sh passed"
