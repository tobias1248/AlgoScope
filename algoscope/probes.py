"""OS-level runtime, memory, and syscall probes."""

from __future__ import annotations

import os
import platform
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

from algoscope.models import Measurement, ProbeCommand, RunResult
from algoscope.utils import optional_median_float, optional_median_int, safe_float, safe_int


class TimeProbe:
    """Measure target process wall time, CPU time, and peak RSS."""

    def __init__(self, python_bin: str) -> None:
        self.python_bin = python_bin
        self.style = self._detect_style()

    @property
    def tool_name(self) -> str:
        return self.style or "unavailable"

    def command_notes(self, program: Path) -> list[ProbeCommand]:
        target = f"{self.python_bin} {program} <n>"
        notes = [
            ProbeCommand(
                title="Target process",
                command=target,
                purpose="Launches the student's program once per input size.",
                os_concept="Process creation",
                status="used",
            )
        ]
        if self.style == "gnu":
            notes.append(
                ProbeCommand(
                    title="GNU time",
                    command=f"/usr/bin/time -v {target}",
                    purpose="Collects user CPU time, system CPU time, elapsed time, and maximum resident set size.",
                    os_concept="CPU accounting and memory management",
                    status="used",
                )
            )
        elif self.style == "bsd":
            notes.append(
                ProbeCommand(
                    title="BSD time",
                    command=f"/usr/bin/time -l {target}",
                    purpose="Collects CPU time and resident memory on BSD/macOS-like systems.",
                    os_concept="CPU accounting and memory management",
                    status="used",
                )
            )
        elif self.style == "wait4":
            notes.append(
                ProbeCommand(
                    title="wait4 fallback",
                    command="os.wait4(child_pid, 0)",
                    purpose="Reads kernel resource usage for the child process when /usr/bin/time is unavailable or restricted.",
                    os_concept="Process lifecycle and resource accounting",
                    status="used fallback",
                )
            )
        else:
            notes.append(
                ProbeCommand(
                    title="Time probe",
                    command="/usr/bin/time -v or os.wait4(child_pid, 0)",
                    purpose="Would collect CPU time and peak RSS, but no supported probe was found.",
                    os_concept="CPU accounting and memory management",
                    status="unavailable",
                )
            )
        return notes

    def run(self, program: Path, size: int) -> RunResult:
        command = [self.python_bin, str(program), str(size)]

        if self.style == "wait4":
            return self._run_with_wait4(command)

        timed_command = command
        if self.style:
            flag = "-v" if self.style == "gnu" else "-l"
            timed_command = ["/usr/bin/time", flag, *command]

        start = time.perf_counter()
        result = subprocess.run(timed_command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        wall_s = time.perf_counter() - start

        if result.returncode != 0:
            raise RuntimeError(f"{program} failed for n={size}:\n{result.stderr.strip()}")

        user_s = system_s = memory_kb = None
        if self.style:
            user_s, system_s, memory_kb = self._parse_time_output(result.stderr, self.style)

        return RunResult(
            wall_ms=wall_s * 1000,
            user_ms=user_s * 1000 if user_s is not None else None,
            system_ms=system_s * 1000 if system_s is not None else None,
            memory_kb=memory_kb,
        )

    def _detect_style(self) -> str | None:
        time_bin = Path("/usr/bin/time")
        if time_bin.exists():
            probe = [str(time_bin), "-v", sys.executable, "-c", "pass"]
            result = subprocess.run(probe, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            if "Maximum resident set size" in result.stderr:
                return "gnu"

            probe = [str(time_bin), "-l", sys.executable, "-c", "pass"]
            result = subprocess.run(probe, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            if "maximum resident set size" in result.stderr.lower():
                return "bsd"

        if hasattr(os, "wait4"):
            return "wait4"
        return None

    @staticmethod
    def _parse_time_output(stderr: str, style: str) -> tuple[float | None, float | None, int | None]:
        user_s = system_s = None
        memory_kb = None

        if style == "gnu":
            for line in stderr.splitlines():
                if "User time (seconds):" in line:
                    user_s = safe_float(line.rsplit(":", 1)[1])
                elif "System time (seconds):" in line:
                    system_s = safe_float(line.rsplit(":", 1)[1])
                elif "Maximum resident set size (kbytes):" in line:
                    memory_kb = safe_int(line.rsplit(":", 1)[1])
        elif style == "bsd":
            for line in stderr.splitlines():
                stripped = line.strip()
                tokens = stripped.split()
                if stripped.endswith("maximum resident set size"):
                    bytes_value = safe_int(tokens[0])
                    memory_kb = bytes_value // 1024 if bytes_value is not None else None
                if "user" in tokens:
                    user_s = safe_float(tokens[tokens.index("user") - 1])
                if "sys" in tokens:
                    system_s = safe_float(tokens[tokens.index("sys") - 1])

        return user_s, system_s, memory_kb

    @staticmethod
    def _run_with_wait4(command: list[str]) -> RunResult:
        start = time.perf_counter()
        proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        _, status, usage = os.wait4(proc.pid, 0)
        wall_s = time.perf_counter() - start
        stderr = proc.stderr.read() if proc.stderr else ""
        returncode = os.waitstatus_to_exitcode(status)
        if returncode != 0:
            raise RuntimeError(f"{' '.join(command)} failed:\n{stderr.strip()}")

        memory_kb = int(usage.ru_maxrss // 1024) if platform.system() == "Darwin" else int(usage.ru_maxrss)
        return RunResult(
            wall_ms=wall_s * 1000,
            user_ms=usage.ru_utime * 1000,
            system_ms=usage.ru_stime * 1000,
            memory_kb=memory_kb,
        )


class SyscallProbe:
    """Collect syscall counts with strace when it is available."""

    def __init__(self, python_bin: str, mode: str) -> None:
        self.python_bin = python_bin
        self.mode = mode
        self.strace_path = shutil.which("strace")

    def command_notes(self, program: Path) -> list[ProbeCommand]:
        target = f"{self.python_bin} {program} <n>"
        status = "used" if self.strace_path and self.mode != "off" else "unavailable"
        if self.mode == "off":
            status = "disabled"
        return [
            ProbeCommand(
                title="strace syscall summary",
                command=f"strace -c {target}",
                purpose="Counts syscall activity such as read, write, openat, mmap, and brk.",
                os_concept="System calls and I/O overhead",
                status=status,
            )
        ]

    def run(self, program: Path, size: int) -> tuple[int | None, list[tuple[str, int]]]:
        if self.mode == "off":
            return None, []

        if not self.strace_path:
            if self.mode == "on":
                raise RuntimeError("strace was requested, but it is not available on this system.")
            return None, []

        command = [self.strace_path, "-c", self.python_bin, str(program), str(size)]
        result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            if self.mode == "on":
                raise RuntimeError(f"strace failed for n={size}:\n{result.stderr.strip()}")
            return None, []

        return self._parse_summary(result.stderr)

    @staticmethod
    def _parse_summary(stderr: str) -> tuple[int | None, list[tuple[str, int]]]:
        rows: list[tuple[str, int]] = []
        total = None
        for raw_line in stderr.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("%") or line.startswith("-"):
                continue
            parts = line.split()
            if parts[-1] == "total":
                numbers = [safe_int(p) for p in parts[:-1]]
                numbers = [n for n in numbers if n is not None]
                if numbers:
                    total = numbers[-2] if len(numbers) >= 2 else numbers[-1]
                continue
            syscall = parts[-1]
            numbers = [safe_int(p) for p in parts[:-1]]
            numbers = [n for n in numbers if n is not None]
            if not numbers:
                continue
            calls = numbers[-2] if len(numbers) >= 2 and len(parts) >= 6 else numbers[-1]
            rows.append((syscall, calls))

        if total is None and rows:
            total = sum(calls for _, calls in rows)
        rows.sort(key=lambda item: item[1], reverse=True)
        return total, rows[:5]


class MeasurementCollector:
    """Coordinate resource probes across all input sizes."""

    def __init__(self, python_bin: str, syscall_mode: str) -> None:
        self.time_probe = TimeProbe(python_bin)
        self.syscall_probe = SyscallProbe(python_bin, syscall_mode)

    def collect(self, program: Path, sizes: list[int], repeats: int) -> tuple[list[Measurement], dict[str, object]]:
        metadata: dict[str, object] = {
            "platform": platform.platform(),
            "python": self.time_probe.python_bin,
            "time_tool": self.time_probe.tool_name,
            "strace": self.syscall_probe.strace_path or "unavailable",
            "probe_commands": [command.__dict__ for command in self.command_notes(program)],
        }

        rows: list[Measurement] = []
        for size in sizes:
            timed_runs = [self.time_probe.run(program, size) for _ in range(repeats)]
            syscall_count, top_syscalls = self.syscall_probe.run(program, size)
            rows.append(
                Measurement(
                    size=size,
                    wall_ms=statistics.median(run.wall_ms for run in timed_runs),
                    user_ms=optional_median_float([run.user_ms for run in timed_runs]),
                    system_ms=optional_median_float([run.system_ms for run in timed_runs]),
                    memory_kb=optional_median_int([run.memory_kb for run in timed_runs]),
                    syscall_count=syscall_count,
                    top_syscalls=top_syscalls,
                )
            )
        return rows, metadata

    def command_notes(self, program: Path) -> list[ProbeCommand]:
        return [*self.time_probe.command_notes(program), *self.syscall_probe.command_notes(program)]
