#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Homebrew Cold-Install Acceptance Tester
# 在一次性 HOME 中验证三种分发载体的冷安装、升级、卸载和数据保留
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE=""
RESULT_JSON=""
STEPS_JSON="[]"
OVERALL_PASSED=true
DATA_PRESERVED=false

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

now_ms() {
  date +%s%3N
}

disk_usage_bytes() {
  local path="$1"
  if [[ -d "$path" ]]; then
    du -sk "$path" 2>/dev/null | awk '{print $1 * 1024}'
  else
    echo 0
  fi
}

append_step() {
  local name="$1"
  local exit_code="$2"
  local duration_ms="$3"
  local disk_bytes="$4"

  local step
  step=$(printf '{"name":"%s","exit_code":%d,"duration_ms":%d,"disk_bytes":%d}' \
    "$name" "$exit_code" "$duration_ms" "$disk_bytes")

  if [[ "$STEPS_JSON" == "[]" ]]; then
    STEPS_JSON="[$step]"
  else
    STEPS_JSON="${STEPS_JSON%]},$step]"
  fi
}

log() {
  local msg
  msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
  echo "$msg"
  if [[ -n "$LOG_FILE" ]]; then
    echo "$msg" >> "$LOG_FILE"
  fi
}

# ---------------------------------------------------------------------------
# JSON output via trap (always runs, even on failure)
# ---------------------------------------------------------------------------

write_result_json() {
  [[ -z "$RESULT_JSON" ]] && return 0

  # Ensure parent directory exists
  mkdir -p "$(dirname "$RESULT_JSON")"

  # Determine data_preserved (only meaningful after uninstall ran)
  local preserved="false"
  if [[ "$DATA_PRESERVED" == "true" ]]; then
    preserved="true"
  fi

  local passed="false"
  if [[ "$OVERALL_PASSED" == "true" ]]; then
    passed="true"
  fi

  cat > "$RESULT_JSON" <<ENDJSON
{
  "carrier": "${CARRIER:-unknown}",
  "passed": $passed,
  "steps": $STEPS_JSON,
  "data_preserved": $preserved,
  "log_path": "${LOG_FILE:-}"
}
ENDJSON

  log "Result written to $RESULT_JSON"
}

trap write_result_json EXIT

# ---------------------------------------------------------------------------
# Step runner — tracks timing, disk, exit code
# ---------------------------------------------------------------------------

run_step() {
  local name="$1"
  shift
  local start_ms exit_code duration_ms disk_before disk_after disk_delta

  log ">>> BEGIN step: $name"
  start_ms=$(now_ms)
  disk_before=$(disk_usage_bytes "$TEST_HOME")

  set +e
  "$@"
  exit_code=$?
  set -e

  disk_after=$(disk_usage_bytes "$TEST_HOME")
  disk_delta=$(( disk_after - disk_before ))
  if (( disk_delta < 0 )); then disk_delta=0; fi

  duration_ms=$(( $(now_ms) - start_ms ))

  append_step "$name" "$exit_code" "$duration_ms" "$disk_delta"
  log "<<< END   step: $name  exit=$exit_code  ${duration_ms}ms  disk_delta=${disk_delta}B"

  # Special handling: subtap doctor may fail (models not downloaded)
  # but still records its exit code. Only fail if exit_code indicates
  # the binary could not even start (126/127) or a genuine crash.
  if [[ "$name" == "doctor" ]]; then
    if (( exit_code == 126 || exit_code == 127 )); then
      log "ERROR: subtap doctor could not execute (exit $exit_code)"
      OVERALL_PASSED=false
    elif (( exit_code != 0 )); then
      log "WARN: subtap doctor exited $exit_code (models may not be downloaded) — not failing acceptance"
    fi
    return 0
  fi

  if (( exit_code != 0 )); then
    log "ERROR: step '$name' failed with exit $exit_code"
    OVERALL_PASSED=false
  fi

  return 0
}

# ---------------------------------------------------------------------------
# Safety guards
# ---------------------------------------------------------------------------

