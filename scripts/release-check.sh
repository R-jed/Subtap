#!/bin/bash
# scripts/release-check.sh
# Release 质量检查脚本

set -e

echo "═══ Release 质量检查 ═══"
echo ""

# 检查项
CHECKS=(
    "pip install -e ."
    "subtap setup --skip-models"
    "subtap --help"
    "subtap run --help"
    "subtap doctor"
    "subtap models list"
    "python -m subtap.cli --help"
)

PASSED=0
FAILED=0

for check in "${CHECKS[@]}"; do
    echo "▸ 检查: $check"
    if eval "$check" > /dev/null 2>&1; then
        echo "  ✓ 通过"
        PASSED=$((PASSED + 1))
    else
        echo "  ✗ 失败"
        FAILED=$((FAILED + 1))
    fi
done

echo ""
echo "═══ 检查结果 ═══"
echo "  通过: $PASSED"
echo "  失败: $FAILED"

if [ $FAILED -gt 0 ]; then
    echo ""
    echo "❌ Release 检查失败"
    exit 1
fi

echo ""
echo "✓ 所有检查通过"
