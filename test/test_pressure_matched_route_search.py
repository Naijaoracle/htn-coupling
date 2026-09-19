import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_pressure_matched_route_search as search


def test_coarse_grid_requires_stationary_direct_target():
    direct = pd.DataFrame([{
        "target": "mild", "status": "ok", "stationarity_pass": False,
        "requested_systolic_mmHg": 130.0, "requested_diastolic_mmHg": 80.0,
        "systolic_mmHg": 130.0, "diastolic_mmHg": 80.0,
    }])
    assert search.coarse_jobs(direct) == []

    direct.loc[0, "stationarity_pass"] = True
    assert search.coarse_jobs(direct)


def test_nonstationary_evaluations_cannot_seed_refinement():
    evaluations = pd.DataFrame([
        {"target": "mild", "status": "ok", "stationarity_pass": True,
         "R": 1.0, "C": 0.8, "J": 1.0},
        {"target": "mild", "status": "ok", "stationarity_pass": False,
         "R": 1.1, "C": 0.8, "J": 0.0},
    ])
    minima = search._local_minima(evaluations, "mild", 0.1)
    assert minima == [{"R": 1.0, "C": 0.8, "J": 1.0}]


def test_missing_stationarity_column_fails_closed():
    evaluations = pd.DataFrame([
        {"target": "mild", "status": "ok", "R": 1.0, "C": 0.8, "J": 1.0},
    ])
    assert search._local_minima(evaluations, "mild", 0.1) == []
