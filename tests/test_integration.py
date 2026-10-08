"""Real Postgres + Redis + forking RQ worker. Runs only when INTEGRATION=1 (set in CI / Docker)."""
import os
import shutil
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from rq import Worker
from sqlalchemy.orm import sessionmaker

from gnss_service import db, jobqueue
from gnss_service.main import app

pytestmark = pytest.mark.skipif(os.environ.get("INTEGRATION") != "1", reason="needs real Postgres/Redis")
DATA = Path(__file__).parent / "data"


@pytest.fixture
def stack(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    engine = db.make_engine()
    assert engine.dialect.name == "postgresql"
    db.Base.metadata.drop_all(engine)
    engine.dispose()
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    command.upgrade(Config("alembic.ini"), "head")  # also proves migrations work on Postgres
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=db.make_engine(), expire_on_commit=False))
    jobqueue.get_redis().flushdb()
    yield TestClient(app)
    shutil.rmtree(tmp_path / "storage", ignore_errors=True)


def _post(c, obs):
    with open(DATA / obs, "rb") as o, open(DATA / "samsung_nav.nav.rnx", "rb") as n:
        return c.post("/jobs", files={"obs": (obs, o), "nav": ("nav", n)})


def test_job_through_real_worker(stack):
    r = _post(stack, "my_data_3.obs")
    assert r.status_code == 201 and r.json()["status"] == "queued"
    Worker([jobqueue.QUEUE_NAME], connection=jobqueue.get_redis()).work(burst=True)  # forks
    job = stack.get(f"/jobs/{r.json()['id']}").json()
    assert job["status"] == "succeeded", job
    assert job["metrics"]["points_kept"] == 116
    assert stack.get(f"/jobs/{job['id']}/result/clean.csv").text.count("\n") == 117


def test_bad_input_fails_cleanly(stack):
    with open(DATA / "samsung_nav.nav.rnx", "rb") as n:
        r = stack.post("/jobs", files={"obs": ("x.obs", b"garbage\n"), "nav": ("nav", n)})
    Worker([jobqueue.QUEUE_NAME], connection=jobqueue.get_redis()).work(burst=True)
    job = stack.get(f"/jobs/{r.json()['id']}").json()
    assert job["status"] == "failed" and job["error"]
