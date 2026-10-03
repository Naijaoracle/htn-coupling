from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "public_demo"
sys.path.insert(0, str(DEMO))

import generate_synthetic_demo as gen  # noqa: E402

SPEC = json.loads((DEMO / "synthetic_demo_spec.json").read_text())

FORBIDDEN_TEXT = re.compile(
    r"(/home/|/tmp/|/Users/|[A-Za-z]:\\|Downloads/|[\w.+-]+@[\w-]+\.[a-z]{2,}|BEGIN (RSA|OPENSSH|PRIVATE)|"
    r"\.wav\b|\.mp4\b|\.mov\b|\.csv\b|\d{4}-\d{2}-\d{2}T|[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5})", re.I)
FORBIDDEN_KEY = re.compile(r"(raw|session|take_id|device|serial|wall|epoch|timestamp|participant_id|h10|ipad|path)", re.I)


@pytest.fixture(scope="module")
def bundle():
    return gen.build(SPEC)


def walk(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield path + "/" + k, "key", k
            yield from walk(v, path + "/" + k)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from walk(v, f"{path}[{i}]")
    else:
        yield path, "value", o


def test_declares_synthetic_and_no_participant_data(bundle):
    assert bundle["data_class"] == "synthetic"
    assert bundle["participant_data"] is False
    assert bundle["badge"] == "SYNTHETIC DATA"
    assert "not participant recordings" in bundle["banner"]


def test_every_signal_carries_provenance_and_unvalidated_flags(bundle):
    for s in bundle["signals"]:
        assert s["source"] and s["processing_stage"] in {"synthetic_observation", "synthetic_latent_state"}
        if s["processing_stage"] == "synthetic_observation" and s["name"] != "synthetic_hr":
            assert s["validated_forward_model"] is False


def test_no_paths_emails_dates_device_ids_or_raw_fields(bundle):
    for path, kind, item in walk(bundle):
        if kind == "key":
            assert not FORBIDDEN_KEY.search(item), path
        elif isinstance(item, str):
            assert not FORBIDDEN_TEXT.search(item), (path, item)
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            assert abs(item) < 1e9, (path, item)  # no epoch-scale values (seed is the only large integer)


def test_deterministic_for_a_seed_and_different_across_seeds():
    a, b = gen.build(SPEC), gen.build(SPEC)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    other = gen.build({**SPEC, "seed": SPEC["seed"] + 1})
    assert json.dumps(a["signals"][1]) != json.dumps(other["signals"][1])


def test_real_estimators_recover_the_synthetic_latent_rate(bundle):
    latent = np.array(bundle["signals"][0]["values"])
    series = bundle["rppg_estimates"]["series_bpm"]
    assert {"y", "pos", "chrom"} <= set(series)
    for rows in series.values():
        assert len(rows) >= 10
        for t, bpm in rows:
            assert abs(bpm - np.interp(t, np.arange(len(latent)), latent)) < 12


def test_forecast_branches_are_labelled_and_not_attributed_to_real_models(bundle):
    names = {b["name"]: b for b in bundle["forecast"]["branches"]}
    assert names["persistence"]["kind"].startswith("baseline_computed")
    for key in ("synthetic_ml_style", "synthetic_mechanistic_style"):
        assert names[key]["kind"] == "illustrative_curve_not_model_output"
    text = json.dumps(bundle["forecast"])
    assert "TimesFM" in text and "No TimesFM or Pulse model was run" in text
    assert not any("timesfm" in n.lower() or "pulse" in n.lower() for n in names)


def test_research_results_are_separate_aggregates_only(bundle):
    rr = bundle["research_results"]
    assert rr["data_class"] == "aggregate_experimental"
    assert all(set(r) == {"recovery", "timesfm", "pulse", "persistence", "linear"} for r in rr["rows"])
    assert "research_results" not in {s["name"] for s in bundle["signals"]}


def test_generator_cli_has_no_input_dataset_argument():
    import argparse
    seen = {}
    real = argparse.ArgumentParser.add_argument

    def spy(self, *names, **kw):
        seen.update({n: kw for n in names})
        return real(self, *names, **kw)

    argparse.ArgumentParser.add_argument = spy
    try:
        with pytest.raises(SystemExit):
            gen.main(["--help"])
    finally:
        argparse.ArgumentParser.add_argument = real
    assert set(seen) - {"-h", "--help"} == {"--spec", "--output", "--exchange-csv"}


def test_generator_source_never_references_private_recordings():
    src = (DEMO / "generate_synthetic_demo.py").read_text()
    tree = ast.parse(src)
    strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    banned = re.compile(r"six_take|h10|ipad|\.csv|read_csv|examples|recovery_[123]", re.I)
    assert not [s for s in strings if banned.search(s) and "docstring" not in s and len(s) < 80], strings
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "read_csv"]
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert "pandas" not in imported


def test_exchange_csv_loads_in_dashboard_contract_and_stays_honest(bundle, tmp_path):
    import io
    import csv
    sys.path.insert(0, str(ROOT / "multimodal_demo_next"))
    from data_contract import load_observations
    rows = gen.exchange_rows(bundle)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=gen.EXCHANGE_COLUMNS)
    w.writeheader()
    w.writerows(rows)
    frame = load_observations(buf.getvalue().encode())
    assert set(frame["layer"]) == {"latent", "synthetic_observation", "estimate", "forecast"}
    assert "sensor" not in set(frame["layer"])
    assert not any(FORBIDDEN_KEY.search(c) for c in frame.columns)
    assert not frame["source"].str.contains(r"timesfm|\bpulse\b|h10|ipad", case=False).any()
    assert frame["time_s"].between(0, 60).all()