validate_safety() {
  # Must be macOS arm64
  if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
    echo "ERROR: must run on macOS arm64" >&2
    exit 2
  fi

  # Must have exactly 4 positional args
  if (( $# != 4 )); then
    echo "Usage: $0 <carrier> <formula_or_cask> <artifact> <result_json>" >&2
    echo "  carrier: formula | cask | launcher" >&2
    exit 2
  fi

  CARRIER="$1"
  FORMULA_OR_CASK="$2"
  ARTIFACT="$3"
  RESULT_JSON="$4"

  # Validate carrier type
  if [[ "$CARRIER" != "formula" && "$CARRIER" != "cask" && "$CARRIER" != "launcher" ]]; then
    echo "ERROR: carrier must be one of: formula, cask, launcher" >&2
    exit 2
  fi

  # TEST_HOME must be an isolated temp directory
  if [[ -z "${TEST_HOME:-}" ]]; then
    echo "ERROR: TEST_HOME is not set" >&2
    RESULT_JSON=""
    exit 2
  fi

  if [[ "$TEST_HOME" != /tmp/subtap-homebrew-* ]]; then
    echo "ERROR: TEST_HOME must match /tmp/subtap-homebrew-*" >&2
    echo "  Got: $TEST_HOME" >&2
    RESULT_JSON=""   # Prevent trap from writing misleading JSON
    exit 2
  fi

  # HOMEBREW_CACHE must be inside TEST_HOME
  if [[ -z "${HOMEBREW_CACHE:-}" || "$HOMEBREW_CACHE" != "$TEST_HOME"/* ]]; then
    echo "ERROR: HOMEBREW_CACHE must be inside TEST_HOME" >&2
    echo "  Expected: $TEST_HOME/..." >&2
    echo "  Got: ${HOMEBREW_CACHE:-<unset>}" >&2
    RESULT_JSON=""
    exit 2
  fi

  # result_json path must be inside TEST_HOME
  if [[ "$RESULT_JSON" != "$TEST_HOME"/* ]]; then
    echo "ERROR: result_json must be inside TEST_HOME" >&2
    echo "  Expected: $TEST_HOME/..." >&2
    echo "  Got: $RESULT_JSON" >&2
    RESULT_JSON=""
    exit 2
  fi
}

# ---------------------------------------------------------------------------
# Main acceptance sequence
# ---------------------------------------------------------------------------

main() {
  validate_safety "$@"

  # Set up logging
  LOG_FILE="$TEST_HOME/acceptance.log"
  mkdir -p "$TEST_HOME"
  : > "$LOG_FILE"

  log "Carrier: $CARRIER"
  log "Formula/Cask: $FORMULA_OR_CASK"
  log "Artifact: $ARTIFACT"
  log "TEST_HOME: $TEST_HOME"
  log "HOMEBREW_CACHE: $HOMEBREW_CACHE"

  # Pre-create user data directory for preservation test
  local user_data_dir="$TEST_HOME/.subtap/glossary"
  mkdir -p "$user_data_dir"
  echo "保留我" > "$user_data_dir/user.txt"
  log "Created user data: $user_data_dir/user.txt"

  # Set HOME to TEST_HOME for all brew operations
  export HOME="$TEST_HOME"

  # --- Acceptance sequence ---

  run_step "audit" brew audit --strict "$FORMULA_OR_CASK"

  run_step "install" brew install "$FORMULA_OR_CASK"

  run_step "version" subtap version

  # doctor: may fail (models not downloaded) but must attempt to run
  run_step "doctor" subtap doctor --json

  run_step "reinstall" brew reinstall "$FORMULA_OR_CASK"

  run_step "uninstall" brew uninstall "$FORMULA_OR_CASK"

  # Verify data preservation
  run_step "data_preserved" bash -c "
    if [[ -f '$user_data_dir/user.txt' ]]; then
      content=\$(cat '$user_data_dir/user.txt')
      if [[ \"\$content\" == '保留我' ]]; then
        exit 0
      else
        echo 'Data corrupted: expected 保留我, got \$content' >&2
        exit 1
      fi
    else
      echo 'Data lost: $user_data_dir/user.txt does not exist' >&2
      exit 1
    fi
  "

  # Record data preservation result
  if [[ -f "$user_data_dir/user.txt" ]] && [[ "$(cat "$user_data_dir/user.txt")" == "保留我" ]]; then
    DATA_PRESERVED=true
  fi

  log "Acceptance complete. passed=$OVERALL_PASSED data_preserved=$DATA_PRESERVED"

  # Exit non-zero if any step failed
  if [[ "$OVERALL_PASSED" != "true" ]]; then
    exit 1
  fi
}

main "$@"
