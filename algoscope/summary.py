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
    """Generate a concise syscall interpretation with GitHub Copilot SDK."""

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
        if not _has_syscall_data(rows):
            if self.mode == "on":
                raise RuntimeError("No syscall data is available for Copilot to explain.")
            return ReportSummary(
                title="Copilot syscall explanation unavailable",
                body="No syscall data is available yet. Run with syscall probing enabled to request a Copilot explanation.",
                provider="github-copilot-sdk",
                status="unavailable",
            )

        try:
            return asyncio.run(self._generate_with_copilot(program, rows, estimate, scores, metadata))
        except Exception as exc:
            if self.mode == "on":
                raise RuntimeError(f"Copilot syscall explanation failed: {exc}") from exc
            return ReportSummary(
                title="Copilot syscall explanation unavailable",
                body=(
                    "GitHub Copilot SDK could not generate a syscall explanation in this environment. "
                    f"Reason: {exc} Local syscall notes are still available."
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
                        "Explain only the Linux syscalls shown in the provided AlgoScope data. "
                        "Connect each syscall to likely kernel-facing behavior in the submitted Python program. "
                        "Do not summarize Big O, timing charts, memory charts, or general performance unless it directly clarifies a syscall. "
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
            title="Copilot syscall explanation",
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
                f"- n={row.size}: syscalls={fmt_int(row.syscall_count)}, "
                f"top_syscalls={row.top_syscalls or 'n/a'}, "
                f"system_time={fmt_ms(row.system_ms)} ms"
            )
            for row in rows
        )
        submitted_code = _program_excerpt(program)

        return f"""請根據以下 AlgoScope syscall 資料，寫給作業系統課學生看的 syscall 解釋。

要求：
- 使用繁體中文。
- 只輸出 3 到 5 個 bullet points。
- 只解釋 Syscall measurements 裡實際出現的 syscall。
- 每個 bullet 盡量包含：syscall 名稱、它通常代表的 kernel 行為、這個 Python 程式或 Python runtime 可能為什麼觸發它。
- 如果 syscall 看起來是 Python interpreter startup/import/runtime 行為，而不是使用者演算法本身，請明確說出。
- 可以短提 system time 或 syscall count，但只在它能幫助理解 syscall 時提。
- 不要分析 Big O、不要評估演算法複雜度、不要總結整體效能。
- 不要加入不存在的數據。

Program: {program.name}
Platform: {metadata.get("platform")}

Submitted code:
```python
{submitted_code}
```

Syscall measurements:
{measurements}
"""

    @staticmethod
    def to_json(summary: ReportSummary | None) -> dict[str, str] | None:
        if summary is None:
            return None
        return asdict(summary)


def _github_token() -> str:
    for env_name in ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        token = os.getenv(env_name)
        if token:
            return token

    if shutil.which("gh") is None:
        raise RuntimeError("Set COPILOT_GITHUB_TOKEN, GH_TOKEN, or GITHUB_TOKEN; GitHub CLI is not installed.")

    result = subprocess.run(["gh", "auth", "token"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()

    raise RuntimeError(
        "Set COPILOT_GITHUB_TOKEN, GH_TOKEN, or GITHUB_TOKEN. "
        "The installed GitHub CLI could not provide a token with `gh auth token`; `gh auth status` alone is not enough."
    )


def _has_syscall_data(rows: list[Measurement]) -> bool:
    return any(row.syscall_count is not None or row.top_syscalls for row in rows)


def _program_excerpt(program: Path, limit: int = 4000) -> str:
    try:
        code = program.read_text(encoding="utf-8")
    except OSError:
        return "# source unavailable"
    if len(code) <= limit:
        return code
    return f"{code[:limit]}\n# ... truncated ..."
