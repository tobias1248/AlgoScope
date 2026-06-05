"""FastAPI entrypoint for the AlgoScope web demo."""

from __future__ import annotations

import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from algoscope.config import DEMO_CASES
from algoscope.service import AnalysisService
from algoscope.web_models import AnalysisRequest


app = FastAPI(title="AlgoScope API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalysisPayload(BaseModel):
    code: str = Field(min_length=1)
    sizes: list[int] = Field(min_length=1, max_length=8)
    repeats: int = Field(default=3, ge=1, le=5)
    syscalls: Literal["auto", "on", "off"] = "auto"
    timeout_seconds: float = Field(default=5.0, ge=0.25, le=30)
    memory_mb: int = Field(default=256, ge=64, le=2048)
    llm_summary: Literal["off", "auto", "on"] = "auto"
    runner: Literal["auto", "docker", "local"] = "auto"

    def to_request(self) -> AnalysisRequest:
        return AnalysisRequest(
            code=self.code,
            sizes=self.sizes,
            repeats=self.repeats,
            syscalls=self.syscalls,
            timeout_seconds=self.timeout_seconds,
            memory_mb=self.memory_mb,
            llm_summary=self.llm_summary,
            runner=self.runner,
        )


class JobRecord(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    created_at: str
    updated_at: str
    result: dict[str, Any] | None = None
    error: str | None = None


_service = AnalysisService()
_executor = ThreadPoolExecutor(max_workers=2)
_jobs: dict[str, JobRecord] = {}
_lock = Lock()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/demo-cases")
def demo_cases() -> list[dict[str, Any]]:
    demos = []
    for key, config in DEMO_CASES.items():
        program = Path(config["program"])
        demos.append(
            {
                "key": key,
                "label": key.replace("_", " ").title(),
                "sizes": list(config["sizes"]),
                "code": program.read_text(encoding="utf-8"),
            }
        )
    demos.extend(
        [
            {
                "key": "infinite_loop",
                "label": "Infinite Loop",
                "sizes": [10, 20, 30],
                "code": "import sys\n\nn = int(sys.argv[1])\nwhile True:\n    pass\n",
            },
            {
                "key": "memory_growth",
                "label": "Memory Growth",
                "sizes": [10, 20, 40],
                "code": (
                    "import sys\n\n"
                    "n = int(sys.argv[1])\n"
                    "blocks = []\n"
                    "for _ in range(n):\n"
                    "    blocks.append(bytearray(8 * 1024 * 1024))\n"
                    "print(len(blocks))\n"
                ),
            },
        ]
    )
    return demos


@app.post("/api/analyses", status_code=202)
def create_analysis(payload: AnalysisPayload) -> dict[str, str]:
    job_id = uuid4().hex
    now = _now()
    record = JobRecord(job_id=job_id, status="queued", created_at=now, updated_at=now)
    with _lock:
        _jobs[job_id] = record
    _executor.submit(_run_job, job_id, payload.to_request())
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/analyses/{job_id}")
def get_analysis(job_id: str) -> JobRecord:
    with _lock:
        record = _jobs.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Analysis job not found.")
    return record


def _run_job(job_id: str, request: AnalysisRequest) -> None:
    _replace(job_id, status="running", updated_at=_now())
    try:
        result = _service.run(request)
    except Exception as exc:
        _replace(
            job_id,
            status="failed",
            updated_at=_now(),
            error=f"{exc}\n{traceback.format_exc(limit=3)}",
        )
        return

    _replace(job_id, status="completed", updated_at=_now(), result=result.to_dict())


def _replace(job_id: str, **updates: Any) -> None:
    with _lock:
        current = _jobs[job_id]
        data = current.model_dump()
        data.update(updates)
        _jobs[job_id] = JobRecord(**data)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def main() -> None:
    import uvicorn

    uvicorn.run("algoscope.api:app", host="127.0.0.1", port=8000)
