"""Фоновые задания для тяжёлого Монте-Карло.

10 000 путей × 18 сценариев на чистом Python занимают десятки секунд,
поэтому HTTP-запрос не должен ждать расчёт. JobManager запускает расчёт
в пуле потоков и отдаёт статус через /api/v2/jobs/{job_id}.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from . import auth as auth_service
from .engine import run_optimization
from .models import JobStatus, OptimizeRequest, OptimizeResponse

JOB_TTL_SECONDS = 60 * 60
MAX_JOBS = 100


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Job:
    job_id: str
    user_id: Optional[str] = None
    status: str = "queued"
    progress: int = 0
    message: str = "В очереди"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    result: Optional[OptimizeResponse] = None
    error: Optional[str] = None
    started_at: float = 0.0
    finished_at: float = 0.0
    charged_tokens: int = 0


class JobManager:
    def __init__(self, max_workers: Optional[int] = None) -> None:
        workers = max_workers or int(os.getenv("OPTIMIZER_JOB_WORKERS", "2"))
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, min(4, workers)),
            thread_name_prefix="optimizer-job",
        )
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()

    def _cleanup_locked(self) -> None:
        now = time.time()
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if job.finished_at and now - job.finished_at > JOB_TTL_SECONDS
        ]
        for job_id in expired:
            self._jobs.pop(job_id, None)
        if len(self._jobs) <= MAX_JOBS:
            return
        finished = sorted(
            (job for job in self._jobs.values() if job.finished_at),
            key=lambda job: job.finished_at,
        )
        for job in finished[: max(0, len(self._jobs) - MAX_JOBS)]:
            self._jobs.pop(job.job_id, None)

    def submit(
        self,
        request: OptimizeRequest,
        user_id: Optional[str] = None,
        charged_tokens: int = 0,
    ) -> str:
        job_id = uuid.uuid4().hex
        job = Job(
            job_id=job_id,
            user_id=user_id,
            charged_tokens=max(0, int(charged_tokens)),
        )
        with self._lock:
            self._cleanup_locked()
            self._jobs[job_id] = job
        self._executor.submit(self._run, job_id, request)
        return job_id

    def _update(
        self,
        job_id: str,
        *,
        status: Optional[str] = None,
        progress: Optional[int] = None,
        message: Optional[str] = None,
        result: Optional[OptimizeResponse] = None,
        error: Optional[str] = None,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            if status is not None:
                job.status = status
            if progress is not None:
                job.progress = max(0, min(100, int(progress)))
            if message is not None:
                job.message = message
            if result is not None:
                job.result = result
            if error is not None:
                job.error = error
            job.updated_at = _now_iso()

    def _run(self, job_id: str, request: OptimizeRequest) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.started_at = time.time()
        self._update(job_id, status="running", progress=1, message="Стартуем расчёт")

        def progress_callback(progress: int, message: str) -> None:
            self._update(job_id, progress=progress, message=message)

        try:
            result = run_optimization(request, progress_callback=progress_callback)
        except Exception as exc:  # noqa: BLE001
            refund_user: Optional[str] = None
            refund_amount = 0
            with self._lock:
                job = self._jobs.get(job_id)
                if job is not None:
                    job.finished_at = time.time()
                    refund_user = job.user_id
                    refund_amount = job.charged_tokens
                    job.charged_tokens = 0
            if refund_user and refund_amount > 0:
                try:
                    auth_service.refund_tokens(
                        refund_user,
                        refund_amount,
                        meta=f"job:{job_id}",
                    )
                except Exception:  # noqa: BLE001
                    pass
            self._update(
                job_id,
                status="error",
                progress=100,
                message="Ошибка расчёта",
                error=f"{type(exc).__name__}: {exc}",
            )
            return
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.finished_at = time.time()
        self._update(
            job_id,
            status="done",
            progress=100,
            message="Готово",
            result=result,
        )

    def get(
        self,
        job_id: str,
        user_id: Optional[str] = None,
    ) -> Optional[JobStatus]:
        with self._lock:
            self._cleanup_locked()
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if user_id is not None and job.user_id != user_id:
                return None
            return JobStatus(
                job_id=job.job_id,
                status=job.status,  # type: ignore[arg-type]
                progress=job.progress,
                message=job.message,
                created_at=job.created_at,
                updated_at=job.updated_at,
                result=job.result,
                error=job.error,
            )

    def list_recent(
        self,
        limit: int = 20,
        user_id: Optional[str] = None,
    ) -> List[JobStatus]:
        with self._lock:
            self._cleanup_locked()
            candidates = [
                job
                for job in self._jobs.values()
                if user_id is None or job.user_id == user_id
            ]
            jobs = sorted(
                candidates,
                key=lambda job: job.created_at,
                reverse=True,
            )[: max(1, min(limit, 100))]
            return [
                JobStatus(
                    job_id=job.job_id,
                    status=job.status,  # type: ignore[arg-type]
                    progress=job.progress,
                    message=job.message,
                    created_at=job.created_at,
                    updated_at=job.updated_at,
                    result=job.result,
                    error=job.error,
                )
                for job in jobs
            ]

    def stats(self) -> Dict[str, int]:
        with self._lock:
            self._cleanup_locked()
            counts = {"queued": 0, "running": 0, "done": 0, "error": 0}
            for job in self._jobs.values():
                counts[job.status] = counts.get(job.status, 0) + 1
            counts["total"] = len(self._jobs)
            return counts

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


JOBS = JobManager()
