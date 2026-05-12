#!/usr/bin/env python3
"""O(n^2) demo: bubble sort on reversed input."""

from __future__ import annotations

import sys


def bubble_sort(values: list[int]) -> None:
    n = len(values)
    for i in range(n):
        swapped = False
        for j in range(0, n - i - 1):
            if values[j] > values[j + 1]:
                values[j], values[j + 1] = values[j + 1], values[j]
                swapped = True
        if not swapped:
            break


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1_000
    values = list(range(n, 0, -1))
    bubble_sort(values)
    print(values[0] if values else 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
