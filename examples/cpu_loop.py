#!/usr/bin/env python3
"""O(n) CPU-bound demo: fixed arithmetic work per input item."""

from __future__ import annotations

import sys


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    acc = 0x12345678
    for i in range(n):
        value = i + 1
        for _ in range(8_000):
            acc = (acc * 1_664_525 + value + 1_013_904_223) & 0xFFFFFFFF
    print(acc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
