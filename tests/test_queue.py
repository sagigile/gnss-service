from redis.exceptions import ConnectionError as RedisConnectionError

from gnss_service import db, jobqueue, jobs
from gnss_service.models import Job, JobStatus


def _post(client, obs, nav):
    return client.post("/jobs", files={"obs": ("a.obs", obs), "nav": ("a.nav", nav)})


def _status(job_id):
    with db.SessionLocal() as s:
        return s.get(Job, job_id)


def test_post_returns_before_work_runs(client, obs_bytes, nav_bytes):
    r = _post(client, obs_bytes, nav_bytes)
    assert r.json()["status"] == "queued"
    assert r.json()["started_at"] is None
    assert jobqueue.get_queue().count == 1
    assert client.get(f"/jobs/{r.json()['id']}/result/clean.csv").status_code == 409


def test_worker_drains_queue(client, obs_bytes, nav_bytes):
    ids = [_post(client, obs_bytes, nav_bytes).json()["id"] for _ in range(2)]
    client.run_worker()
    assert jobqueue.get_queue().count == 0
    assert all(_status(i).status == JobStatus.succeeded for i in ids)


def test_queue_down_returns_503_and_fails_job(client, monkeypatch, obs_bytes, nav_bytes):
    def boom(job_id):
        raise RedisConnectionError("redis down")

    monkeypatch.setattr(jobqueue, "enqueue_job", boom)
    assert _post(client, obs_bytes, nav_bytes).status_code == 503
    with db.SessionLocal() as s:
        job = s.query(Job).one()
        assert job.status == JobStatus.failed and "queue unavailable" in job.error


def test_failure_callback_marks_stuck_job_failed(client, obs_bytes, nav_bytes):
    jid = _post(client, obs_bytes, nav_bytes).json()["id"]
    with db.SessionLocal() as s:
        s.get(Job, jid).status = JobStatus.running  # simulate a worker killed mid-job
        s.commit()

    class FakeRqJob:
        args = (jid,)

    jobs.on_job_failure(FakeRqJob(), None, TimeoutError, TimeoutError(), None)
    job = _status(jid)
    assert job.status == JobStatus.failed and "timeout" in job.error


def test_failure_callback_does_not_overwrite_success(client, obs_bytes, nav_bytes):
    jid = _post(client, obs_bytes, nav_bytes).json()["id"]
    client.run_worker()

    class FakeRqJob:
        args = (jid,)

    jobs.on_job_failure(FakeRqJob(), None, RuntimeError, RuntimeError(), None)
    assert _status(jid).status == JobStatus.succeeded


def test_real_timeout_marks_job_failed(client, monkeypatch, obs_bytes, nav_bytes):
    import time

    monkeypatch.setenv("JOB_TIMEOUT_SECONDS", "1")

    def spin(*a, **k):  # short sleeps so the timeout can fire on Windows too
        for _ in range(400):
            time.sleep(0.05)

    monkeypatch.setattr(jobs, "process", spin)
    jid = _post(client, obs_bytes, nav_bytes).json()["id"]
    client.run_worker()
    job = _status(jid)
    assert job.status == JobStatus.failed and "timeout" in job.error


def test_sweeper_fails_only_stale_running_jobs(client, monkeypatch, obs_bytes, nav_bytes):
    from datetime import datetime, timedelta, timezone

    old = _post(client, obs_bytes, nav_bytes).json()["id"]
    fresh = _post(client, obs_bytes, nav_bytes).json()["id"]
    now = datetime.now(timezone.utc)
    with db.SessionLocal() as s:
        for jid, age in ((old, 3600), (fresh, 5)):
            j = s.get(Job, jid)
            j.status, j.started_at = JobStatus.running, now - timedelta(seconds=age)
        s.commit()
    assert jobs.sweep_stale_jobs() == 1
    assert _status(old).status == JobStatus.failed and "worker lost" in _status(old).error
    assert _status(fresh).status == JobStatus.running
