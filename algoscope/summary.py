"""LLM-backed report summaries focused on OS observability."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from algoscope.models import ComplexityScore, Measurement
from algoscope.utils import fmt_int, fmt_ms


SummaryMode = Literal["off", "auto", "on"]


@dataclass(frozen=True)
class ReportSummary:
    title: str
    body: str
    provider: str
    status: str


class LlmSummaryService:
    """Generate a concise OS-performance interpretation with GitHub Copilot SDK."""

    def __init__(self, mode: SummaryMode, timeout_seconds: float = 45.0, model: str | None = None) -> None:
        self.mode = mode
        self.timeout_seconds = timeout_seconds
        self.model = model

    def generate(
        self,
        program: Path,
        rows: list[Measurement],
        estimate: str,
        scores: list[ComplexityScore],
        metadata: dict[str, Any],
    ) -> ReportSummary | None:
        if self.mode == "off":
            return None

        try:
            return asyncio.run(self._generate_with_copilot(program, rows, estimate, scores, metadata))
        except Exception as exc:
            if self.mode == "on":
                raise RuntimeError(f"LLM summary generation failed: {exc}") from exc
            return ReportSummary(
                title="LLM Summary Unavailable",
                body=(
                    "GitHub Copilot SDK could not generate a summary in this environment. "
                    f"Reason: {exc}. The numeric OS measurements and charts are still valid."
                ),
                provider="github-copilot-sdk",
                status="unavailable",
            )

    async def _generate_with_copilot(
        self,
        program: Path,
        rows: list[Measurement],
        estimate: str,
        scores: list[ComplexityScore],
        metadata: dict[str, Any],
    ) -> ReportSummary:
        try:
            from copilot import CopilotClient, SubprocessConfig
            from copilot.generated.session_events import AssistantMessageData
            from copilot.session import PermissionHandler
        except ImportError as exc:
            raise RuntimeError("github-copilot-sdk is not installed") from exc

        prompt = self._build_prompt(program, rows, estimate, scores, metadata)
        config = SubprocessConfig(
            cwd=str(program.parent),
            github_token=_github_token(),
            log_level="error",
        )

        async with CopilotClient(config) as client:
            session = await client.create_session(
                on_permission_request=PermissionHandler.approve_all,
                model=self.model,
                client_name="AlgoScope",
                working_directory=str(program.parent),
                available_tools=[],
                excluded_tools=["*"],
                system_message={
                    "mode": "append",
                    "content": (
                        "You are an operating-systems teaching assistant. "
                        "Explain Linux syscall and resource measurement data for students. "
                        "Prioritize displayed syscalls, kernel-facing behavior, I/O overhead, system time, and RSS. "
                        "Do not claim formal proof of Big O complexity. "
                        "Return concise Traditional Chinese Markdown only."
                    ),
                },
            )
            event = await session.send_and_wait(prompt, timeout=self.timeout_seconds)
            await session.destroy()

        if event is None or not isinstance(event.data, AssistantMessageData):
            raise RuntimeError("Copilot did not return an assistant message")

        body = event.data.content.strip()
        if not body:
            raise RuntimeError("Copilot returned an empty summary")

        return ReportSummary(
            title="LLM OS Performance Summary",
            body=body,
            provider="github-copilot-sdk",
            status="generated",
        )

    @staticmethod
    def _build_prompt(
        program: Path,
        rows: list[Measurement],
        estimate: str,
        scores: list[ComplexityScore],
        metadata: dict[str, Any],
    ) -> str:
        measurements = "\n".join(
            (
                f"- n={row.size}: wall={fmt_ms(row.wall_ms)} ms, user={fmt_ms(row.user_ms)} ms, "
                f"system={fmt_ms(row.system_ms)} ms, RSS={fmt_int(row.memory_kb)} KB, "
                f"syscalls={fmt_int(row.syscall_count)}, top_syscalls={row.top_syscalls or 'n/a'}"
            )
            for row in rows
        )
        best_scores = "\n".join(
            f"- {score.name}: normalized_rmse={score.normalized_rmse:.4f}" for score in scores[:3]
        )
        probe_commands = metadata.get("probe_commands", [])
        probes = "\n".join(
            f"- {probe.get('title')}: {probe.get('command')} ({probe.get('status')})"
            for probe in probe_commands
            if isinstance(probe, dict)
        )
        syscall_explanations = metadata.get("syscall_explanations", [])
        syscall_notes = "\n".join(
            f"- {item.get('name')}: calls={item.get('calls')}, meaning={item.get('meaning')}, signal={item.get('signal')}"
            for item in syscall_explanations
            if isinstance(item, dict)
        )

        return f"""請根據以下 AlgoScope 報告資料，寫一段給作業系統課學生看的摘要。

要求：
- 使用繁體中文。
- 只輸出 4 到 6 個 bullet points。
- 優先解釋顯示出來的 syscall：它們通常代表什麼 kernel 行為，以及這個程式為什麼會觸發它們。
- 接著連到 resource usage：system CPU time、RSS memory、I/O overhead、process startup overhead。
- Big O 只能放在最後輔助說明，且要說這是 observed growth pattern，不是形式化證明。
- 如果 syscall 資料是 n/a，請明確說明需要 Linux strace 才能完整觀察 syscall。
- 不要加入不存在的數據。

Program: {program.name}
Estimated complexity: {estimate}
Platform: {metadata.get("platform")}
Time tool: {metadata.get("time_tool")}
strace: {metadata.get("strace")}

Measurements:
{measurements}

Best model scores:
{best_scores}

OS probes:
{probes}

Local syscall explanations:
{syscall_notes or 'n/a'}
"""

    @staticmethod
    def to_json(summary: ReportSummary | None) -> dict[str, str] | None:
        if summary is None:
            return None
        return asdict(summary)


def _github_token() -> str | None:
    token = os.getenv("GITHUB_TOKEN")
    if token:
        return token
    if shutil.which("gh") is None:
        return None
    result = subprocess.run(["gh", "auth", "token"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None
