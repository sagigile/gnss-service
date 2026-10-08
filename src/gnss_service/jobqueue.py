"""Redis/RQ plumbing. Kept separate so the API and the worker share one definition."""
from __future__ import annotations

from redis import Redis
from rq import Callback, Queue

from . import jobs
from .config import settings

QUEUE_NAME = "gnss"


def get_redis() -> Redis:
    return Redis.from_url(settings.redis_url)


def get_queue() -> Queue:
    return Queue(QUEUE_NAME, connection=get_redis())


def enqueue_job(job_id: str) -> None:
    get_queue().enqueue(
        jobs.run_job,
        job_id,
        job_timeout=settings.job_timeout_seconds,
        result_ttl=0,
        failure_ttl=86400,
        on_failure=Callback(jobs.on_job_failure),
    )
