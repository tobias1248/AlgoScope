"""Comparison workflows for OS-level behavior across programs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from algoscope.config import COMPARISON_CASES
from algoscope.models import ComparisonReport, ComparisonTarget, ComparisonTargetResult
from algoscope.probes import MeasurementCollector


class ComparisonRunner:
    """Run a named comparison case across multiple target programs."""

    def __init__(self, python_bin: str, syscall_mode: str) -> None:
        self.python_bin = python_bin
        self.syscall_mode = syscall_mode

    def run(self, case_name: str, sizes: list[int] | None, repeats: int) -> ComparisonReport:
        if case_name not in COMPARISON_CASES:
            raise SystemExit(f"Unknown comparison case: {case_name}")

        case = COMPARISON_CASES[case_name]
        selected_sizes = sizes or list(case["sizes"])
        if not selected_sizes or any(size <= 0 for size in selected_sizes):
            raise SystemExit("Comparison sizes must be positive integers.")

        results: list[ComparisonTargetResult] = []
        for target_data in case["targets"]:
            target = self._target_from_config(target_data)
            if not target.program.exists():
                raise SystemExit(f"Comparison program not found: {target.program}")
            collector = MeasurementCollector(self.python_bin, self.syscall_mode)
            measurements, metadata = collector.collect(target.program, selected_sizes, repeats)
            results.append(
                ComparisonTargetResult(
                    target=target,
                    measurements=measurements,
                    metadata=metadata,
                )
            )

        return ComparisonReport(
            title=str(case["title"]),
            slug=str(case["slug"]),
            description=str(case["description"]),
            sizes=selected_sizes,
            results=results,
        )

    @staticmethod
    def _target_from_config(target_data: dict[str, Any]) -> ComparisonTarget:
        return ComparisonTarget(
            key=str(target_data["key"]),
            label=str(target_data["label"]),
            program=Path(target_data["program"]).expanduser().resolve(),
            expected_complexity=str(target_data["expected_complexity"]),
            interpretation=str(target_data["interpretation"]),
        )

