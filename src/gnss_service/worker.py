"""Worker entry point: ``python -m gnss_service.worker`` (Linux/macOS/Docker; RQ needs fork)."""
from rq import Worker

from . import jobs
from .jobqueue import QUEUE_NAME, get_redis


def main() -> None:
    swept = jobs.sweep_stale_jobs()
    if swept:
        print(f"marked {swept} stale job(s) as failed", flush=True)
    conn = get_redis()
    Worker([QUEUE_NAME], connection=conn).work()


if __name__ == "__main__":
    main()
