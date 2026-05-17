from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from schemas import AnalyzeMode, LongVideoJobResponse, LongVideoJobStatus
from services.pipeline import pipeline


@dataclass
class LongVideoJobRecord:
    job_id: str
    status: LongVideoJobStatus = LongVideoJobStatus.queued
    progress: int = 0
    result: dict | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class LongVideoJobManager:
    def __init__(self, ttl_seconds: int = 1800) -> None:
        self._ttl_seconds = ttl_seconds
        self._jobs: dict[str, LongVideoJobRecord] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="captp-long-video")

    def create_job(self, content: bytes, filename: str, content_type: str, mode: AnalyzeMode) -> LongVideoJobResponse:
        self._prune_locked()
        job_id = uuid.uuid4().hex
        record = LongVideoJobRecord(job_id=job_id)
        with self._lock:
            self._jobs[job_id] = record
        self._executor.submit(self._run_job, job_id, content, filename, content_type, mode)
        return self._to_response(record)

    def get_job(self, job_id: str) -> LongVideoJobResponse | None:
        with self._lock:
            self._prune_locked()
            record = self._jobs.get(job_id)
            if record is None:
                return None
            return self._to_response(record)

    def _run_job(self, job_id: str, content: bytes, filename: str, content_type: str, mode: AnalyzeMode) -> None:
        self._update(job_id, status=LongVideoJobStatus.running, progress=10, error=None)
        try:
            result = pipeline.analyze_long_video_async_final(
                content=content,
                filename=filename,
                content_type=content_type,
                mode=mode,
                progress_callback=lambda value: self._update(job_id, progress=value),
            )
        except Exception as exc:
            self._update(job_id, status=LongVideoJobStatus.failed, progress=100, error=str(exc))
            return

        self._update(job_id, status=LongVideoJobStatus.completed, progress=100, result=result.model_dump(), error=None)

    def _update(
        self,
        job_id: str,
        *,
        status: LongVideoJobStatus | None = None,
        progress: int | None = None,
        result: dict | None = None,
        error: str | None = None,
    ) -> None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return
            if status is not None:
                record.status = status
            if progress is not None:
                record.progress = max(0, min(100, int(progress)))
            if result is not None:
                record.result = result
            if error is not None or status == LongVideoJobStatus.failed:
                record.error = error
            record.updated_at = time.time()

    def _to_response(self, record: LongVideoJobRecord) -> LongVideoJobResponse:
        return LongVideoJobResponse(
            job_id=record.job_id,
            status=record.status,
            progress=record.progress,
            result=record.result,
            error=record.error,
        )

    def _prune_locked(self) -> None:
        now = time.time()
        stale_ids = [
            job_id
            for job_id, record in self._jobs.items()
            if record.status in {LongVideoJobStatus.completed, LongVideoJobStatus.failed}
            and (now - record.updated_at) > self._ttl_seconds
        ]
        for job_id in stale_ids:
            self._jobs.pop(job_id, None)


job_manager = LongVideoJobManager()
