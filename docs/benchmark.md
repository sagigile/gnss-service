# Benchmark

Measured with [`scripts/benchmark.py`](../scripts/benchmark.py) against the Docker Compose stack
(`docker compose up --build`, Postgres 16, Redis 7, API + worker containers). Re-run it to reproduce.

**Environment:** Intel Core i9-13900H (14 cores / 20 threads), Docker Desktop on Windows 11 (20 CPUs and
~11.5 GiB visible to the Docker VM), client on the same machine. Single run per configuration set, on
2026-10-08. Numbers will differ on other hardware.

## Per-job time (sequential, 1 worker, 5 repetitions each)

"Processing" is `started_at -> finished_at` as recorded by the service (solver + writing outputs).
"End-to-end" is `created_at -> finished_at` (adds queue wait). Upload time is not included.

| OBS file | Size | Epochs in file | Processing median (min-max) | End-to-end median |
|---|---|---|---|---|
| `my_data_2.obs` | 0.24 MB | 60 | 0.55 s (0.54-0.58) | 0.59 s |
| `my_data_3.obs` | 0.56 MB | 140 | 1.06 s (0.90-1.19) | 1.09 s |
| `my_data_1.obs` | 6.14 MB | 1295 | 7.25 s (7.14-7.33) | 7.30 s |

Every job also uses the same 8.2 MB navigation file.

## Throughput vs. number of workers

12 jobs of `my_data_3.obs` submitted concurrently, 3 runs per setting
(`docker compose up --scale worker=N`). Wall time = first submit -> last job finished, so it **includes the
client uploading 12 x (0.56 MB + 8.2 MB) over localhost**.

| Workers | Wall time per run | Jobs/s per run | Median jobs/s |
|---|---|---|---|
| 1 | 13.44 s, 13.23 s, 12.58 s | 0.89, 0.91, 0.95 | 0.91 |
| 2 | 7.39 s, 6.57 s, 7.10 s | 1.62, 1.83, 1.69 | 1.69 |
| 4 | 4.21 s, 4.29 s, 4.15 s | 2.85, 2.80, 2.89 | 2.85 |

Median throughput with 4 workers is ~3.1x that of 1 worker in this setup.

## Caveats

- One machine, Docker Desktop VM, no network latency; not a production load test.
- Small sample (3-5 runs). Read the min-max column, not just the median.
- Only one file type was used for the concurrency test; the API itself (not the solver) was not load-tested
  separately.
