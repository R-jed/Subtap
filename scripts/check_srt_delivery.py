#!/usr/bin/env python3
"""Check SRT files against Subtap delivery-quality rules."""

from __future__ import annotations

from pathlib import Path
import sys

from subtap.core.subtitle_quality import validate_srt_delivery


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: check_srt_delivery.py <file.srt> [...]", file=sys.stderr)
        return 2

    failed = False
    for arg in args:
        path = Path(arg)
        report = validate_srt_delivery(path.read_text(encoding="utf-8"))
        if not report.ok:
            print(f"{path}: {report}", file=sys.stderr)
            failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
