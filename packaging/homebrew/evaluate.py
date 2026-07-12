"""Select the sole Homebrew distribution carrier by fixed rules.

Rules (fixed priority, not configurable):
1. cold_install, python_hidden, rollback, audit — all must be True (hard gates)
2. Only carriers passing all hard gates qualify
3. Among qualified, prefer smaller installed_bytes
4. Ties broken by: Formula > Cask > launcher
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Hard-gate fields — every one must be True for a carrier to qualify.
_GATES = ("cold_install", "python_hidden", "rollback", "audit")

# Fixed tie-break order: earlier index wins.
_PRIORITY = ("formula", "cask", "launcher")


def select(results: list[dict]) -> str | None:
    """Return the name of the selected carrier, or None if none qualify.

    *results* is a list of dicts, each with keys:
        carrier, cold_install, python_hidden, rollback, audit, installed_bytes
    """
    # Phase 1: filter by hard gates
    qualified = [r for r in results if all(r.get(g) for g in _GATES)]

    if not qualified:
        return None

    # Phase 2: sort by installed_bytes ascending, then by priority
    def _sort_key(r: dict) -> tuple[int, int]:
        name = r["carrier"]
        try:
            prio = _PRIORITY.index(name)
        except ValueError:
            prio = len(_PRIORITY)  # unknown carriers sort last
        return (r.get("installed_bytes", 0), prio)

    qualified.sort(key=_sort_key)
    return qualified[0]["carrier"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_output(
    results: list[dict],
) -> dict:
    """Build the JSON output structure."""
    qualified_names = [
        r["carrier"]
        for r in results
        if all(r.get(g) for g in _GATES)
    ]
    rejected: dict[str, list[str]] = {}
    for r in results:
        name = r["carrier"]
        if name in qualified_names:
            continue
        failed_gates = [g for g in _GATES if not r.get(g)]
        rejected[name] = failed_gates

    selected = select(results)

    return {
        "selected": selected,
        "qualified": qualified_names,
        "rejected": rejected,
    }


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]

    print_selected_path = False
    args: list[str] = []
    for arg in argv:
        if arg == "--print-selected-path":
            print_selected_path = True
        else:
            args.append(arg)

    if not args:
        print("Usage: evaluate.py [--print-selected-path] result1.json [result2.json ...]", file=sys.stderr)
        sys.exit(2)

    results: list[dict] = []
    for path in args:
        with open(path) as f:
            results.append(json.load(f))

    output = _build_output(results)

    if output["selected"] is None:
        print(json.dumps(output, indent=2))
        sys.exit(1)

    print(json.dumps(output, indent=2))

    if print_selected_path:
        # Find the path that corresponds to the selected carrier
        selected = output["selected"]
        for path, result in zip(args, results):
            if result.get("carrier") == selected:
                print(path)
                break


if __name__ == "__main__":
    main()
