from __future__ import annotations

import ast
import csv
import io
import json
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "public_demo"))
sys.path.insert(0, str(ROOT / "multimodal_demo_next"))

import generate_synthetic_session_csv as gen  # noqa: E402
from data_contract import load_observations  # noqa: E402

SPEC = json.loads((ROOT / "public_demo/synthetic_session_spec.json").read_text())

# The exchange schema the dashboard expects (structure only; no values).
SCHEMA = ["time_s", "channel", "value", "unit", "layer", "source", "scenario", "episode_id", "episode_relationship",
          "clock_provenance", "alignment_status", "take_id", "take_time_s", "protocol_time_s", "phase", "alignment_method",
          "model_version", "parameterization", "processing_stage", "derived_from", "candidate_id", "exercise_intensity",
          "exercise_duration_s", "cessation_to_recovery_origin_delay_s", "conditioning_sigma_bpm"]
SERIES = {
    "h10_raw_ecg_rr_bpm", "h10_continuous_rr_bpm", "max_ir_blind_winner_bpm", "max_red_blind_winner_bpm",
    "pcg_cardio_near_candidate", "pcg_dominant_event_rate", "pcg_secondary_event_rate", "chrom_blind_winner_bpm",
    "pos_blind_winner_bpm", "y_blind_winner_bpm", "heart_rate", "ad8232_ecg_raw_continuous_25hz",
    "pcg_band_rms_20_400hz_ch1", "pcg_band_rms_20_400hz_ch2", "max_ir_raw_continuous", "max_red_raw_continuous",
    "camera_frame_difference_proxy", "camera_mean_blue", "camera_mean_green", "camera_mean_luma", "camera_mean_red"}
TAKES = {"rest_1", "rest_2", "rest_3", "recovery_1", "recovery_2", "recovery_3",
         "continuous_ESP32", "continuous_H10", "continuous_audio"}


@pytest.fixture(scope="module")
def frame():
    rows = gen.build(SPEC)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=gen.COLUMNS)
    w.writeheader()
    w.writerows(rows)
    return pd.read_csv(io.StringIO(buf.getvalue()), low_memory=False)


def test_preserves_exchange_structure(frame):
    assert list(frame.columns) == SCHEMA + ["data_class"]
    assert set(frame["channel"]) == SERIES
    assert set(frame["take_id"].dropna()) == TAKES
    assert set(frame["episode_relationship"]) == {"same_episode", "comparable_scenario"}
    assert frame["candidate_id"].dropna().nunique() == 72
    assert len(frame) > 100_000


def test_every_row_is_labelled_synthetic_and_honest(frame):
    assert (frame["data_class"] == "synthetic").all()
    assert frame["source"].str.startswith("SYNTH:").all()
    assert set(frame["layer"]) == {"synthetic_observation", "estimate", "latent"}
    assert "sensor" not in set(frame["layer"])
    latent = frame[frame["layer"] == "latent"]
    assert latent["derived_from"].str.contains("Pulse was not run").all()
    assert not latent["parameterization"].str.contains("StandardMale").any()


def test_no_paths_emails_dates_or_epoch_scale_values(frame):
    bad = re.compile(r"(/home/|/tmp/|/Users/|[A-Za-z]:\\|@[\w-]+\.[a-z]{2,}|\d{4}-\d{2}-\d{2}T|\.wav\b|\.mp4\b)", re.I)
    for col in frame.select_dtypes(include="object"):
        assert not frame[col].dropna().astype(str).str.contains(bad).any(), col
    assert frame["time_s"].abs().max() < 1e4
    assert frame["value"].abs().max() < 1e7


def test_deterministic_for_a_seed(frame):
    again = gen.build(SPEC)
    assert len(again) == len(frame)
    assert gen.build(SPEC) == again
    assert gen.build({**SPEC, "seed": SPEC["seed"] + 1}) != again


def test_loader_shim_runs_panels_in_memory_and_keeps_data_class(frame):
    text = frame.to_csv(index=False).encode()
    loaded = load_observations(text)
    assert (loaded["data_class"] == "synthetic").all()
    assert not loaded["source"].str.startswith("SYNTH:").any()
    assert {"sensor", "estimate", "latent"} == set(loaded["layer"])
    assert (loaded[loaded["layer"] == "latent"]["source"] == "Pulse").all()
    assert (loaded["processing_stage"] == "hr_constrained_pulse_ensemble_candidate_v1").any()


def test_loader_leaves_non_synthetic_files_untouched():
    raw = pd.DataFrame({"time_s": [0.0, 1.0], "channel": ["h", "h"], "value": [60.0, 61.0], "unit": ["bpm"] * 2,
                        "layer": ["sensor"] * 2, "source": ["SYNTH:x", "SYNTH:x"]})
    out = load_observations(raw.to_csv(index=False).encode())
    assert (out["source"] == "SYNTH:x").all() and set(out["layer"]) == {"sensor"}


def test_cli_has_only_spec_and_output_and_never_reads_recordings():
    import argparse
    seen, real = {}, argparse.ArgumentParser.add_argument

    def spy(self, *names, **kw):
        seen.update({n: kw for n in names})
        return real(self, *names, **kw)

    argparse.ArgumentParser.add_argument = spy
    try:
        with pytest.raises(SystemExit):
            gen.main(["--help"])
    finally:
        argparse.ArgumentParser.add_argument = real
    assert set(seen) - {"-h", "--help"} == {"--spec", "--output"}
    tree = ast.parse((ROOT / "public_demo/generate_synthetic_session_csv.py").read_text())
    strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and len(n.value) < 80]
    assert not [s for s in strings if re.search(r"six_take|examples|read_csv", s)]
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "read_csv"]
    assert "pandas" not in {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
