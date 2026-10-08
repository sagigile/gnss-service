import io

from gnss_service import db
from gnss_service.models import Job

import pandas as pd


def _post(client, obs, nav):
    return client.post("/jobs", files={"obs": ("a.obs", obs), "nav": ("a.nav", nav)})


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_successful_job_end_to_end(client, obs_bytes, nav_bytes):
    r = _post(client, obs_bytes, nav_bytes)
    assert r.status_code == 201
    assert r.json()["status"] == "queued"
    client.run_worker()
    job = client.get(f"/jobs/{r.json()['id']}").json()
    assert job["status"] == "succeeded"
    assert job["error"] is None
    assert job["metrics"]["points_kept"] > 0
    assert job["started_at"] and job["finished_at"]

    csv = client.get(f"/jobs/{job['id']}/result/clean.csv")
    assert csv.status_code == 200
    df = pd.read_csv(io.StringIO(csv.text))
    assert len(df) == job["metrics"]["points_kept"]
    kml = client.get(f"/jobs/{job['id']}/result/clean.kml")
    assert kml.status_code == 200 and "<kml" in kml.text


def test_bad_rinex_marks_job_failed(client, nav_bytes):
    r = _post(client, b"not rinex\n", nav_bytes)
    assert r.status_code == 201
    client.run_worker()
    job = client.get(f"/jobs/{r.json()['id']}").json()
    assert job["status"] == "failed"
    assert job["error"]
    assert client.get(f"/jobs/{job['id']}/result/clean.csv").status_code == 409


def test_unknown_job_404(client):
    assert client.get("/jobs/does-not-exist").status_code == 404


def test_unknown_result_name_404(client, obs_bytes, nav_bytes):
    jid = _post(client, obs_bytes, nav_bytes).json()["id"]
    client.run_worker()
    assert client.get(f"/jobs/{jid}/result/passwd").status_code == 404


def test_empty_upload_rejected_and_not_persisted(client, nav_bytes):
    r = _post(client, b"", nav_bytes)
    assert r.status_code == 422
    with db.SessionLocal() as s:
        assert s.query(Job).count() == 0


def test_oversize_upload_rejected(client, monkeypatch, obs_bytes, nav_bytes):
    monkeypatch.setenv("MAX_UPLOAD_MB", "0")
    assert _post(client, obs_bytes, nav_bytes).status_code == 413


def test_missing_file_field_422(client, obs_bytes):
    r = client.post("/jobs", files={"obs": ("a.obs", obs_bytes)})
    assert r.status_code == 422
