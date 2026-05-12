"""Typed data objects shared across AlgoScope modules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Measurement:
    size: int
    wall_ms: float
    user_ms: float | None
    system_ms: float | None
    memory_kb: int | None
    syscall_count: int | None
    top_syscalls: list[tuple[str, int]]


@dataclass(frozen=True)
class RunResult:
    wall_ms: float
    user_ms: float | None
    system_ms: float | None
    memory_kb: int | None


@dataclass(frozen=True)
class ComplexityScore:
    name: str
    a: float
    b: float
    rmse: float
    normalized_rmse: float


@dataclass(frozen=True)
class ProbeCommand:
    title: str
    command: str
    purpose: str
    os_concept: str
    status: str

