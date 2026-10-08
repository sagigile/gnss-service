from __future__ import annotations

import shutil
from datetime import datetime

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from redis.exceptions import RedisError

from . import db, jobqueue, jobs
from .config import settings
from .models import Job, JobStatus

app = FastAPI(title="GNSS processing service")

CHUNK = 1024 * 1024


def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()


class JobOut(BaseModel):
    id: str
    status: JobStatus
    obs_filename: str
    nav_filename: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    metrics: dict | None

    model_config = {"from_attributes": True}


async def _save_upload(upload: UploadFile, dest) -> None:
    size = 0
    with open(dest, "wb") as fh:
        while chunk := await upload.read(CHUNK):
            size += len(chunk)
            if size > settings.max_upload_bytes:
                raise HTTPException(413, f"{upload.filename}: file exceeds {settings.max_upload_bytes // 2**20} MB limit")
            fh.write(chunk)
    if size == 0:
        raise HTTPException(422, f"{upload.filename}: file is empty")


def dispatch(job_id: str) -> None:
    """Put the job on the RQ queue; a worker process picks it up."""
    try:
        jobqueue.enqueue_job(job_id)
    except RedisError:
        jobs.mark_failed(job_id, "queue unavailable")
        raise HTTPException(503, "job queue is unavailable, try again later")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/jobs", response_model=JobOut, status_code=201)
async def create_job(
    obs: UploadFile = File(..., description="RINEX observation file"),
    nav: UploadFile = File(..., description="RINEX navigation (ephemeris) file"),
    session: Session = Depends(get_db),
):
    job = Job(obs_filename=obs.filename or "obs", nav_filename=nav.filename or "nav")
    session.add(job)
    session.commit()
    d = jobs.job_dir(job.id)
    d.mkdir(parents=True, exist_ok=True)
    try:
        await _save_upload(obs, d / "input.obs")
        await _save_upload(nav, d / "input.nav")
    except HTTPException:
        session.delete(job)
        session.commit()
        shutil.rmtree(d, ignore_errors=True)
        raise
    dispatch(job.id)
    session.refresh(job)
    return job


def _get_job(session: Session, job_id: str) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job


@app.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, session: Session = Depends(get_db)):
    return _get_job(session, job_id)


@app.get("/jobs/{job_id}/result/{name}")
def get_result(job_id: str, name: str, session: Session = Depends(get_db)):
    job = _get_job(session, job_id)
    if name not in jobs.RESULT_FILES:
        raise HTTPException(404, f"unknown result; choose one of {sorted(jobs.RESULT_FILES)}")
    if job.status != JobStatus.succeeded:
        raise HTTPException(409, f"job is {job.status.value}, result not available")
    return FileResponse(jobs.job_dir(job_id) / "out" / name, media_type=jobs.RESULT_FILES[name], filename=name)
