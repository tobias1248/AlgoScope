"""Web-first analysis workflow for submitted programs."""

from __future__ import annotations

import platform
import statistics
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from algoscope.complexity import ComplexityEstimator
from algoscope.models import Measurement
from algoscope.sandbox import SandboxLimits, SandboxRunResult, select_runner
from algoscope.summary import LlmSummaryService
from algoscope.web_models import AnalysisRequest, AnalysisResult, RepeatRun, WebMeasurement


class AnalysisService:
    """Run submitted Python code and return JSON-friendly analysis data."""

    def __init__(self) -> None:
        self.estimator = ComplexityEstimator()

    def run(self, request: AnalysisRequest) -> AnalysisResult:
        self._validate(request)
        limits = SandboxLimits(timeout_seconds=request.timeout_seconds, memory_mb=request.memory_mb)
        runner = select_runner(request.runner)

        with tempfile.TemporaryDirectory(prefix="algoscope-") as tmp:
            program = Path(tmp) / "solution.py"
            program.write_text(request.code, encoding="utf-8")

            rows = [self._measure_size(runner, program, size, request.repeats, limits, request.syscalls) for size in request.sizes]

            complexity_rows = [
                Measurement(
                    size=row.size,
                    wall_ms=row.wall_ms or 0.0,
                    user_ms=row.user_ms,
                    system_ms=row.system_ms,
                    memory_kb=row.memory_kb,
                    syscall_count=row.syscall_count,
                    top_syscalls=row.top_syscalls,
                )
                for row in rows
                if row.status in {"ok", "probe_failed"} and row.wall_ms is not None
            ]

            if len(complexity_rows) >= 2:
                estimate, scores = self.estimator.estimate(complexity_rows)
            else:
                estimate, scores = "insufficient_data", []

            metadata: dict[str, Any] = {
                "platform": platform.platform(),
                "runner": runner.name,
                "runner_warning": (
                    "Local development runner is active because Docker was not selected or not found. "
                    "Do not use local mode for untrusted public submissions."
                    if runner.name == "local-dev"
                    else None
                ),
                "timeout_seconds": request.timeout_seconds,
                "memory_mb": request.memory_mb,
                "sizes": request.sizes,
                "repeats": request.repeats,
                "syscalls": request.syscalls,
                "successful_measurements": len(complexity_rows),
            }

            summary = None
            if complexity_rows:
                summary = LlmSummaryService(request.llm_summary, timeout_seconds=25.0).generate(
                    program, complexity_rows, estimate, scores, metadata
                )

            return AnalysisResult(
                status="completed",
                estimated_complexity=estimate,
                measurements=rows,
                model_scores=scores,
                summary=summary,
                metadata=metadata,
            )

    @staticmethod
    def _validate(request: AnalysisRequest) -> None:
        if not request.code.strip():
            raise ValueError("Code is required.")
        if not request.sizes or any(size <= 0 for size in request.sizes):
            raise ValueError("Sizes must be positive integers.")
        if len(request.sizes) > 8:
            raise ValueError("At most 8 input sizes are allowed in the demo.")
        if request.repeats < 1 or request.repeats > 5:
            raise ValueError("Repeats must be between 1 and 5.")
        if request.timeout_seconds < 0.25 or request.timeout_seconds > 30:
            raise ValueError("Timeout must be between 0.25 and 30 seconds.")
        if request.memory_mb < 64 or request.memory_mb > 2048:
            raise ValueError("Memory limit must be between 64 and 2048 MB.")

    def _measure_size(
        self,
        runner,
        program: Path,
        size: int,
        repeats: int,
        limits: SandboxLimits,
        syscall_mode: str,
    ) -> WebMeasurement:
        timed_runs = [runner.run_timed(program, size, limits) for _ in range(repeats)]
        ok_runs = [run for run in timed_runs if run.status == "ok" and run.wall_ms is not None]
        syscall_count = None
        top_syscalls: list[tuple[str, int]] = []
        syscall_error = None

        if ok_runs:
            syscall_count, top_syscalls, syscall_error = runner.run_syscalls(program, size, limits, syscall_mode)

        if ok_runs:
            status = "ok" if syscall_error is None else "probe_failed"
            return WebMeasurement(
                size=size,
                status=status,
                wall_ms=statistics.median(run.wall_ms for run in ok_runs if run.wall_ms is not None),
                user_ms=_median_optional([run.user_ms for run in ok_runs]),
                system_ms=_median_optional([run.system_ms for run in ok_runs]),
                memory_kb=_median_optional_int([run.memory_kb for run in ok_runs]),
                syscall_count=syscall_count,
                top_syscalls=top_syscalls,
                stderr_excerpt=syscall_error,
                repeats=[_repeat(run) for run in timed_runs],
            )

        first = timed_runs[0]
        return WebMeasurement(
            size=size,
            status=first.status,
            wall_ms=first.wall_ms,
            user_ms=first.user_ms,
            system_ms=first.system_ms,
            memory_kb=first.memory_kb,
            syscall_count=None,
            top_syscalls=[],
            exit_code=first.exit_code,
            stderr_excerpt=first.stderr_excerpt,
            repeats=[_repeat(run) for run in timed_runs],
        )


def _repeat(run: SandboxRunResult) -> RepeatRun:
    return RepeatRun(
        status=run.status,
        wall_ms=run.wall_ms,
        user_ms=run.user_ms,
        system_ms=run.system_ms,
        memory_kb=run.memory_kb,
        exit_code=run.exit_code,
        stderr_excerpt=run.stderr_excerpt,
        runner=run.runner,
    )


def _median_optional(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return statistics.median(present) if present else None


def _median_optional_int(values: list[int | None]) -> int | None:
    present = [value for value in values if value is not None]
    return int(statistics.median(present)) if present else None
