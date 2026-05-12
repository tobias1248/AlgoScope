#!/usr/bin/env python3
"""O(n) I/O-bound demo: create and write many small files."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    payload = b"AlgoScope file writer payload\n" * 64
    total = 0

    with tempfile.TemporaryDirectory(prefix="algoscope-writer-") as tmp:
        root = Path(tmp)
        for i in range(n):
            path = root / f"item-{i}.dat"
            fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
            try:
                total += os.write(fd, payload)
            finally:
                os.close(fd)

        for i in range(n):
            total += (root / f"item-{i}.dat").stat().st_size

    print(total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
