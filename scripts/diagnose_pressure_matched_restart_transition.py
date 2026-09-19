#!/usr/bin/env python3
"""Bounded two-setting test of accumulated baroreflex scales at modifier restart.

For each saved low-target modifier setting, run the ordinary non-incremental
mechanics action, save the exact post-stabilization state, then compare normal
continuation with a diagnostic-only branch that resets four baroreflex scales
to 1.0 before resuming. The modified branch is an engineering control, never a
primary result. The state is tracked throughout stabilization at 50 Hz.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PULSE = Path(os.environ.get("PULSE_ROOT", "/tmp/pulse-htn-a04"))
BIN = PULSE / "build/install/bin"
PYTHON = PULSE / "build/install/python"
if str(PYTHON) not in sys.path:
    sys.path.insert(0, str(PYTHON))

sys.path.insert(0, str(ROOT / "scripts"))
import run_stage6_bounds as stage6

OUT = ROOT / "results/pressure_matched_routes/private/restart_transition_diagnostic"
STATE = ROOT / "results/stage2/private/cache/StandardMale_stage2_baseline.json"
CASES = {
    "mild_R1.300_C0.720": (1.300, 0.720),
    "intermediate_R1.720_C0.600": (1.720, 0.600),
}
SCALE_KEYS = (
    "BaroreceptorHeartRateScale", "BaroreceptorHeartElastanceScale",
    "BaroreceptorResistanceScale", "BaroreceptorComplianceScale",
)
EXTRA_REQUESTS = (
    ("BloodVolume", "VolumeUnit", "mL"),
    ("IntracranialPressure", "PressureUnit", "mmHg"),
    ("CerebralPerfusionPressure", "PressureUnit", "mmHg"),
    ("BaroreceptorResetMidpoint", "PressureUnit", "mmHg"),
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def manager_for(symbols, result_file: Path | None = None):
    manager = stage6.requests(symbols)
    existing = manager.get_data_requests()
    from pulse.cdm.scalars import VolumeUnit
    symbols["VolumeUnit"] = VolumeUnit
    for prop, unit_name, unit_value in EXTRA_REQUESTS:
        unit = getattr(symbols[unit_name], unit_value)
        existing.append(symbols["SEDataRequest"].create_physiology_request(prop, unit))
    manager.set_data_requests(existing)
    if result_file is not None:
        manager.set_results_filename(str(result_file))
        manager.set_samples_per_second(50)
    return manager


def pulse_headers(manager) -> list[str]:
    return ["Time(s)"] + [str(req) for req in manager.get_data_requests()]


def row(engine, headers):
    return dict(zip(headers, engine.pull_data().copy()))


def capture(engine, manager, seconds: float, path: Path):
    headers = pulse_headers(manager)
    rows = []
    count = int(round(seconds / 0.02))
    for _ in range(count):
        if not engine.advance_time_s(0.02):
            raise RuntimeError(f"Pulse stopped during {seconds:g}s post-action trace")
        rows.append(row(engine, headers))
    import pandas as pd
    frame = pd.DataFrame(rows)
    frame.to_csv(path, index=False)
    fields = ["SystolicArterialPressure(mmHg)", "DiastolicArterialPressure(mmHg)",
              "MeanArterialPressure(mmHg)", "HeartRate(1/min)",
              "SystemicVascularResistance(mmHg_s/mL)", "BaroreceptorHeartRateScale",
              "BaroreceptorHeartElastanceScale", "BaroreceptorResistanceScale",
              "BaroreceptorComplianceScale", "BaroreceptorResetMidpoint(mmHg)"]
    summary = {}
    for field in fields:
        if field in frame:
            x = frame[field].astype(float)
            summary[field] = {"first": float(x.iloc[0]), "last": float(x.iloc[-1]),
                              "min": float(x.min()), "max": float(x.max())}
    for cutoff in (0.5, 1.0, 2.0, 5.0, 10.0):
        window = frame[frame["Time(s)"].astype(float) <= float(frame["Time(s)"].iloc[0]) + cutoff]
        if len(window):
            summary[f"first_{cutoff:g}s"] = {
                key: float(window[key].iloc[-1]) for key in fields if key in window
            }
    return summary


def engine_for(symbols, manager, log: Path):
    engine = symbols["PulseEngine"](data_root_dir=str(BIN))
    engine.log_to_console(False)
    engine.set_log_filename(str(log))
    if not engine.serialize_from_file(str(STATE), manager):
        raise RuntimeError("stock state load failed")
    return engine


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    symbols = stage6.pulse_symbols()
    revision = subprocess.check_output(["git", "-C", str(PULSE), "rev-parse", "HEAD"], text=True).strip()
    from pulse.cdm.engine import eSerializationFormat
    symbols["eSerializationFormat"] = eSerializationFormat
    results = {"pulse_revision": revision,
               "purpose": "diagnostic-only post-stabilization state perturbation; not a primary result",
               "reset_scales": list(SCALE_KEYS), "sample_interval_s": 0.02, "cases": {}}
    for name, (resistance, compliance) in CASES.items():
        case_dir = OUT / name
        case_dir.mkdir(parents=True, exist_ok=True)
        manager = manager_for(symbols, case_dir / "during_stabilization.csv")
        engine = engine_for(symbols, manager, case_dir / "pulse.log")
        action = symbols["SECardiovascularMechanicsModification"]()
        action.get_modifiers().get_systemic_resistance_multiplier().set_value(resistance)
        action.get_modifiers().get_arterial_compliance_multiplier().set_value(compliance)
        started = time.monotonic()
        engine.process_action(action)
        state_path = case_dir / "post_action_state.json"
        if not engine.serialize_to_file(str(state_path)):
            raise RuntimeError(f"could not serialize post-action state for {name}")
        state = state_path.read_text()
        state_obj = json.loads(state)
        nervous = state_obj["Nervous"]["Common"]
        before = {key: nervous[key].get("Value") for key in SCALE_KEYS}
        enabled = nervous.get("BaroreceptorFeedback")
        state_bytes = state_path.read_bytes()
        baseline_summary = capture(engine, manager, 12.0, case_dir / "normal_continuation.csv")

        changed = json.loads(state)
        changed_nervous = changed["Nervous"]["Common"]
        for key in SCALE_KEYS:
            changed_nervous[key] = {"Value": 1.0}
        changed_state = json.dumps(changed, separators=(",", ":"))
        control_manager = manager_for(symbols)
        control = symbols["PulseEngine"](data_root_dir=str(BIN))
        control.log_to_console(False)
        control.set_log_filename(str(case_dir / "reset_scales_control.log"))
        if not control.serialize_from_string(changed_state, control_manager,
                                             symbols["eSerializationFormat"].JSON):
            raise RuntimeError(f"modified-state control load failed for {name}")
        control_summary = capture(control, control_manager, 12.0,
                                  case_dir / "reset_scales_control.csv")
        changed_scale_keys = [key for key in SCALE_KEYS
                              if float(before[key]) != 1.0]
        results["cases"][name] = {
            "resistance_multiplier": resistance,
            "compliance_multiplier": compliance,
            "post_action_sim_time_s": float(state_obj["SimulationTime"].get("ScalarTime", {}).get("Value", 0.0)) if isinstance(state_obj["SimulationTime"], dict) else float(state_obj["SimulationTime"]),
            "post_action_feedback_switch": enabled,
            "post_action_baroreflex_scales": before,
            "post_action_reset_midpoint_mmHg": state_obj["Nervous"].get(
                "BaroreceptorResetMidpoint_mmHg"),
            "post_action_state_sha256": sha256_bytes(state_bytes),
            "reset_control_changed_scales": changed_scale_keys,
            "reset_control_semantically_same_state": changed == state_obj,
            "normal_continuation": baseline_summary,
            "reset_scales_control": control_summary,
            "wall_s_including_12s_normal_and_control_traces": time.monotonic() - started,
            "outputs": ["during_stabilization.csv", "normal_continuation.csv",
                        "reset_scales_control.csv", "post_action_state.json",
                        "pulse.log", "reset_scales_control.log"],
        }
        (OUT / "summary.json").write_text(json.dumps(results, indent=2) + "\n")
        print(name, json.dumps(results["cases"][name], indent=2))
    print(f"Saved diagnostic summary: {OUT / 'summary.json'}")


if __name__ == "__main__":
    main()
