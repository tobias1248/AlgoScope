"""Sandbox runners for submitted Python programs."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from algoscope.probes import SyscallProbe, TimeProbe
from algoscope.web_models import RunStatus


STDERR_LIMIT = 1800


@dataclass(frozen=True)
class SandboxLimits:
    timeout_seconds: float
    memory_mb: int
    cpus: float = 1.0


@dataclass(frozen=True)
class SandboxRunResult:
    status: RunStatus
    wall_ms: float | None
    user_ms: float | None
    system_ms: float | None
    memory_kb: int | None
    syscall_count: int | None
    top_syscalls: list[tuple[str, int]]
    exit_code: int | None
    stderr_excerpt: str | None
    runner: str


class ProgramRunner(Protocol):
    name: str

    def run_timed(self, program: Path, size: int, limits: SandboxLimits) -> SandboxRunResult:
        ...

    def run_syscalls(self, program: Path, size: int, limits: SandboxLimits, mode: str) -> tuple[int | None, list[tuple[str, int]], str | None]:
        ...


def select_runner(mode: str, image: str = "algoscope-runner:latest") -> ProgramRunner:
    docker_available = shutil.which("docker") is not None
    if mode == "docker":
        return DockerSandboxRunner(image)
    if mode == "local":
        return LocalSandboxRunner(sys.executable)
    if docker_available:
        return DockerSandboxRunner(image)
    return LocalSandboxRunner(sys.executable)


class LocalSandboxRunner:
    """Development-only runner used when Docker is not installed."""

    name = "local-dev"

    def __init__(self, python_bin: str) -> None:
        self.python_bin = python_bin

    def run_timed(self, program: Path, size: int, limits: SandboxLimits) -> SandboxRunResult:
        command = [self.python_bin, str(program), str(size)]
        timed_command = command
        if Path("/usr/bin/time").exists():
            timed_command = ["/usr/bin/time", "-v", *command]

        start = time.perf_counter()
        proc = subprocess.Popen(
            timed_command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
            preexec_fn=_limit_child(limits),
        )
        try:
            _, stderr = proc.communicate(timeout=limits.timeout_seconds)
        except subprocess.TimeoutExpired:
            _kill_process_group(proc.pid)
            _, stderr = proc.communicate()
            return SandboxRunResult(
                status="timeout_killed",
                wall_ms=(time.perf_counter() - start) * 1000,
                user_ms=None,
                system_ms=None,
                memory_kb=None,
                syscall_count=None,
                top_syscalls=[],
                exit_code=None,
                stderr_excerpt=_excerpt(stderr),
                runner=self.name,
            )

        wall_ms = (time.perf_counter() - start) * 1000
        user_s = system_s = memory_kb = None
        if timed_command != command:
            user_s, system_s, memory_kb = TimeProbe._parse_time_output(stderr, "gnu")

        if proc.returncode == 0:
            return SandboxRunResult(
                status="ok",
                wall_ms=wall_ms,
                user_ms=user_s * 1000 if user_s is not None else None,
                system_ms=system_s * 1000 if system_s is not None else None,
                memory_kb=memory_kb,
                syscall_count=None,
                top_syscalls=[],
                exit_code=proc.returncode,
                stderr_excerpt=None,
                runner=self.name,
            )

        return SandboxRunResult(
            status=_classify_failure(proc.returncode, stderr),
            wall_ms=wall_ms,
            user_ms=user_s * 1000 if user_s is not None else None,
            system_ms=system_s * 1000 if system_s is not None else None,
            memory_kb=memory_kb,
            syscall_count=None,
            top_syscalls=[],
            exit_code=proc.returncode,
            stderr_excerpt=_excerpt(stderr),
            runner=self.name,
        )

    def run_syscalls(self, program: Path, size: int, limits: SandboxLimits, mode: str) -> tuple[int | None, list[tuple[str, int]], str | None]:
        if mode == "off":
            return None, [], None
        strace = shutil.which("strace")
        if not strace:
            if mode == "on":
                return None, [], "strace is not installed."
            return None, [], None

        command = [strace, "-c", self.python_bin, str(program), str(size)]
        proc = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
            preexec_fn=_limit_child(limits),
        )
        try:
            _, stderr = proc.communicate(timeout=limits.timeout_seconds)
        except subprocess.TimeoutExpired:
            _kill_process_group(proc.pid)
            _, stderr = proc.communicate()
            return None, [], "strace run timed out."
        if proc.returncode != 0:
            if mode == "on":
                return None, [], _excerpt(stderr)
            return None, [], None
        total, top = SyscallProbe._parse_summary(stderr)
        return total, top, None


class DockerSandboxRunner:
    """Runs submitted code in the AlgoScope Docker runner image."""

    name = "docker"

    def __init__(self, image: str) -> None:
        self.image = image

    def run_timed(self, program: Path, size: int, limits: SandboxLimits) -> SandboxRunResult:
        command = self._docker_command(program.parent, limits, ["/usr/bin/time", "-v", "python", "/src/solution.py", str(size)])
        start = time.perf_counter()
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                timeout=limits.timeout_seconds + 1,
            )
        except subprocess.TimeoutExpired as exc:
            return SandboxRunResult(
                status="timeout_killed",
                wall_ms=(time.perf_counter() - start) * 1000,
                user_ms=None,
                system_ms=None,
                memory_kb=None,
                syscall_count=None,
                top_syscalls=[],
                exit_code=None,
                stderr_excerpt=_excerpt(exc.stderr if isinstance(exc.stderr, str) else None),
                runner=self.name,
            )

        wall_ms = (time.perf_counter() - start) * 1000
        user_s, system_s, memory_kb = TimeProbe._parse_time_output(result.stderr, "gnu")
        if result.returncode == 0:
            status: RunStatus = "ok"
        else:
            status = _classify_failure(result.returncode, result.stderr)

        return SandboxRunResult(
            status=status,
            wall_ms=wall_ms,
            user_ms=user_s * 1000 if user_s is not None else None,
            system_ms=system_s * 1000 if system_s is not None else None,
            memory_kb=memory_kb,
            syscall_count=None,
            top_syscalls=[],
            exit_code=result.returncode,
            stderr_excerpt=None if status == "ok" else _excerpt(result.stderr),
            runner=self.name,
        )

    def run_syscalls(self, program: Path, size: int, limits: SandboxLimits, mode: str) -> tuple[int | None, list[tuple[str, int]], str | None]:
        if mode == "off":
            return None, [], None
        command = self._docker_command(program.parent, limits, ["strace", "-c", "python", "/src/solution.py", str(size)])
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                timeout=limits.timeout_seconds + 1,
            )
        except subprocess.TimeoutExpired:
            return None, [], "strace run timed out."
        if result.returncode != 0:
            if mode == "on":
                return None, [], _excerpt(result.stderr)
            return None, [], None
        total, top = SyscallProbe._parse_summary(result.stderr)
        return total, top, None

    def _docker_command(self, work_dir: Path, limits: SandboxLimits, inner_command: list[str]) -> list[str]:
        return [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--memory",
            f"{limits.memory_mb}m",
            "--cpus",
            str(limits.cpus),
            "--pids-limit",
            "64",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
            "--tmpfs",
            "/work:rw,noexec,nosuid,size=64m",
            "-v",
            f"{work_dir}:/src:ro",
            self.image,
            *inner_command,
        ]


def _limit_child(limits: SandboxLimits):
    def apply_limits() -> None:
        try:
            import resource

            memory_bytes = limits.memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
            cpu_seconds = max(1, int(limits.timeout_seconds) + 1)
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
        except Exception:
            pass

    return apply_limits


def _kill_process_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGTERM)
        time.sleep(0.1)
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _classify_failure(returncode: int | None, stderr: str | None) -> RunStatus:
    text = (stderr or "").lower()
    if returncode in {137, -9} or "killed" in text or "out of memory" in text or "memoryerror" in text:
        return "memory_killed"
    return "runtime_error"


def _excerpt(stderr: str | None) -> str | None:
    if not stderr:
        return None
    stripped = stderr.strip()
    if len(stripped) <= STDERR_LIMIT:
        return stripped
    return stripped[-STDERR_LIMIT:]
