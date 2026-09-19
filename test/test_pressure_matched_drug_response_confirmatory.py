import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pressure_matched_drug_response_common as common


def test_baseline_window_is_half_open_30_in_60_out():
    rows = [{"elapsed_s": t, "value": t} for t in (29, 30, 59, 60)]
    assert [r["elapsed_s"] for r in common.baseline_window_rows(rows)] == [30, 59]


def test_execution_matrix_has_twelve_unique_fresh_challenge_directories(tmp_path):
    matrix = common.execution_matrix()
    paths = [common.case_directory(tmp_path, t, r, rep, "challenge") for t, r, rep in matrix]
    assert len(matrix) == 12
    assert len(set(paths)) == 12
    assert {p.name for p in paths} == {"challenge"}
    assert {p.parent.name for p in paths} == {"direct", "modifier"}
    assert {p.parent.parent.name for p in paths} == {"replicate_01", "replicate_02"}
    baseline_paths = [common.case_directory(tmp_path, t, r, rep, "baseline")
                      for t, r, rep in common.execution_matrix()]
    assert len(set(baseline_paths)) == 12
    assert all(a != b for a, b in zip(paths, baseline_paths))


def test_pair_gate_requires_pressure_match_and_stationarity():
    direct = {"systolic_mmHg": 140.0, "diastolic_mmHg": 90.0, "stationarity_pass": True}
    modifier = {"systolic_mmHg": 140.2, "diastolic_mmHg": 89.9, "stationarity_pass": True}
    assert common.pair_gate_passes(direct, modifier)
    modifier["diastolic_mmHg"] = 90.251
    assert not common.pair_gate_passes(direct, modifier)
    modifier["diastolic_mmHg"] = 89.9
    modifier["stationarity_pass"] = False
    assert not common.pair_gate_passes(direct, modifier)


def test_challenge_gate_checks_fresh_baseline_against_screened_peer():
    challenged = {"systolic_mmHg": 140.1, "diastolic_mmHg": 90.0, "stationarity_pass": True}
    peer = {"systolic_mmHg": 140.0, "diastolic_mmHg": 90.2}
    assert common.challenge_gate_passes(challenged, peer)
    challenged["systolic_mmHg"] = 140.251
    assert not common.challenge_gate_passes(challenged, peer)


def test_repeatability_report_compares_full_numeric_traces_and_event_times(tmp_path, monkeypatch):
    import json
    import pandas as pd
    import run_pressure_matched_drug_response_confirmatory as runner

    monkeypatch.setattr(runner, "OUT", tmp_path)
    for replicate in (1, 2):
        case = common.case_directory(tmp_path, "mild", "direct", replicate, "challenge")
        case.mkdir(parents=True)
        summary = {
            "status": "challenge_complete",
            "event_first_observed_elapsed_s": {"Hypernatremia": 93},
        }
        (case / "summary.json").write_text(json.dumps(summary))
        pd.DataFrame({"elapsed_s": [1, 2], "pressure": [100.0, 101.0],
                      "sodium": [142.0, 143.0]}).to_csv(
            case / "challenge_trace.csv.gz", index=False, compression="gzip")
    report = runner.summarize_repeatability({})
    pair = report["mild/direct"]
    assert pair["status"] == "compared"
    assert pair["exact_numeric_trace_match"]
    assert pair["event_onsets_identical"]

    case = common.case_directory(tmp_path, "mild", "direct", 2, "challenge")
    pd.DataFrame({"elapsed_s": [1, 2], "pressure": [100.0, 101.1],
                  "sodium": [142.0, 143.0]}).to_csv(
        case / "challenge_trace.csv.gz", index=False, compression="gzip")
    pair = runner.summarize_repeatability({})["mild/direct"]
    assert pair["max_abs_numeric_difference"]["pressure"] > 0
    assert not pair["exact_numeric_trace_match"]


def test_attempt_labels_keep_runs_separate_and_reject_path_traversal(tmp_path):
    assert common.attempt_output_directory(tmp_path, "confirmatory_retry_01") == tmp_path / "confirmatory_retry_01"
    for invalid in ("../escape", "..", "", "space not allowed"):
        try:
            common.attempt_output_directory(tmp_path, invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted invalid attempt label {invalid!r}")


def test_pair_decision_keeps_stdin_open_for_communicate():
    import subprocess
    import sys
    import run_pressure_matched_drug_response_confirmatory as runner

    child = subprocess.Popen([sys.executable, "-c", "print(input())"], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, text=True)
    runner.send_pair_decision(child, "GO")
    stdout, _ = child.communicate(timeout=5)
    assert stdout.strip() == "GO"
    assert child.returncode == 0
