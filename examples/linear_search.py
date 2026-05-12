#!/usr/bin/env python3
"""O(n) demo: worst-case linear search."""

from __future__ import annotations

import sys


def linear_search(values: list[int], target: int) -> bool:
    for value in values:
        if value == target:
            return True
    return False


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    values = list(range(n))
    hits = 0
    for _ in range(40):
        hits += int(linear_search(values, -1))
    print(hits)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
