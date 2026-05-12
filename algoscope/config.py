"""Project-level configuration and built-in demo cases."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

DEMO_CASES = {
    "linear_search": {
        "program": ROOT / "examples" / "linear_search.py",
        "sizes": [20_000, 60_000, 120_000, 220_000, 360_000],
    },
    "bubble_sort": {
        "program": ROOT / "examples" / "bubble_sort.py",
        "sizes": [100, 250, 500, 800, 1_200],
    },
    "python_sort": {
        "program": ROOT / "examples" / "python_sort.py",
        "sizes": [50_000, 120_000, 250_000, 500_000, 900_000],
    },
    "io_heavy": {
        "program": ROOT / "examples" / "io_heavy.py",
        "sizes": [100, 250, 500, 1_000, 2_000],
    },
}

