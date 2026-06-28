#!/bin/bash
# scripts/release-check.sh
# Release 质量检查脚本

set -e

echo "═══ Release 质量检查 ═══"
echo ""

PYTHON="${PYTHON:-python3}"
if [ -x ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
fi

# 检查项
CHECKS=(
    "pip install -e .[dev,ai]|$PYTHON -m pip install -e '.[dev,ai]'"
    "ruff check|$PYTHON -m ruff check src tests"
    "black --check|$PYTHON -m black --check src tests"
    "mypy|$PYTHON -m mypy src/subtap"
    "pytest|$PYTHON -m pytest -q -p no:cacheprovider -x"
    "subtap setup --skip-models|$PYTHON -m subtap.cli setup --skip-models"
    "subtap --help|$PYTHON -m subtap.cli --help"
    "subtap run --help|$PYTHON -m subtap.cli run --help"
    "subtap batch-transcribe --help|$PYTHON -m subtap.cli batch-transcribe --help"
    "subtap glossary --help|$PYTHON -m subtap.cli glossary --help"
    "subtap doctor|$PYTHON -m subtap.cli doctor --workspace"
    "subtap doctor --json|$PYTHON -m subtap.cli doctor --workspace --json"
    "subtap models list|$PYTHON -m subtap.cli models list"
    "python -m subtap.cli --help|$PYTHON -m subtap.cli --help"
)

PASSED=0
FAILED=0

for check in "${CHECKS[@]}"; do
    label="${check%%|*}"
    command="${check#*|}"
    echo "▸ 检查: $label"
    OUTPUT=$(eval "$command" 2>&1) && RC=0 || RC=$?
    if [ $RC -eq 0 ]; then
        echo "  ✓ 通过"
        PASSED=$((PASSED + 1))
    else
        echo "  ✗ 失败"
        if [ "$label" = "pytest" ]; then
            echo "$OUTPUT" | tail -30
        else
            echo "$OUTPUT" | head -10
        fi
        FAILED=$((FAILED + 1))
    fi
done

echo "▸ 检查: subtap run smoke"
if [ -f "models/asr_0.6b/config.json" ]; then
    SMOKE_DIR="$(mktemp -d)"
    "$PYTHON" - "$SMOKE_DIR/input.wav" <<'PY' > /dev/null
import math
import struct
import sys
import wave

path = sys.argv[1]
with wave.open(path, "w") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(16000)
    frames = bytearray()
    for i in range(16000):
        sample = int(12000 * math.sin(2 * math.pi * 440 * i / 16000))
        frames += struct.pack("<h", sample)
    wav.writeframes(frames)
PY
    if "$PYTHON" -m subtap.cli run "$SMOKE_DIR/input.wav" \
        --no-tui --no-git-check --no-cleanroom \
        --mode fast --no-timestamp \
        -w "$SMOKE_DIR/work" -o "$SMOKE_DIR/output" > /dev/null 2>&1 \
        && [ -s "$SMOKE_DIR/output/output.srt" ]; then
        echo "  ✓ 通过"
        PASSED=$((PASSED + 1))
    else
        echo "  ✗ 失败"
        FAILED=$((FAILED + 1))
    fi
    rm -rf "$SMOKE_DIR"
else
    echo "  - 跳过：models/asr_0.6b 未安装"
fi

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
