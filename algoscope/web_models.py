"""Web-facing analysis contracts for the AlgoScope demo app."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from algoscope.models import ComplexityScore
from algoscope.summary import ReportSummary


SyscallMode = Literal["auto", "on", "off"]
SummaryMode = Literal["off", "auto", "on"]
RunnerMode = Literal["auto", "docker", "local"]
RunStatus = Literal["ok", "timeout_killed", "memory_killed", "runtime_error", "probe_failed"]


@dataclass(frozen=True)
class AnalysisRequest:
    code: str
    sizes: list[int]
    repeats: int = 3
    syscalls: SyscallMode = "auto"
    timeout_seconds: float = 5.0
    memory_mb: int = 256
    llm_summary: SummaryMode = "auto"
    runner: RunnerMode = "auto"


@dataclass(frozen=True)
class RepeatRun:
    status: RunStatus
    wall_ms: float | None
    user_ms: float | None
    system_ms: float | None
    memory_kb: int | None
    exit_code: int | None
    stdout_excerpt: str | None
    stderr_excerpt: str | None
    runner: str


@dataclass(frozen=True)
class WebMeasurement:
    size: int
    status: RunStatus
    wall_ms: float | None
    user_ms: float | None
    system_ms: float | None
    memory_kb: int | None
    syscall_count: int | None
    top_syscalls: list[tuple[str, int]]
    exit_code: int | None = None
    stdout_excerpt: str | None = None
    stderr_excerpt: str | None = None
    repeats: list[RepeatRun] = field(default_factory=list)


@dataclass(frozen=True)
class AnalysisResult:
    status: Literal["completed", "failed"]
    estimated_complexity: str
    measurements: list[WebMeasurement]
    model_scores: list[ComplexityScore]
    summary: ReportSummary | None
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "estimated_complexity": self.estimated_complexity,
            "measurements": [asdict(row) for row in self.measurements],
            "model_scores": [asdict(score) for score in self.model_scores],
            "summary": asdict(self.summary) if self.summary else None,
            "metadata": self.metadata,
        }
