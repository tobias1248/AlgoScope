"""OS-level runtime, memory, and syscall probes with an Active Auditing Watchdog."""

from __future__ import annotations

import os
import platform
import shutil
import statistics
import subprocess
import sys
import time
import threading
import signal
from pathlib import Path

# 注意：請確保環境中已安裝 psutil (pip install psutil)
import psutil

from algoscope.models import Measurement, ProbeCommand, RunResult
from algoscope.utils import optional_median_float, optional_median_int, safe_float, safe_int


class TimeProbe:
    """Measure target process wall time, CPU time, and peak RSS with Watchdog support."""

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

    def _watchdog_worker(self, pid: int, mode: str, kill_event: threading.Event, stop_event: threading.Event):
        """背景看門狗執行緒：每 0.05 秒檢查子行程狀態，爆表就主動 Kill 掉"""
        try:
            proc = psutil.Process(pid)
            
            # 🌟 修正1：重新調整資源閾值
            # Eco 模式：嚴格節能，限制 CPU 60% 與 記憶體 150MB
            # Normal 模式：完全放行 CPU 讓常規演算法滿載狂飆，將 CPU 門檻設為無限大 (999.0)，記憶體設 2GB 作為防自焚底線
            cpu_limit = 60.0 if mode == "eco" else 999.0
            mem_limit_mb = 150.0 if mode == "eco" else 2048.0

            # 預熱 psutil 的 cpu_percent
            proc.cpu_percent(interval=None)
            
            while not stop_event.is_set() and proc.is_running():
                # 取得即時資源狀態
                cpu_usage = proc.cpu_percent(interval=None)
                mem_mb = proc.memory_info().rss / (1024 * 1024)

                if cpu_usage > cpu_limit or mem_mb > mem_limit_mb:
                    print(f"\n🚨 [Watchdog Alert - {mode.upper()} MODE]")
                    print(f"⚠️  PID {pid} Exceeded Quota! CPU: {cpu_usage}%, MEM: {mem_mb:.1f} MB")
                    print(f"🛑 [OS Action] Sending SIGKILL to process tree to prevent system thrashing...")
                    
                    # 🌟 修正2：採用行程樹全數撲殺（Kill Process Tree）連坐法，防止外層監測工具卡死
                    try:
                        parent = proc.parent()
                        
                        # 先宰了作怪的目標 Python 子行程
                        proc.kill()
                        
                        # 如果外層包著 /usr/bin/time 或 strace 且不是主程式，一併強制清理
                        if parent and parent.pid != os.getpid():
                            parent.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        # 備用防線：如果 psutil 抓失敗，改用 os.kill 跨平台安全訊號
                        try:
                            if platform.system() == "Windows":
                                os.kill(pid, signal.SIGTERM)
                            else:
                                os.kill(pid, getattr(signal, "SIGKILL", 9))
                        except ProcessLookupError:
                            pass
                    
                    kill_event.set()
                    break
                time.sleep(0.05)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    def run(self, program: Path, size: int, mode: str = "normal") -> RunResult:
        command = [self.python_bin, str(program), str(size)]

        # 如果是在 Windows 或不支援 time tool 的環境使用 wait4/Popen 核心
        if self.style == "wait4" or self.style is None:
            return self._run_with_watchdog_core(command, mode)

        flag = "-v" if self.style == "gnu" else "-l"
        timed_command = ["/usr/bin/time", flag, *command]
        return self._run_with_watchdog_core(timed_command, mode, is_wrapped=True)

    def _run_with_watchdog_core(self, full_command: list[str], mode: str, is_wrapped: bool = False) -> RunResult:
        """核心執行邏輯：非同步啟動行程並配置看門狗守護"""
        start_time = time.perf_counter()
        
        # 啟動子行程 (不阻塞)
        proc = subprocess.Popen(full_command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        
        # 定位真正的目標 Python PID (如果被 /usr/bin/time 包裹，需要找子行程)
        target_pid = proc.pid
        time.sleep(0.02) # 給系統一點時間 fork
        if is_wrapped:
            try:
                ps_proc = psutil.Process(proc.pid)
                children = ps_proc.children()
                if children:
                    target_pid = children[0].pid
            except psutil.NoSuchProcess:
                pass

        # 初始化看門狗執行緒
        kill_event = threading.Event()
        stop_event = threading.Event()
        watchdog_thread = threading.Thread(
            target=self._watchdog_worker, 
            args=(target_pid, mode, kill_event, stop_event),
            daemon=True
        )
        watchdog_thread.start()

        # 🌟 修正3：優雅收屍邏輯。使用 communicate 讀取並等待行程結束
        try:
            stdout_out, stderr_out = proc.communicate()
        except:
            stdout_out, stderr_out = "", ""
            
        wall_s = time.perf_counter() - start_time
        
        # 關閉看門狗
        stop_event.set()
        watchdog_thread.join()

        # 🚨 檢查是否是被看門狗主動砍掉的
        if kill_event.is_set():
            return RunResult(
                wall_ms=wall_s * 1000,
                user_ms=None,      # 填入 None 讓 HTML 能優雅轉為 N/A 呈現
                system_ms=None,
                memory_kb=None,
            )

        if proc.returncode != 0:
            # 排除因被外部 SIGKILL 導致的 returncode (-9 是 Linux SIGKILL, 137 是 bash 終止碼)
            if proc.returncode in [-9, -15, 137, 143]: 
                return RunResult(wall_ms=wall_s * 1000, user_ms=None, system_ms=None, memory_kb=None)
            # 萬一看門狗沒設 kill_event 但行程還是死了，給予基礎相容，不直接爆破主程式
            return RunResult(wall_ms=wall_s * 1000, user_ms=None, system_ms=None, memory_kb=None)

        # 正常結束，解析數據
        user_s = system_s = memory_kb = None
        if self.style and is_wrapped:
            user_s, system_s, memory_kb = self._parse_time_output(stderr_out, self.style)

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
            if platform.system() == "Darwin" and hasattr(os, "wait4"):
                return "wait4"
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
        return user_s, system_s, memory_kb


class SyscallProbe:
    """Collect syscall counts with strace when it is available."""

    def __init__(self, python_bin: str, mode: str) -> None:
        self.python_bin = python_bin
        self.mode = mode
        self.strace_path = shutil.which("strace")

    def command_notes(self, program: Path) -> list[ProbeCommand]:
        target = f"{self.python_bin} {program} <n>"
        status = "used" if self.strace_path and self.mode != "off" else "unavailable"
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
        if self.mode == "off" or not self.strace_path:
            return None, []
        command = [self.strace_path, "-c", self.python_bin, str(program), str(size)]
        
        # 🌟 修正4：加固 strace 執行時子行程可能突然被看門狗撲殺的例外處理
        try:
            result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=5)
            if result.returncode != 0:
                return None, []
            return self._parse_summary(result.stderr)
        except:
            return None, []

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
                numbers = [safe_int(p) for p in parts[:-1] if safe_int(p) is not None]
                if numbers:
                    total = numbers[-2] if len(numbers) >= 2 else numbers[-1]
                continue
            syscall = parts[-1]
            numbers = [safe_int(p) for p in parts[:-1] if safe_int(p) is not None]
            if not numbers:
                continue
            calls = numbers[-2] if len(numbers) >= 2 and len(parts) >= 6 else numbers[-1]
            rows.append((syscall, calls))
        if total is None and rows:
            total = sum(calls for _, calls in rows)
        rows.sort(key=lambda item: item[1], reverse=True)
        return total, rows[:5]


class MeasurementCollector:
    """Coordinate resource probes across all input sizes with policy integration."""

    def __init__(self, python_bin: str, syscall_mode: str, mode: str = "normal") -> None:
        self.time_probe = TimeProbe(python_bin)
        self.syscall_probe = SyscallProbe(python_bin, syscall_mode)
        self.mode = mode # 保存正常/緊急模式參數

    def collect(self, program: Path, sizes: list[int], repeats: int) -> tuple[list[Measurement], dict[str, object]]:
        metadata: dict[str, object] = {
            "platform": platform.platform(),
            "python": self.time_probe.python_bin,
            "time_tool": self.time_probe.tool_name,
            "strace": self.syscall_probe.strace_path or "unavailable",
            "audit_mode": self.mode, # 將目前模式寫入 HTML 報表元數據
            "probe_commands": [command.__dict__ for command in self.command_notes(program)],
        }

        rows: list[Measurement] = []
        for size in sizes:
            # 傳遞 mode 參數給 time_probe
            timed_runs = [self.time_probe.run(program, size, self.mode) for _ in range(repeats)]
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