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


def test_coarse_search_checkpoints_and_skips_completed_points(tmp_path, monkeypatch):
    monkeypatch.setattr(search, "OUT", tmp_path)
    pd.DataFrame([{"target": "mild", "status": "ok", "stationarity_pass": True}]).to_csv(
        tmp_path / "direct_states.csv", index=False)
    jobs = [
        {"case_id": f"coarse_{index}", "target": "mild", "R": 1.0 + index * 0.1,
         "C": 0.8, "achieved_systolic_mmHg": 130.0,
         "achieved_diastolic_mmHg": 80.0}
        for index in range(3)
    ]
    monkeypatch.setattr(search, "coarse_jobs", lambda direct: jobs)
    submitted = []

    def fake_run_jobs(batch, workers):
        submitted.extend(batch)
        return [{**job, "status": "ok", "systolic_mmHg": 130.0,
                 "diastolic_mmHg": 80.0} for job in batch]

    monkeypatch.setattr(search, "run_jobs", fake_run_jobs)
    first = search.coarse_search(workers=1)
    second = search.coarse_search(workers=1)
    assert len(first) == 3
    assert len(second) == 3
    assert len(submitted) == 3


def test_finer_refinement_seeds_only_from_immediately_preceding_grid():
    rows = []
    for r in (1.0, 1.1):
        rows.append({"target": "higher", "status": "ok", "stationarity_pass": True,
                     "R": r, "C": 0.4, "J": -100.0, "refinement_step": float("nan")})
    for r in (1.48, 1.50, 1.52):
        for c in (0.58, 0.60, 0.62):
            rows.append({"target": "higher", "status": "ok", "stationarity_pass": True,
                         "R": r, "C": c, "J": 0.0 if (r, c) == (1.50, 0.60) else 1.0,
                         "refinement_step": 0.02})
    mixed = pd.DataFrame(rows)
    # The old mixed-grid call admitted isolated coarse points as minima.
    assert len(search._local_minima(mixed, "higher", 0.02)) > 1
    seed_frame = search._refinement_seed_frame(mixed, previous=0.02, coarse_spacing=0.1)
    minima = search._local_minima(seed_frame, "higher", 0.02)
    assert minima == [{"R": 1.5, "C": 0.6, "J": 0.0}]
    assert set(seed_frame.refinement_step.unique()) == {0.02}
