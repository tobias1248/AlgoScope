#!/usr/bin/env python3
"""I/O-heavy demo: many small file writes and reads."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    checksum = 0
    with tempfile.TemporaryDirectory(prefix="algoscope-") as tmp:
        root = Path(tmp)
        for i in range(n):
            path = root / f"item-{i}.txt"
            payload = f"{i},{i * i}\n"
            path.write_text(payload, encoding="utf-8")
        for i in range(n):
            path = root / f"item-{i}.txt"
            checksum += len(path.read_text(encoding="utf-8"))
    print(checksum)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
