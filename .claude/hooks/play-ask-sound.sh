#!/bin/bash
# Play a short prompt sound when Claude needs user confirmation.
# Backgrounded to avoid blocking the hook chain.
# Env override: SUBTAP_ASK_SOUND=/path/to/sound.aiff

# Drain stdin (Claude Code passes JSON event payload; we don't need it).
cat >/dev/null

# Default to macOS Frog.aiff; override via SUBTAP_ASK_SOUND env.
SOUND="${SUBTAP_ASK_SOUND:-/System/Library/Sounds/Frog.aiff}"

# macOS: afplay. Linux: paplay. Other: noop.
if [ "$(uname)" = "Darwin" ] && [ -f "$SOUND" ]; then
  afplay "$SOUND" >/dev/null 2>&1 &
  disown
elif [ "$(uname)" = "Linux" ] && command -v paplay >/dev/null 2>&1; then
  paplay "$SOUND" >/dev/null 2>&1 &
  disown
fi

exit 0