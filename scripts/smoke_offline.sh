#!/usr/bin/env bash
# Run real local-only short-sample smoke checks with network disabled.
#
# Exit codes:
#   0 — all samples processed and SRT delivery checks passed
#   1 — missing models, missing samples, or SRT delivery failure
#
# Environment:
#   SUBTAP_SMOKE_AUDIO_DIR  — override test audio directory
#   SUBTAP_SMOKE_MODEL_ROOT — override local model root
#   SUBTAP_SMOKE_REFERENCE_SRT — manually reviewed high-quality Chinese SRT
#   SUBTAP_SMOKE_REQUIRED_CUES — override required reviewed cue list
#   SUBTAP_SMOKE_SUBTAP_BIN — run an installed subtap executable instead of uv
#   SUBTAP_SMOKE_PYTHON_BIN — override Python used by the regression checker
#   SUBTAP_SMOKE_JSON       — write structured JSON result to this path

set -euo pipefail

info() {
    echo "[subtap-smoke] $*" >&2
}

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AUDIO_DIR="${SUBTAP_SMOKE_AUDIO_DIR:-/Users/qunqing/Downloads/ASR-SRT测试音频}"
MODEL_ROOT="${SUBTAP_SMOKE_MODEL_ROOT:-$ROOT/models}"
TMP_DIR="$(mktemp -d)"
SMOKE_HOME="$TMP_DIR/home"
SANDBOX_PROFILE="$TMP_DIR/offline.sb"
SUBTAP_BIN="${SUBTAP_SMOKE_SUBTAP_BIN:-}"
REFERENCE_SRT="${SUBTAP_SMOKE_REFERENCE_SRT:-}"
REQUIRED_CUES="${SUBTAP_SMOKE_REQUIRED_CUES:-$ROOT/tests/fixtures/high_quality_zh_required_cues.txt}"
MAX_RTF="0.25"

cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

if ! command -v sandbox-exec >/dev/null 2>&1; then
    echo "[subtap-smoke] macOS sandbox-exec is required for offline acceptance" >&2
    exit 1
fi

if [[ -n "$SUBTAP_BIN" && ! -x "$SUBTAP_BIN" ]]; then
    echo "[subtap-smoke] subtap executable not found: $SUBTAP_BIN" >&2
    exit 1
fi

if [[ -z "$REFERENCE_SRT" || ! -f "$REFERENCE_SRT" ]]; then
    echo "[subtap-smoke] SUBTAP_SMOKE_REFERENCE_SRT must point to a reviewed SRT" >&2
    exit 1
fi

if [[ ! -f "$REQUIRED_CUES" ]]; then
    echo "[subtap-smoke] required cue list not found: $REQUIRED_CUES" >&2
    exit 1
fi

cat > "$SANDBOX_PROFILE" <<'EOF'
(version 1)
(allow default)
(deny network*)
EOF

if [[ ! -f "$MODEL_ROOT/asr_1.7b/config.json" || ! -f "$MODEL_ROOT/aligner/config.json" ]]; then
    echo "[subtap-smoke] missing local models under: $MODEL_ROOT" >&2
    echo "[subtap-smoke] set SUBTAP_SMOKE_MODEL_ROOT=/path/to/models if needed" >&2
    exit 1
fi

mkdir -p "$SMOKE_HOME/.subtap/glossaries"
cat > "$SMOKE_HOME/.subtap/config.yaml" <<EOF
mode: offline
models:
  root: "$MODEL_ROOT"
asr:
  backend: mlx-qwen-asr
  model: asr_1.7b
  quantization: q8
  keep_model_alive: false
align:
  backend: mlx-qwen-aligner
  model: aligner
  quantization: q8
  keep_model_alive: false
llm_proofread: false
llm_hotword: false
translate_to: ""
EOF

run_sample() {
    local input="$1"
    local name="$2"

    if [[ ! -f "$input" ]]; then
        echo "[subtap-smoke] missing sample: $input" >&2
        return 1
    fi

    local -a subtap_command
    if [[ -n "$SUBTAP_BIN" ]]; then
        subtap_command=("$SUBTAP_BIN")
    else
        subtap_command=(uv run subtap)
    fi

    HOME="$SMOKE_HOME" sandbox-exec -f "$SANDBOX_PROFILE" \
        "${subtap_command[@]}" run "$input" \
            --local-only \
            --work-dir "$TMP_DIR/work-$name" \
            --output-dir "$TMP_DIR/out-$name" \
            --no-git-check \
            --no-cleanroom
}

run_sample "$AUDIO_DIR/数字测试.mp3" "number"
run_sample "$AUDIO_DIR/短的演讲音频.wav" "speech"
run_sample "$AUDIO_DIR/高质量中文语音.mp3" "high-quality-zh"

if [[ -n "${SUBTAP_SMOKE_PYTHON_BIN:-}" ]]; then
    SMOKE_PYTHON=("$SUBTAP_SMOKE_PYTHON_BIN")
elif [[ -n "$SUBTAP_BIN" ]]; then
    SMOKE_PYTHON=("$(dirname "$SUBTAP_BIN")/python")
else
    SMOKE_PYTHON=(uv run python)
fi
HOME="$SMOKE_HOME" sandbox-exec -f "$SANDBOX_PROFILE" \
    "${SMOKE_PYTHON[@]}" "$ROOT/scripts/check_srt_delivery.py" \
        "$TMP_DIR"/out-*/*.srt

QUALITY_SRT="$(find "$TMP_DIR/out-high-quality-zh" -maxdepth 1 -name '*.srt' -print -quit)"
if [[ -z "$QUALITY_SRT" ]]; then
    echo "[subtap-smoke] high-quality Chinese SRT was not generated" >&2
    exit 1
fi

HOME="$SMOKE_HOME" sandbox-exec -f "$SANDBOX_PROFILE" \
    "${SMOKE_PYTHON[@]}" "$ROOT/scripts/check_srt_regression.py" \
        "$QUALITY_SRT" "$REFERENCE_SRT" \
        --required-cues "$REQUIRED_CUES"

HOME="$SMOKE_HOME" sandbox-exec -f "$SANDBOX_PROFILE" \
    "${SMOKE_PYTHON[@]}" "$ROOT/scripts/check_performance.py" \
        "$TMP_DIR/work-high-quality-zh/metrics.json" \
        --max-rtf "$MAX_RTF"

JSON_OUTPUT="${SUBTAP_SMOKE_JSON:-}"
if [[ -n "$JSON_OUTPUT" ]]; then
    cat > "$JSON_OUTPUT" <<ENDJSON
{
  "ok": true,
  "samples": [
    {"name": "number", "input": "$AUDIO_DIR/数字测试.mp3", "output_dir": "$TMP_DIR/out-number"},
    {"name": "speech", "input": "$AUDIO_DIR/短的演讲音频.wav", "output_dir": "$TMP_DIR/out-speech"},
    {"name": "high-quality-zh", "input": "$AUDIO_DIR/高质量中文语音.mp3", "output_dir": "$TMP_DIR/out-high-quality-zh"}
  ],
  "output_dirs": ["$TMP_DIR/out-number", "$TMP_DIR/out-speech", "$TMP_DIR/out-high-quality-zh"],
  "srt_check": "passed"
}
ENDJSON
    info "JSON 结果写入: $JSON_OUTPUT"
fi
