#!/usr/bin/env bash
# Run real local-only short-sample smoke checks with network disabled.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AUDIO_DIR="${SUBTAP_SMOKE_AUDIO_DIR:-/Users/qunqing/Downloads/ASR-SRT测试音频}"
MODEL_ROOT="${SUBTAP_SMOKE_MODEL_ROOT:-$ROOT/models}"
TMP_DIR="$(mktemp -d)"
SMOKE_HOME="$TMP_DIR/home"

cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

if [[ ! -f "$MODEL_ROOT/asr_1.7b/config.json" || ! -f "$MODEL_ROOT/aligner/config.json" ]]; then
    echo "[subtap-smoke] missing local models under: $MODEL_ROOT" >&2
    echo "[subtap-smoke] set SUBTAP_SMOKE_MODEL_ROOT=/path/to/models if needed" >&2
    exit 1
fi

mkdir -p "$SMOKE_HOME/.subtap/glossary"
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

export HTTP_PROXY=http://127.0.0.1:9
export HTTPS_PROXY=http://127.0.0.1:9
export ALL_PROXY=http://127.0.0.1:9

run_sample() {
    local input="$1"
    local name="$2"

    if [[ ! -f "$input" ]]; then
        echo "[subtap-smoke] missing sample: $input" >&2
        return 1
    fi

    HOME="$SMOKE_HOME" uv run subtap run "$input" \
        --local-only \
        --work-dir "$TMP_DIR/work-$name" \
        --output-dir "$TMP_DIR/out-$name" \
        --no-git-check \
        --no-cleanroom
}

run_sample "$AUDIO_DIR/数字测试.mp3" "number"
run_sample "$AUDIO_DIR/短的演讲音频.wav" "speech"

python3 "$ROOT/scripts/check_srt_delivery.py" "$TMP_DIR"/out-*/*.srt
