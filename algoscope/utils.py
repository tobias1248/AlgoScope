"""Small parsing and formatting helpers."""

from __future__ import annotations

import statistics


def safe_float(value: str) -> float | None:
    try:
        return float(value.strip())
    except ValueError:
        return None


def safe_int(value: str) -> int | None:
    try:
        return int(value.strip())
    except ValueError:
        return None


def optional_median_float(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return statistics.median(present)


def optional_median_int(values: list[int | None]) -> int | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return int(statistics.median(present))


def fmt_ms(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.2f}"


def fmt_int(value: int | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:,}"

