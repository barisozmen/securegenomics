"""A tiny in-process background-job registry.

Long-running CLI operations — creating a project (which also generates and
uploads a crypto context), the encode → encrypt → upload data pipeline, running
a protocol, decrypting a result — are executed on worker threads so the HTTP
handler returns immediately with a ``job_id``. The frontend polls
``GET /api/jobs/<id>`` for live status, step progress, and captured CLI output.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional


class Job:
    """A single background operation and its live state."""

    def __init__(self, kind: str, title: str) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.title = title
        self.status = "running"  # running | succeeded | failed
        self.steps: List[Dict[str, str]] = []
        self.log_lines: List[str] = []
        self.result: Any = None
        self.error: Optional[str] = None
        self.created_at = time.time()
        self.updated_at = self.created_at
        self._lock = threading.Lock()

    # -- mutation helpers used from the worker thread ---------------------
    def set_steps(self, names: List[str]) -> None:
        with self._lock:
            self.steps = [{"name": n, "status": "pending"} for n in names]
            self.updated_at = time.time()

    def mark(self, name: str, status: str) -> None:
        with self._lock:
            for step in self.steps:
                if step["name"] == name:
                    step["status"] = status
            self.updated_at = time.time()

    def log(self, text: str) -> None:
        if not text:
            return
        with self._lock:
            for line in text.splitlines():
                if line.strip():
                    self.log_lines.append(line.rstrip())
            self.updated_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "id": self.id,
                "kind": self.kind,
                "title": self.title,
                "status": self.status,
                "steps": list(self.steps),
                "log": list(self.log_lines),
                "result": self.result,
                "error": self.error,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
            }


class JobRegistry:
    """Owns all jobs and the threads running them."""

    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()

    def submit(self, kind: str, title: str, target: Callable[[Job], Any]) -> Job:
        job = Job(kind, title)
        with self._lock:
            self._jobs[job.id] = job
        thread = threading.Thread(
            target=self._run, args=(job, target), daemon=True, name=f"job-{job.id}"
        )
        thread.start()
        return job

    def _run(self, job: Job, target: Callable[[Job], Any]) -> None:
        try:
            job.result = target(job)
            job.status = "succeeded"
        except Exception as exc:  # noqa: BLE001 — surfaced to the UI verbatim
            job.error = str(exc)
            job.status = "failed"
            job.log(f"Error: {exc}")
        finally:
            job.updated_at = time.time()

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def recent(self, limit: int = 25) -> List[Dict[str, Any]]:
        with self._lock:
            jobs = sorted(
                self._jobs.values(), key=lambda j: j.created_at, reverse=True
            )
        return [j.to_dict() for j in jobs[:limit]]
