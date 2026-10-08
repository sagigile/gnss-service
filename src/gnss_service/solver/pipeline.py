"""Library entry point around the vendored GNSS solver.

``legacy_main.py`` is the original NaviProject script, kept unmodified. This
module re-uses its functions with explicit input/output paths and returns
quality metrics instead of printing.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import legacy_main as solver


class SolverError(Exception):
    """Raised when the input cannot be processed into a track."""


@dataclass(frozen=True)
class ProcessResult:
    raw_csv: Path
    clean_csv: Path
    clean_kml: Path
    metrics: dict


def process(obs_path: Path, nav_path: Path, out_dir: Path) -> ProcessResult:
    obs_path, nav_path, out_dir = Path(obs_path), Path(nav_path), Path(out_dir)
    for p in (obs_path, nav_path):
        if not p.is_file():
            raise SolverError(f"file not found: {p.name}")
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        nav = solver.parse_nav_rinex(nav_path)
        epochs = solver.parse_obs_rinex(obs_path)
    except Exception as exc:  # parser raises assorted errors on malformed input
        raise SolverError(f"could not parse RINEX input: {exc}") from exc
    if not epochs:
        raise SolverError("no observation epochs found in OBS file")

    solutions = []
    prev_state = prev_prev_state = None
    prev_time = prev_prev_time = None
    for epoch in epochs:
        sol = solver.solve_epoch_position(
            epoch=epoch,
            nav=nav,
            prev_state=prev_state,
            prev_prev_state=prev_prev_state,
            prev_time=prev_time,
            prev_prev_time=prev_prev_time,
        )
        if sol:
            prev_prev_state, prev_prev_time = prev_state, prev_time
            prev_state, prev_time = sol["state_vec"], sol["time"]
            solutions.append(sol)
    if not solutions:
        raise SolverError("no valid GNSS solutions were found")

    raw_df = pd.DataFrame(solutions)
    raw_df["time"] = pd.to_datetime(raw_df["time"], utc=True)
    raw_df = raw_df.drop(columns=["state_vec"], errors="ignore")
    raw_df = solver.add_lla_and_velocity(raw_df)
    clean_df = solver.clean_track(raw_df)

    raw_out = raw_df.copy()
    raw_out["kept_measurement"] = clean_df["kept_measurement"].values
    raw_out["utc_time"] = raw_out["time"].dt.strftime("%Y-%m-%d %H:%M:%S")
    raw_csv = out_dir / "raw.csv"
    raw_out[solver.RAW_CSV_COLUMNS].to_csv(raw_csv, index=False)

    kept = clean_df[clean_df["kept_measurement"]].copy()
    clean_csv = out_dir / "clean.csv"
    clean_kml = out_dir / "clean.kml"
    kept[solver.CLEAN_CSV_COLUMNS].to_csv(clean_csv, index=False)
    solver.write_kml_points(kept, clean_kml)

    metrics = {
        "epochs_in_obs": len(epochs),
        "epochs_solved": len(raw_df),
        "points_kept": int(len(kept)),
        "mean_pdop": float(raw_df["pdop"].mean()),
        "mean_rms_residual_m": float(raw_df["rms_residual_m"].mean()),
        "mean_num_sats": float(raw_df["num_sats"].mean()),
    }
    return ProcessResult(raw_csv, clean_csv, clean_kml, metrics)
