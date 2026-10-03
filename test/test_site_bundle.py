from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "public_demo"))

import build_site_bundle as bsb  # noqa: E402


def test_builder_refuses_a_csv_that_is_not_entirely_synthetic(tmp_path):
    csv = tmp_path / "session.csv"
    csv.write_text("time_s,channel,value,unit,layer,source\n0,h,60,bpm,sensor,SomeDevice\n")
    args = type("A", (), {"session_csv": csv, "spec": ROOT / "public_demo/synthetic_demo_spec.json",
                          "pulse_candidates": csv, "model_episode": csv})()
    with pytest.raises(SystemExit, match="not entirely data_class=synthetic"):
        bsb.build(args)


def test_builder_has_no_hidden_input_beyond_declared_synthetic_files():
    import argparse
    seen, real = {}, argparse.ArgumentParser.add_argument

    def spy(self, *names, **kw):
        seen.update({n: kw for n in names})
        return real(self, *names, **kw)

    argparse.ArgumentParser.add_argument = spy
    try:
        with pytest.raises(SystemExit):
            bsb.main(["--help"])
    finally:
        argparse.ArgumentParser.add_argument = real
    assert set(seen) - {"-h", "--help"} == {"--session-csv", "--pulse-candidates", "--model-episode", "--spec", "--output-dir"}


def test_committed_model_episode_is_model_output_only():
    m = json.loads((ROOT / "public_demo/model_episode_pulse_openbf.json").read_text())
    assert "no participant data" in m["source"]
    assert set(m["state"]) == {"Aortic inflow", "Aortic pressure", "Heart rate", "External carotid flow", "External carotid pressure"}
    assert not re.search(r"(/home/|@|\.csv|\.wav|H10|iPad)", json.dumps(m))
