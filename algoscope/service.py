"""Web-first analysis workflow for submitted programs."""

from __future__ import annotations

import platform
import statistics
import tempfile
from pathlib import Path
from typing import Any

from algoscope.complexity import ComplexityEstimator
from algoscope.config import RUNTIME_DIR
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

        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="algoscope-", dir=RUNTIME_DIR) as tmp:
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

            warnings = _analysis_warnings(rows, complexity_rows, runner.name)

            metadata: dict[str, Any] = {
                "platform": platform.platform(),
                "runner": runner.name,
                "runner_warning": (
                    "Isolation fallback is active. Use only trusted code in this mode."
                    if runner.name == "local-dev"
                    else None
                ),
                "timeout_seconds": request.timeout_seconds,
                "memory_mb": request.memory_mb,
                "sizes": request.sizes,
                "repeats": request.repeats,
                "syscalls": request.syscalls,
                "successful_measurements": len(complexity_rows),
                "confidence": "low" if warnings else "medium",
                "warnings": warnings,
                "local_observations": _local_observations(rows, estimate),
                "syscall_explanations": _syscall_explanations(rows),
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
                stdout_excerpt=_first_present([run.stdout_excerpt for run in ok_runs]),
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
            stdout_excerpt=first.stdout_excerpt,
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
        stdout_excerpt=run.stdout_excerpt,
        stderr_excerpt=run.stderr_excerpt,
        runner=run.runner,
    )


def _median_optional(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return statistics.median(present) if present else None


def _median_optional_int(values: list[int | None]) -> int | None:
    present = [value for value in values if value is not None]
    return int(statistics.median(present)) if present else None


def _first_present(values: list[str | None]) -> str | None:
    return next((value for value in values if value), None)


def _analysis_warnings(rows: list[WebMeasurement], complexity_rows: list[Measurement], runner_name: str) -> list[str]:
    warnings: list[str] = []
    if len(complexity_rows) < 3:
        warnings.append("Big O fit has low confidence because fewer than three successful measurements are available.")

    cpu_times = [row.user_ms for row in rows if row.status in {"ok", "probe_failed"} and row.user_ms is not None]
    if cpu_times and max(cpu_times) < 50:
        warnings.append(
            "Measured user CPU time is very small, so startup and measurement overhead may dominate the observed Big O fit."
        )

    if runner_name == "docker":
        wall_times = [row.wall_ms for row in rows if row.status in {"ok", "probe_failed"} and row.wall_ms is not None]
        user_times = [row.user_ms for row in rows if row.status in {"ok", "probe_failed"} and row.user_ms is not None]
        if wall_times and user_times and max(user_times) * 4 < max(wall_times):
            warnings.append("Wall time is much larger than user CPU time, which indicates sandbox startup overhead is significant.")

    abnormal = [row for row in rows if row.status not in {"ok", "probe_failed"}]
    if abnormal:
        warnings.append("Some input sizes did not complete normally; Big O is estimated only from successful measurements.")

    return warnings


def _local_observations(rows: list[WebMeasurement], estimate: str) -> list[str]:
    observations: list[str] = []
    if estimate != "insufficient_data":
        observations.append(f"Observed growth best matches {estimate}; this is a measurement fit, not a formal proof.")

    abnormal = [row for row in rows if row.status not in {"ok", "probe_failed"}]
    if abnormal:
        sizes = ", ".join(str(row.size) for row in abnormal[:4])
        observations.append(f"Abnormal execution was detected at input size(s): {sizes}. Check status and stderr details.")

    syscall_rows = [row for row in rows if row.syscall_count is not None]
    if syscall_rows:
        latest = syscall_rows[-1]
        top = ", ".join(name for name, _ in latest.top_syscalls[:3])
        observations.append(f"Latest syscall sample counted {latest.syscall_count} calls; top syscalls include {top or 'n/a'}.")

    memory_rows = [row for row in rows if row.memory_kb is not None]
    if len(memory_rows) >= 2 and memory_rows[-1].memory_kb and memory_rows[0].memory_kb:
        growth = memory_rows[-1].memory_kb / max(memory_rows[0].memory_kb, 1)
        if growth >= 2:
            observations.append(f"Peak RSS increased by about {growth:.1f}x across the measured range.")

    if not observations:
        observations.append("Run completed, but measurements are too small or sparse for a strong interpretation.")
    return observations


_SYSCALL_MEANINGS: dict[str, tuple[str, str]] = {
    "read": ("Reads bytes from a file descriptor.", "Frequent reads usually indicate file, pipe, or interpreter/module loading activity."),
    "write": ("Writes bytes to a file descriptor.", "Frequent writes point to stdout, logging, or file-output-heavy behavior."),
    "open": ("Opens a filesystem path.", "Path opens indicate file access or dynamic runtime/library loading."),
    "openat": ("Opens a path relative to a directory file descriptor.", "Many openat calls usually mean filesystem lookup, imports, temp files, or I/O workload."),
    "close": ("Releases a file descriptor.", "Close calls tend to track file/socket lifecycle and cleanup."),
    "newfstatat": ("Reads metadata for a path.", "High counts often come from module lookup, filesystem checks, or file-heavy workloads."),
    "fstat": ("Reads metadata for an open file descriptor.", "This often accompanies file reads/writes or interpreter startup checks."),
    "stat": ("Reads filesystem metadata.", "Stat-heavy traces indicate path probing or file existence checks."),
    "lseek": ("Moves or checks the current file offset.", "Lseek often appears around buffered file reads and Python runtime file handling."),
    "mmap": ("Maps files or anonymous memory into the process address space.", "Mmap reflects interpreter/library loading and memory allocation behavior."),
    "munmap": ("Unmaps a memory region.", "Munmap shows cleanup of mapped files or memory regions."),
    "brk": ("Moves the process heap boundary.", "Brk activity points to heap allocation pressure."),
    "ioctl": ("Sends a device-specific control request.", "Ioctl often appears from terminal, file descriptor, or runtime environment checks."),
    "getdents64": ("Reads directory entries.", "Directory scanning usually appears during imports or file discovery."),
    "execve": ("Starts a new program image.", "Execve is process launch; it marks program startup."),
    "clone": ("Creates a thread or process.", "Clone indicates concurrency or runtime-managed helper threads/processes."),
    "futex": ("Waits or wakes userspace locks through the kernel.", "Futex activity points to thread synchronization or runtime locking."),
}


def _syscall_explanations(rows: list[WebMeasurement]) -> list[dict[str, object]]:
    latest = next((row for row in reversed(rows) if row.top_syscalls), None)
    if latest is None:
        return []
    explanations = []
    for name, calls in latest.top_syscalls:
        meaning, signal = _SYSCALL_MEANINGS.get(
            name,
            ("Kernel service requested by the process.", "Interpret this syscall together with the program code and resource trends."),
        )
        explanations.append({"name": name, "calls": calls, "meaning": meaning, "signal": signal})
    return explanations
