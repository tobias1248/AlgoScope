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
    "monster": {
        "program": ROOT / "examples" / "monster.py",
        "sizes": [100, 250, 500],
    },
}

COMPARISON_CASES = {
    "same-on": {
        "title": "Same O(n), Different OS Behavior",
        "slug": "same-on-os-behavior",
        "description": (
            "Both programs perform O(n) work, but one is CPU-bound while the other is I/O-bound. "
            "The comparison highlights user time, system time, memory usage, syscall count, and top syscalls."
        ),
        "sizes": [50, 100, 200, 400],
        "targets": [
            {
                "key": "cpu_loop",
                "label": "cpu_loop.py",
                "program": ROOT / "examples" / "cpu_loop.py",
                "expected_complexity": "O(n)",
                "interpretation": "CPU-bound: user-space arithmetic should dominate, with relatively low syscall activity.",
            },
            {
                "key": "file_writer",
                "label": "file_writer.py",
                "program": ROOT / "examples" / "file_writer.py",
                "expected_complexity": "O(n)",
                "interpretation": "I/O-bound: file creation and writes should increase system time and syscall activity.",
            },
        ],
    }
}
