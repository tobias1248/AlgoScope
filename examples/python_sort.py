#!/usr/bin/env python3
"""O(n log n) demo: Python's built-in Timsort."""

from __future__ import annotations

import sys


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    modulus = max(n * 3 + 1, 2)
    values = [(i * 1_103_515_245 + 12_345) % modulus for i in range(n)]
    values.sort()
    print((values[0] + values[-1]) if values else 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
