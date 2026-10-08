"""Benchmark a running Compose stack. Usage: python scripts/benchmark.py [--base URL] [--reps N] [--burst K]

Reports only what it measures: per-job processing time (started_at -> finished_at, as recorded by the
service), end-to-end latency (created_at -> finished_at), and wall-clock time for a burst of K jobs.
"""
import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import httpx

DATA = Path(__file__).resolve().parent.parent / "tests" / "data"
NAV = DATA / "samsung_nav.nav.rnx"


def ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def submit(client: httpx.Client, obs: str) -> str:
    with open(DATA / obs, "rb") as o, open(NAV, "rb") as n:
        r = client.post("/jobs", files={"obs": (obs, o), "nav": ("nav", n)})
    r.raise_for_status()
    return r.json()["id"]


def wait(client: httpx.Client, job_id: str, timeout: float = 300) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/jobs/{job_id}").json()
        if j["status"] in ("succeeded", "failed"):
            return j
        time.sleep(0.2)
    raise TimeoutError(job_id)


def summarize(xs: list[float]) -> dict:
    return {"n": len(xs), "median_s": round(statistics.median(xs), 3), "min_s": round(min(xs), 3),
            "max_s": round(max(xs), 3)}


def sequential(client, obs: str, reps: int) -> dict:
    proc, e2e, meta = [], [], None
    for _ in range(reps):
        j = wait(client, submit(client, obs))
        assert j["status"] == "succeeded", j
        proc.append(ts(j["finished_at"]) - ts(j["started_at"]))
        e2e.append(ts(j["finished_at"]) - ts(j["created_at"]))
        meta = j["metrics"]
    return {
        "file": obs,
        "size_mb": round((DATA / obs).stat().st_size / 2**20, 2),
        "epochs_in_obs": meta["epochs_in_obs"],
        "processing": summarize(proc),
        "end_to_end": summarize(e2e),
    }


def burst(base: str, obs: str, k: int) -> dict:
    with httpx.Client(base_url=base, timeout=120) as c:
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=k) as ex:
            ids = list(ex.map(lambda _: submit(c, obs), range(k)))
        jobs = [wait(c, i) for i in ids]
        wall = max(ts(j["finished_at"]) for j in jobs) - t0
    assert all(j["status"] == "succeeded" for j in jobs)
    return {"jobs": k, "file": obs, "wall_s": round(wall, 2), "jobs_per_s": round(k / wall, 2)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8010")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--burst", type=int, default=0, help="also run a burst of K jobs (0 = skip)")
    ap.add_argument("--files", nargs="+", default=["my_data_2.obs", "my_data_3.obs", "my_data_1.obs"])
    a = ap.parse_args()
    out = {}
    with httpx.Client(base_url=a.base, timeout=120) as c:
        if a.reps:
            out["sequential"] = [sequential(c, f, a.reps) for f in a.files]
    if a.burst:
        out["burst"] = burst(a.base, "my_data_3.obs", a.burst)
    print(json.dumps(out, indent=2))
