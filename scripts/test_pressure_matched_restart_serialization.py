#!/usr/bin/env python3
"""Regression for cardiovascular modifiers and Stage 7 state across checkpoints.

Run against a Pulse build that includes the checkpoint schema change by setting
PULSE_ROOT. The archived post-action states predate that field, so this test
injects the known action coordinates into the typed protobuf state, loads it,
saves it again, and compares both fresh-engine continuations with the archived
uninterrupted traces.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd
from google.protobuf.json_format import MessageToJson, ParseDict

ROOT = Path(__file__).resolve().parents[1]
PULSE = Path(os.environ.get("PULSE_ROOT", "/tmp/pulse-stage7-diagnostic"))
PREFIX = PULSE / "build/install"
BIN = PREFIX / "bin"
PYTHON = PREFIX / "python"
sys.path[:0] = [str(PYTHON), str(BIN)]

from pulse.cdm.engine import eSerializationFormat
from pulse.cdm.scalars import VolumeUnit
from pulse.engine.PulseEngine import PulseEngine
from pulse.engine.bind.State_pb2 import StateData

OUT = ROOT / "results/pressure_matched_routes/private/restart_transition_diagnostic"
CASES = {
    "mild_R1.300_C0.720": (1.300, 0.720, True),
    "intermediate_R1.720_C0.600": (1.720, 0.600, False),
}


def make_manager(symbols, path: Path | None = None):
    manager = symbols["requests"](symbols)
    requests = manager.get_data_requests()
    for prop, unit_type, unit_value in (
        ("BloodVolume", "VolumeUnit", "mL"),
        ("IntracranialPressure", "PressureUnit", "mmHg"),
        ("CerebralPerfusionPressure", "PressureUnit", "mmHg"),
        ("BaroreceptorResetMidpoint", "PressureUnit", "mmHg"),
    ):
        requests.append(symbols["SEDataRequest"].create_physiology_request(
            prop, getattr(symbols[unit_type], unit_value)))
    manager.set_data_requests(requests)
    if path is not None:
        manager.set_results_filename(str(path))
        manager.set_samples_per_second(50)
    return manager


def capture(engine, manager, path: Path):
    headers = ["Time(s)"] + [str(req) for req in manager.get_data_requests()]
    rows = []
    for _ in range(600):
        if not engine.advance_time_s(0.02):
            raise RuntimeError("engine stopped during 12-second continuation")
        rows.append(engine.pull_data().copy())
    pd.DataFrame(rows, columns=headers).to_csv(path, index=False)


def load_engine(symbols, state_text: str, name: str, manager=None):
    manager = manager or make_manager(symbols)
    engine = symbols["PulseEngine"](data_root_dir=str(BIN))
    engine.log_to_console(False)
    engine.set_log_filename(str(OUT / f"{name}.log"))
    if not engine.serialize_from_string(state_text, manager, eSerializationFormat.JSON):
        raise RuntimeError(f"checkpoint load failed: {name}")
    return engine, manager


def assert_trace_matches(reference: Path, actual: Path, case: str):
    expected = pd.read_csv(reference)
    got = pd.read_csv(actual)
    if list(expected.columns) != list(got.columns):
        raise AssertionError(f"column mismatch for {case}: {list(expected.columns)} != {list(got.columns)}")
    errors = (expected.astype(float) - got.astype(float)).abs()
    maximum = errors.max().max()
    if maximum != 0.0:
        worst = errors.max().sort_values(ascending=False).head(5).to_dict()
        raise AssertionError(f"trace mismatch for {case}: max_abs_error={maximum}; worst={worst}")


def main():
    import run_stage6_bounds as stage6
    symbols = stage6.pulse_symbols()
    symbols["requests"] = stage6.requests
    symbols["VolumeUnit"] = VolumeUnit
    result = {}
    for case, (resistance, compliance, stage7) in CASES.items():
        case_dir = OUT / case
        saved = json.loads((case_dir / "post_action_state.json").read_text())
        state = ParseDict(saved, StateData())
        mods = state.Cardiovascular.MechanicsModifiers
        mods.SystemicResistanceMultiplier.ScalarUnsigned.Value = resistance
        mods.ArterialComplianceMultiplier.ScalarUnsigned.Value = compliance
        state.Nervous.Stage7ResettingEnabled = stage7
        text = MessageToJson(state, preserving_proto_field_name=True)

        first_path = case_dir / "serialization_regression_first.csv"
        first_manager = make_manager(symbols, first_path)
        first, first_manager = load_engine(symbols, text, f"{case}_serialization_first", first_manager)
        roundtrip_path = case_dir / "serialization_regression_roundtrip.json"
        if not first.serialize_to_file(str(roundtrip_path)):
            raise RuntimeError(f"checkpoint save failed: {case}")
        roundtrip = json.loads(roundtrip_path.read_text())
        cardiovascular = roundtrip["Cardiovascular"]["MechanicsModifiers"]
        assert cardiovascular["SystemicResistanceMultiplier"]["ScalarUnsigned"]["Value"] == resistance
        assert cardiovascular["ArterialComplianceMultiplier"]["ScalarUnsigned"]["Value"] == compliance
        assert roundtrip["Nervous"].get("Stage7ResettingEnabled", False) is stage7
        capture(first, first_manager, first_path)
        assert_trace_matches(case_dir / "normal_continuation.csv", first_path, case)

        second_path = case_dir / "serialization_regression_second.csv"
        second_manager = make_manager(symbols, second_path)
        second, second_manager = load_engine(
            symbols, roundtrip_path.read_text(), f"{case}_serialization_second", second_manager)
        capture(second, second_manager, second_path)
        assert_trace_matches(case_dir / "normal_continuation.csv", second_path, case)
        result[case] = {"max_abs_diff_first_reload": 0.0,
                        "max_abs_diff_second_reload": 0.0,
                        "resistance_multiplier": resistance,
                        "compliance_multiplier": compliance,
                        "stage7_enabled": stage7}
        print(case, result[case])
    summary = OUT / "checkpoint_serialization_regression.json"
    summary.write_text(json.dumps({"pulse_root": str(PULSE), "cases": result}, indent=2) + "\n")
    print("wrote", summary)


if __name__ == "__main__":
    main()
