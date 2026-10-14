from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field


@dataclass
class Job:
    user: str
    payload: dict
    status: str = "running"
    events: list[dict] = field(default_factory=list)
    result: dict | None = None
    cond: threading.Condition = field(default_factory=threading.Condition)


_jobs: dict[str, Job] = {}
_guard = threading.Lock()


def create_job(user: str, payload: dict) -> str:
    job_id = uuid.uuid4().hex
    job = Job(user=user, payload=payload)
    with _guard:
        _jobs[job_id] = job
        while len(_jobs) > 20:
            _jobs.pop(next(iter(_jobs)))
    return job_id


def job_meta(job_id: str) -> dict | None:
    job = _get(job_id)
    if job is None:
        return None
    with job.cond:
        return {"user": job.user, "status": job.status, "payload": json.dumps(job.payload)}


def set_status(job_id: str, status: str) -> None:
    job = _get(job_id)
    if job is None:
        return
    with job.cond:
        job.status = status
        job.cond.notify_all()


def claim_sync(job_id: str) -> bool:
    job = _get(job_id)
    if job is None:
        return False
    with job.cond:
        if job.status != "prompt":
            return False
        job.status = "syncing"
        job.cond.notify_all()
        return True


def store_result(job_id: str, result: dict) -> None:
    job = _get(job_id)
    if job is None:
        return
    with job.cond:
        job.result = result


def load_result(job_id: str) -> dict | None:
    job = _get(job_id)
    if job is None:
        return None
    with job.cond:
        return job.result


def publish(job_id: str, kind: str, text: str) -> None:
    job = _get(job_id)
    if job is None:
        return
    with job.cond:
        job.events.append({"kind": kind, "text": text})
        job.cond.notify_all()


def iter_events(job_id: str) -> Iterator[str]:
    """Replay lines already written, then wait for the next ones."""
    job = _get(job_id)
    if job is None:
        return
    index = 0
    while True:
        with job.cond:
            while index >= len(job.events) and job.status not in {"done", "error"}:
                if not job.cond.wait(timeout=15):
                    break
            if index >= len(job.events):
                pending = None
                finished = job.status in {"done", "error"}
            else:
                pending = job.events[index]
                index += 1
                finished = False
        if pending is None:
            if finished:
                return
            yield ": keepalive\n\n"
            continue
        yield f"data: {json.dumps(pending)}\n\n"
        if pending.get("kind") in {"done", "error"}:
            return


def _get(job_id: str) -> Job | None:
    with _guard:
        return _jobs.get(job_id)
