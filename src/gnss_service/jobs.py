"""Job lifecycle: storage layout and execution of the solver for one job."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from rq.timeouts import JobTimeoutException
from sqlalchemy.orm import Session, sessionmaker

from . import db
from .config import settings
from .models import Job, JobStatus
from .solver.pipeline import SolverError, process

RESULT_FILES = {"clean.csv": "text/csv", "raw.csv": "text/csv", "clean.kml": "application/vnd.google-earth.kml+xml"}


def job_dir(job_id: str) -> Path:
    return settings.storage_dir / job_id


def run_job(job_id: str, session_factory: sessionmaker | None = None) -> None:
    """Execute one job. Opens its own session so a worker process can call it."""
    session: Session = (session_factory or db.SessionLocal)()
    try:
        job = session.get(Job, job_id)
        if job is None:
            return
        job.status = JobStatus.running
        job.started_at = datetime.now(timezone.utc)
        session.commit()
        d = job_dir(job_id)
        try:
            result = process(d / "input.obs", d / "input.nav", d / "out")
            job.status, job.metrics = JobStatus.succeeded, result.metrics
        except JobTimeoutException:
            job.status, job.error = JobStatus.failed, "job failed: timeout"
        except SolverError as exc:
            job.status, job.error = JobStatus.failed, str(exc)
        except Exception as exc:  # never leave a job stuck in "running"
            job.status, job.error = JobStatus.failed, f"internal error: {type(exc).__name__}"
        job.finished_at = datetime.now(timezone.utc)
        session.commit()
    finally:
        session.close()


def mark_failed(job_id: str, message: str, session_factory: sessionmaker | None = None) -> None:
    session: Session = (session_factory or db.SessionLocal)()
    try:
        job = session.get(Job, job_id)
        if job is not None and job.status in (JobStatus.queued, JobStatus.running):
            job.status, job.error = JobStatus.failed, message
            job.finished_at = datetime.now(timezone.utc)
            session.commit()
    finally:
        session.close()


def on_job_failure(rq_job, connection, exc_type, exc_value, traceback) -> None:
    """RQ failure callback: covers timeouts and crashes that run_job cannot catch itself."""
    reason = "timeout" if "Timeout" in exc_type.__name__ else exc_type.__name__
    mark_failed(rq_job.args[0], f"job failed: {reason}")
