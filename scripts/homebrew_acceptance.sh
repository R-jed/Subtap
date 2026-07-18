#!/usr/bin/env bash
# Destructive Homebrew acceptance test. Run only in an ephemeral macOS CI user.

set -euo pipefail

info()  { printf '[brew-accept] %s\n' "$*"; }
error() { printf '[brew-accept] ERROR: %s\n' "$*" >&2; }

if [[ "${SUBTAP_HOMEBREW_ACCEPTANCE:-}" != "1" ]]; then
    error "refusing destructive test; set SUBTAP_HOMEBREW_ACCEPTANCE=1"
    exit 1
fi
if [[ -z "${SUBTAP_ACCEPTANCE_HOME:-}" || "$HOME" != "$SUBTAP_ACCEPTANCE_HOME" ]]; then
    error "HOME must equal an explicit SUBTAP_ACCEPTANCE_HOME"
    exit 1
fi
case "$HOME" in
    /tmp/*|/private/tmp/*|/var/folders/*|/private/var/folders/*) ;;
    *) error "acceptance HOME must be an ephemeral temporary directory"; exit 1 ;;
esac
if [[ "$(uname -m)" != "arm64" ]]; then
    error "requires Apple Silicon (arm64)"
    exit 1
fi
if ! command -v brew >/dev/null; then
    error "Homebrew is required"
    exit 1
fi
if brew list --versions subtap >/dev/null 2>&1; then
    error "refusing to touch an existing Subtap installation"
    exit 1
fi
if ! brew tap | grep -Fxq "r-jed/tap"; then
    error "r-jed/tap is not configured; create and validate the tap first"
    exit 1
fi
if [[ -z "${PREVIOUS_FORMULA:-}" || ! -f "$PREVIOUS_FORMULA" ]]; then
    error "PREVIOUS_FORMULA must point to a validated previous Formula file"
    exit 1
fi

installed=0
cleanup() {
    if [[ "$installed" == "1" ]]; then
        brew uninstall subtap >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

SUBTAP_DIR="$HOME/.subtap"
for directory in models glossaries manuscripts jobs; do
    mkdir -p "$SUBTAP_DIR/$directory"
    printf 'preserve\n' > "$SUBTAP_DIR/$directory/acceptance-sentinel"
done

info "cold install"
brew install r-jed/tap/subtap
installed=1
subtap version
subtap tui --help >/dev/null

doctor_json="$(mktemp)"
doctor_status=0
subtap doctor --json >"$doctor_json" || doctor_status=$?
python3 - "$doctor_json" "$doctor_status" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
if payload.get("models_error"):
    raise SystemExit(f"doctor model check failed: {payload['models_error']}")
failed = [item["name"] for item in payload.get("checks", []) if not item.get("ok")]
config = payload.get("config", {})
if failed or not config.get("valid", False):
    raise SystemExit(f"doctor failed outside optional model state: checks={failed}, config={config}")
# A non-zero status is allowed only when the structured report shows that the
# runtime/config checks pass; missing models are reported separately.
if int(sys.argv[2]) and all(model.get("installed") for model in payload.get("models", [])):
    raise SystemExit("doctor returned non-zero without a missing model")
PY

if [[ "${SUBTAP_SKIP_FORMULA_AUDIT:-}" == "1" ]]; then
    info "strict formula validation already completed for the public candidate"
else
    info "strict formula validation"
    brew audit --strict r-jed/tap/subtap
fi
brew test r-jed/tap/subtap

info "prepare previous version"
brew uninstall subtap
installed=0
brew install "$PREVIOUS_FORMULA"
installed=1
previous_version="$(subtap version)"

info "upgrade previous version to candidate"
brew upgrade subtap
upgraded_version="$(subtap version)"
test "$upgraded_version" != "$previous_version" || {
    error "upgrade did not change the installed version"
    exit 1
}

info "rollback to previous version"
brew uninstall subtap
installed=0
brew install "$PREVIOUS_FORMULA"
installed=1
rollback_version="$(subtap version)"
test "$rollback_version" = "$previous_version" || {
    error "rollback did not restore the previous version"
    exit 1
}

info "final uninstall"
brew uninstall subtap
installed=0

for directory in models glossaries manuscripts jobs; do
    test -f "$SUBTAP_DIR/$directory/acceptance-sentinel" || {
        error "user data removed: $directory"
        exit 1
    }
done

info "all Homebrew acceptance checks passed"
