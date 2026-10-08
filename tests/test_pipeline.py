from pathlib import Path

import pandas as pd
import pytest

from gnss_service.solver.pipeline import SolverError, process

DATA = Path(__file__).parent / "data"
NAV = DATA / "samsung_nav.nav.rnx"


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    return process(DATA / "my_data_3.obs", NAV, tmp_path_factory.mktemp("out"))


def test_outputs_created(result):
    assert result.raw_csv.is_file()
    assert result.clean_csv.is_file()
    assert result.clean_kml.read_text(encoding="utf-8").lstrip().startswith("<?xml")


def test_clean_csv_matches_original_repo_output(result):
    """Wrapper must reproduce the CSV committed in NaviProject (same solver)."""
    # initial_guess_method is excluded: both initial guesses converge to the
    # same solution and the label is picked by ~1e-9 float noise in the RMS.
    drop = ["initial_guess_method"]
    got = pd.read_csv(result.clean_csv).drop(columns=drop)
    want = pd.read_csv(DATA / "golden_clean_short_path.csv").drop(columns=drop)
    pd.testing.assert_frame_equal(got, want, check_exact=False, rtol=1e-6, atol=1e-6)


def test_metrics_consistent(result):
    m = result.metrics
    assert m["points_kept"] == len(pd.read_csv(result.clean_csv))
    assert 0 < m["points_kept"] <= m["epochs_solved"] <= m["epochs_in_obs"]


def test_missing_file_raises(tmp_path):
    with pytest.raises(SolverError):
        process(tmp_path / "nope.obs", NAV, tmp_path / "out")


def test_garbage_obs_raises(tmp_path):
    bad = tmp_path / "bad.obs"
    bad.write_text("this is not a rinex file\n")
    with pytest.raises(SolverError):
        process(bad, NAV, tmp_path / "out")
