#!/usr/bin/env python3
"""Run the locked two-repeat pressure-matched norepinephrine confirmation.

Every baseline screen and challenge route runs in its own Pulse process. For a
challenge pair, both processes wait after their pre-infusion measurements;
the parent sends GO only after both baselines pass the pair and stationarity
rules. Full traces are written under the ignored private results namespace.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
CONFIG_PATH = ROOT / "config/pressure_matched_drug_response_confirmatory_v1.json"
PROTOCOL_PATH = ROOT / "docs/PRESSURE_MATCHED_DRUG_RESPONSE_CONFIRMATORY_PROTOCOL.md"
PULSE = Path(os.environ.get("PULSE_ROOT", "/tmp/pulse-checkpoint-restart"))
BIN = Path(os.environ.get("PULSE_BIN", "/tmp/pulse-checkpoint-install/bin"))
OUT_BASE = ROOT / "results/pressure_matched_drug_response_confirmatory/private"
OUT = OUT_BASE
ATTEMPT_LABEL = None
BASES = ROOT / "results/pressure_matched_routes_v2/private/cases"
STATE = ROOT / "results/stage2/private/cache/StandardMale_stage2_baseline.json"

sys.path.insert(0, str(SCRIPT_DIR))
import pressure_matched_drug_response_common as common


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_config():
    return json.loads(CONFIG_PATH.read_text())


def verify_locked_inputs(require_committed=True):
    cfg = load_config()
    pulse_sha = subprocess.check_output(["git", "-C", str(PULSE), "rev-parse", "HEAD"], text=True).strip()
    if pulse_sha != cfg["pulse_revision"]:
        raise RuntimeError(f"Pulse revision mismatch: expected {cfg['pulse_revision']}, found {pulse_sha}")
    expected_binding = pulse_sha[:9]
    binding_probe = subprocess.run(
        [sys.executable, "-c", "import PyPulse; print(PyPulse.__hash__)"],
        text=True, capture_output=True, env=child_env())
    if binding_probe.returncode or binding_probe.stdout.strip().splitlines()[-1] != expected_binding:
        raise RuntimeError(
            f"Pulse Python binding mismatch: expected {expected_binding}, "
            f"got {binding_probe.stdout.strip()} {binding_probe.stderr.strip()}")
    expected = cfg["source_states"]
    if digest(STATE) != expected["modifier_standardmale_checkpoint_sha256"]:
        raise RuntimeError("StandardMale source checkpoint SHA-256 mismatch")
    for target, expected_sha in expected["direct_patient_payload_sha256"].items():
        actual = digest(BASES / f"direct_{target}" / "patient.json")
        if actual != expected_sha:
            raise RuntimeError(f"Direct {target} patient payload SHA-256 mismatch")
    runner_path = Path(__file__).resolve()
    helper_path = SCRIPT_DIR / "pressure_matched_drug_response_common.py"
    test_path = ROOT / "test/test_pressure_matched_drug_response_confirmatory.py"
    if require_committed:
        for path in (CONFIG_PATH, PROTOCOL_PATH, runner_path, helper_path, test_path):
            rel = path.relative_to(ROOT).as_posix()
            subprocess.check_call(["git", "-C", str(ROOT), "cat-file", "-e", f"HEAD:{rel}"])
    return {
        "protocol": PROTOCOL_PATH.relative_to(ROOT).as_posix(),
        "protocol_sha256": digest(PROTOCOL_PATH),
        "configuration": CONFIG_PATH.relative_to(ROOT).as_posix(),
        "configuration_sha256": digest(CONFIG_PATH),
        "runner": runner_path.relative_to(ROOT).as_posix(),
        "runner_sha256": digest(runner_path),
        "helper": helper_path.relative_to(ROOT).as_posix(),
        "helper_sha256": digest(helper_path),
        "test": test_path.relative_to(ROOT).as_posix(),
        "test_sha256": digest(test_path),
        "pulse_revision": pulse_sha,
        "stage0_sha256": cfg["stage0_sha256"],
        "source_states": expected,
    }


def pulse_requests():
    os.environ["PULSE_ROOT"] = str(PULSE)
    os.environ["PULSE_BIN"] = str(BIN)
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    import run_stage6_bounds as stage6
    from pulse.cdm.engine import SEDataRequestManager, SEDataRequest
    from pulse.cdm.scalars import (AmountPerVolumeUnit, MassPerVolumeUnit, OsmolalityUnit,
                                   VolumePerTimeUnit, VolumeUnit)
    symbols = stage6.pulse_symbols()
    base = stage6.requests(symbols).get_data_requests()
    extra = [
        SEDataRequest.create_physiology_request("BloodVolume", VolumeUnit.mL),
        SEDataRequest.create_physiology_request("UrineProductionRate", VolumePerTimeUnit.mL_Per_min),
        SEDataRequest.create_physiology_request("UrineOsmolality", OsmolalityUnit.mOsm_Per_kg),
        SEDataRequest.create_physiology_request("RenalPlasmaFlow", VolumePerTimeUnit.mL_Per_min),
        SEDataRequest.create_liquid_compartment_request("LeftUreter", "InFlow", VolumePerTimeUnit.mL_Per_min),
        SEDataRequest.create_liquid_compartment_request("RightUreter", "InFlow", VolumePerTimeUnit.mL_Per_min),
        SEDataRequest.create_liquid_compartment_substance_request("LeftUreter", "Sodium", "Concentration", MassPerVolumeUnit.mg_Per_mL),
        SEDataRequest.create_liquid_compartment_substance_request("RightUreter", "Sodium", "Concentration", MassPerVolumeUnit.mg_Per_mL),
        SEDataRequest.create_liquid_compartment_substance_request("Aorta", "Sodium", "Molarity", AmountPerVolumeUnit.mEq_Per_L),
        SEDataRequest.create_liquid_compartment_substance_request("Aorta", "Sodium", "Concentration", MassPerVolumeUnit.mg_Per_mL),
    ]
    columns = stage6.COLUMNS + [
        "blood_volume_mL", "urine_production_mL_min", "urine_osmolality_mOsm_kg",
        "renal_plasma_flow_mL_min", "left_ureter_flow_mL_min", "right_ureter_flow_mL_min",
        "left_ureter_sodium_mg_mL", "right_ureter_sodium_mg_mL",
        "aortic_sodium_mEq_L", "aortic_sodium_mg_mL",
    ]
    return stage6, SEDataRequestManager(base + extra), columns


def initialize(target: str, route: str, case_dir: Path):
    stage6, requests, columns = pulse_requests()
    os.environ["PULSE_ROOT"] = str(PULSE)
    os.environ["PULSE_BIN"] = str(BIN)
    from pulse.cdm.patient import SEPatientConfiguration
    from pulse.cdm.patient_actions import SECardiovascularMechanicsModification
    from pulse.engine.PulseEngine import PulseEngine

    engine = PulseEngine(data_root_dir=str(BIN))
    engine.log_to_console(False)
    engine.set_log_filename(str(case_dir / "pulse.log"))
    if route == "direct":
        patient = BASES / f"direct_{target}" / "patient.json"
        patient_config = SEPatientConfiguration()
        patient_config.set_data_root_dir(str(BIN))
        patient_config.set_patient_file(str(patient))
        if not engine.initialize_engine(patient_config, requests):
            raise RuntimeError(f"direct patient initialization failed: {patient}")
    else:
        if not engine.serialize_from_file(str(STATE), requests):
            raise RuntimeError("could not load StandardMale modifier source checkpoint")
        target_cfg = load_config()["targets"][target]
        action = SECardiovascularMechanicsModification()
        action.get_modifiers().get_systemic_resistance_multiplier().set_value(target_cfg["modifier_R"])
        action.get_modifiers().get_arterial_compliance_multiplier().set_value(target_cfg["modifier_C"])
        engine.process_action(action)
        if not engine.advance_time_s(0.02):
            raise RuntimeError("Pulse stopped after cardiovascular mechanics modification")
    return engine, stage6, columns


def stationarity(rows):
    bins = []
    # These bins cover the final 12 s, with the t=60 sample still pre-infusion:
    # (48,51], (51,54], (54,57], (57,60].
    for low, high in ((48, 51), (51, 54), (54, 57), (57, 60)):
        part = [r for r in rows if low < float(r["elapsed_s"]) <= high]
        if len(part) != 3:
            raise ValueError(f"stationarity bin ({low},{high}] has {len(part)} samples; expected 3")
        bins.append({m: statistics.median(float(r[m]) for r in part)
                     for m in ("systolic_mmHg", "diastolic_mmHg")})
    ranges = {m: max(b[m] for b in bins) - min(b[m] for b in bins)
              for m in ("systolic_mmHg", "diastolic_mmHg")}
    return ranges, all(v <= 0.25 for v in ranges.values())


def summarize_baseline(rows):
    baseline = common.baseline_window_rows(rows)
    if len(baseline) != 30:
        raise ValueError(f"baseline window has {len(baseline)} samples; expected 30")
    metrics = [
        "systolic_mmHg", "diastolic_mmHg", "map_mmHg", "heart_rate_per_min",
        "cardiac_output_L_min", "svr_mmHg_s_mL", "LeftKidneyVasculature_inflow_mL_min",
        "RightKidneyVasculature_inflow_mL_min", "BrainVasculature_inflow_mL_min",
        "baroreceptor_heart_rate_scale", "baroreceptor_heart_elastance_scale",
        "baroreceptor_resistance_scale", "baroreceptor_compliance_scale",
        "aortic_sodium_mEq_L", "aortic_sodium_mg_mL", "blood_volume_mL",
        "renal_plasma_flow_mL_min", "urine_production_mL_min", "urine_osmolality_mOsm_kg",
        "left_ureter_flow_mL_min", "right_ureter_flow_mL_min",
        "left_ureter_sodium_mg_mL", "right_ureter_sodium_mg_mL",
    ]
    out = {m: statistics.median(float(r[m]) for r in baseline) for m in metrics}
    out["urinary_sodium_output_mg_min"] = statistics.median(
        float(r["left_ureter_flow_mL_min"]) * float(r["left_ureter_sodium_mg_mL"])
        + float(r["right_ureter_flow_mL_min"]) * float(r["right_ureter_sodium_mg_mL"])
        for r in baseline)
    if not all(pd.notna(v) for v in out.values()):
        raise ValueError("a required baseline request returned a non-finite value")
    ranges, passes = stationarity(rows)
    out["stationarity_ranges_mmHg"] = ranges
    out["stationarity_pass"] = passes
    return out


def case_path(target, route, replicate, phase):
    return common.case_directory(OUT, target, route, replicate, phase)


def event_snapshot(active, elapsed, previous, first, transitions):
    current = {str(name): bool(value) for name, value in (active or {}).items()}
    for name in set(previous) | set(current):
        now = current.get(name, False)
        was = previous.get(name, False)
        if now and not was:
            first.setdefault(name, elapsed)
            transitions.append({"event": name, "state": "on", "elapsed_s": elapsed})
        elif was and not now:
            transitions.append({"event": name, "state": "off", "elapsed_s": elapsed})
    previous.clear()
    previous.update(current)
    return current


def run_process(target, route, replicate, phase, wait_for_pair=False):
    case = case_path(target, route, replicate, phase)
    case.mkdir(parents=True, exist_ok=False)
    engine, stage6, columns = initialize(target, route, case)
    rows, previous_events, first_events, transitions = [], {}, {}, []

    def sample(elapsed, label):
        if not engine.advance_time_s(1.0):
            raise RuntimeError(f"Pulse stopped at {label} second {elapsed}")
        active = engine.pull_active_events() or {}
        current = event_snapshot(active, elapsed, previous_events, first_events, transitions)
        values = engine.pull_data().copy()
        if len(values) != len(columns):
            raise RuntimeError(f"Pulse returned {len(values)} values for {len(columns)} requests")
        row = dict(zip(columns, values))
        row.update(elapsed_s=elapsed, phase=label)
        rows.append(row)
        if not all(pd.notna(row.get(c)) for c in columns):
            raise RuntimeError(f"a required request returned a non-finite value at {elapsed}s")
        return current

    result = {"target": target, "route": route, "replicate": replicate, "phase": phase,
              "case_path": str(case.relative_to(ROOT))}
    try:
        for elapsed in range(1, 61):
            sample(elapsed, "predrug")
        baseline = summarize_baseline(rows)
        result.update({"baseline": baseline, "active_events_predrug": sorted(k for k, v in previous_events.items() if v),
                       "event_first_observed_elapsed_s": dict(first_events),
                       "event_transitions": list(transitions)})
        result["status"] = "baseline_complete"
        pd.DataFrame(rows).to_csv(case / ("baseline_trace.csv.gz" if phase == "baseline" else "challenge_trace.csv.gz"),
                                  index=False, compression="gzip")

        if phase == "baseline":
            (case / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
            print("RESULT:" + json.dumps(result), flush=True)
            return result

        ready = {"target": target, "route": route, "replicate": replicate,
                 "baseline": baseline, "active_events_predrug": result["active_events_predrug"]}
        if wait_for_pair:
            print("READY:" + json.dumps(ready), flush=True)
            decision = sys.stdin.readline().strip()
        else:
            decision = "GO"
        if decision != "GO":
            result["status"] = "not_administered_pair_gate_failed"
            result["reason"] = "at least one challenged route baseline failed the predeclared pair gate"
            (case / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
            print("RESULT:" + json.dumps(result), flush=True)
            return result

        cfg = load_config()["challenge"]
        from pulse.cdm.patient_actions import SESubstanceInfusion
        from pulse.cdm.scalars import MassPerVolumeUnit, VolumePerTimeUnit, VolumeUnit
        infusion = SESubstanceInfusion()
        infusion.set_comment("Locked pressure-matched norepinephrine confirmation")
        infusion.set_substance(cfg["substance"])
        infusion.get_concentration().set_value(cfg["concentration_ug_mL"], MassPerVolumeUnit.ug_Per_mL)
        infusion.get_rate().set_value(cfg["pulse_rate_mL_s"], VolumePerTimeUnit.mL_Per_s)
        infusion.get_volume().set_value(cfg["reservoir_volume_mL"], VolumeUnit.mL)
        action_result = engine.process_action(infusion)
        if action_result is False:
            raise RuntimeError("Pulse rejected the norepinephrine infusion action")
        irreversible_seen = False
        for elapsed in range(61, 661):
            sample(elapsed, "infusion" if elapsed <= 360 else "post")
            irreversible_seen |= bool(previous_events.get("IrreversibleState", False))
        result.update({"status": "challenge_complete", "infusion_action_accepted": True,
                       "infusion_completed": True, "post_observation_completed": True,
                       "irreversible_state_observed": irreversible_seen,
                       "dose_ug_kg_min": cfg["dose_ug_kg_min"],
                       "concentration_ug_mL": cfg["concentration_ug_mL"],
                       "rate_mL_s": cfg["pulse_rate_mL_s"],
                       "nominal_volume_equivalent_mL": cfg["pulse_rate_mL_s"] * cfg["infusion_duration_s"],
                       "reservoir_volume_mL": cfg["reservoir_volume_mL"],
                       "administered_mass_ug": cfg["administered_mass_ug"],
                       "event_first_observed_elapsed_s": dict(first_events),
                       "event_transitions": list(transitions),
                       "active_events_at_end": sorted(k for k, v in previous_events.items() if v)})
        frame = pd.DataFrame(rows)
        frame["urinary_sodium_output_mg_min"] = (
            frame["left_ureter_flow_mL_min"] * frame["left_ureter_sodium_mg_mL"]
            + frame["right_ureter_flow_mL_min"] * frame["right_ureter_sodium_mg_mL"]
        )
        baseline_start = baseline
        for metric in list(columns) + ["urinary_sodium_output_mg_min"]:
            rolling = frame[metric].rolling(10, min_periods=10).median()
            delta = rolling - float(baseline_start[metric]) if metric in baseline_start else None
            if delta is not None:
                max_index, min_index = int(delta.idxmax()), int(delta.idxmin())
                abs_index = int(delta.abs().idxmax())
                result.setdefault("response", {})[metric] = {
                    "max_delta": float(delta.iloc[max_index]),
                    "max_delta_elapsed_s": int(frame.iloc[max_index]["elapsed_s"]),
                    "min_delta": float(delta.iloc[min_index]),
                    "min_delta_elapsed_s": int(frame.iloc[min_index]["elapsed_s"]),
                    "max_abs_delta": float(delta.iloc[abs_index]),
                    "max_abs_delta_elapsed_s": int(frame.iloc[abs_index]["elapsed_s"]),
                }
        map_delta = frame["map_mmHg"].rolling(10, min_periods=10).median() - baseline["map_mmHg"]
        map_peak_index = int(map_delta.idxmax())
        result["flow_at_peak_map_response"] = {
            "elapsed_s": int(frame.iloc[map_peak_index]["elapsed_s"]),
            "map_change_mmHg": float(map_delta.iloc[map_peak_index]),
            "left_renal_flow_mL_min": float(frame.iloc[map_peak_index]["LeftKidneyVasculature_inflow_mL_min"]),
            "right_renal_flow_mL_min": float(frame.iloc[map_peak_index]["RightKidneyVasculature_inflow_mL_min"]),
            "cerebral_flow_mL_min": float(frame.iloc[map_peak_index]["BrainVasculature_inflow_mL_min"]),
        }
        result["minimum_regional_flows_mL_min"] = {
            "left_renal": float(frame["LeftKidneyVasculature_inflow_mL_min"].min()),
            "right_renal": float(frame["RightKidneyVasculature_inflow_mL_min"].min()),
            "cerebral": float(frame["BrainVasculature_inflow_mL_min"].min()),
        }
        sodium = frame["aortic_sodium_mEq_L"]
        result["sodium_outcome"] = {
            "threshold_mEq_L": 145.0,
            "baseline_mEq_L": baseline["aortic_sodium_mEq_L"],
            "peak_mEq_L": float(sodium.max()),
            "change_from_baseline_mEq_L": float(sodium.max() - baseline["aortic_sodium_mEq_L"]),
            "hypernatremia_first_observed_elapsed_s": first_events.get("Hypernatremia"),
            "sodium_at_event_mEq_L": next((float(r["aortic_sodium_mEq_L"]) for r in rows
                                            if r["elapsed_s"] == first_events.get("Hypernatremia")), None),
            "onset_phase": next((r["phase"] for r in rows if r["elapsed_s"] == first_events.get("Hypernatremia")), None),
            "preexisting_before_infusion": ("Hypernatremia" in result["active_events_predrug"]
                                             or baseline["aortic_sodium_mEq_L"] >= 145.0),
        }
        result["renal_outcome"] = {
            "baseline_renal_plasma_flow_mL_min": baseline["renal_plasma_flow_mL_min"],
            "minimum_renal_plasma_flow_mL_min": float(frame["renal_plasma_flow_mL_min"].min()),
            "baseline_urine_production_mL_min": baseline["urine_production_mL_min"],
            "minimum_urine_production_mL_min": float(frame["urine_production_mL_min"].min()),
        }
        frame.to_csv(case / "challenge_trace.csv.gz", index=False, compression="gzip")
        (case / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
        print("RESULT:" + json.dumps(result), flush=True)
        return result
    except Exception as exc:
        if rows:
            pd.DataFrame(rows).to_csv(case / ("baseline_trace.csv.gz" if phase == "baseline" else "challenge_trace.csv.gz"),
                                      index=False, compression="gzip")
        result.update({"status": "runtime_failure", "error": f"{type(exc).__name__}: {exc}",
                       "event_first_observed_elapsed_s": first_events,
                       "event_transitions": transitions})
        (case / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
        print("RESULT:" + json.dumps(result), flush=True)
        return result


def child_command(target, route, replicate, phase, wait=False):
    return [sys.executable, str(Path(__file__).resolve()), "--child", "--target", target,
            "--route", route, "--replicate", str(replicate), "--phase", phase,
            "--attempt-label", ATTEMPT_LABEL,
            *( ["--wait-for-pair"] if wait else [] )]


def send_pair_decision(proc, decision):
    """Send one gate decision; leave closing the pipe to communicate()."""
    proc.stdin.write(decision + "\n")
    proc.stdin.flush()


def child_env():
    env = os.environ.copy()
    env["PULSE_ROOT"] = str(PULSE)
    env["PULSE_BIN"] = str(BIN)
    pyroots = [str(BIN.parent / "python"), str(BIN)]
    env["PYTHONPATH"] = os.pathsep.join(pyroots + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    env["LD_LIBRARY_PATH"] = str(BIN) + (os.pathsep + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
    return env


def launch_baseline(target, route, replicate):
    proc = subprocess.run(child_command(target, route, replicate, "baseline"), text=True,
                          capture_output=True, env=child_env())
    if proc.returncode:
        raise RuntimeError(f"baseline child failed {target}/{route}/r{replicate}:\n{proc.stdout}\n{proc.stderr}")
    line = next((line for line in reversed(proc.stdout.splitlines()) if line.startswith("RESULT:")), None)
    if line is None:
        raise RuntimeError(f"baseline child returned no result: {proc.stdout}\n{proc.stderr}")
    return json.loads(line[len("RESULT:"):])


def read_ready(proc, label):
    while True:
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError(f"{label} exited before challenged baseline gate: {proc.stderr.read()}")
        if line.startswith("READY:"):
            return json.loads(line[len("READY:"):])


def read_result(proc, label):
    stdout, stderr = proc.communicate()
    if proc.returncode:
        raise RuntimeError(f"challenge child failed {label}:\n{stdout}\n{stderr}")
    line = next((line for line in reversed(stdout.splitlines()) if line.startswith("RESULT:")), None)
    if line is None:
        raise RuntimeError(f"challenge child returned no result {label}:\n{stdout}\n{stderr}")
    return json.loads(line[len("RESULT:"):])


def challenge_pair(target, replicate, screened):
    procs = {}
    ready = {}
    try:
        for route in common.ROUTES:
            procs[route] = subprocess.Popen(child_command(target, route, replicate, "challenge", wait=True),
                                             text=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                             stderr=subprocess.PIPE, env=child_env(), bufsize=1)
        for route in common.ROUTES:
            ready[route] = read_ready(procs[route], f"{target}/{route}/r{replicate}")
        direct, modifier = ready["direct"]["baseline"], ready["modifier"]["baseline"]
        gate = {
            "screen_pair_pass": common.pair_gate_passes(screened["direct"]["baseline"], screened["modifier"]["baseline"]),
            "challenged_pair_pass": common.pair_gate_passes(direct, modifier),
            "direct_against_screened_modifier_pass": common.challenge_gate_passes(direct, screened["modifier"]["baseline"]),
            "modifier_against_screened_direct_pass": common.challenge_gate_passes(modifier, screened["direct"]["baseline"]),
        }
        gate["pass"] = all(gate.values())
        (OUT / target / f"replicate_{replicate:02d}" / "challenge_pair_gate.json").write_text(json.dumps(gate, indent=2) + "\n")
        decision = "GO" if gate["pass"] else "NO"
        for proc in procs.values():
            send_pair_decision(proc, decision)
        results = {route: read_result(procs[route], f"{target}/{route}/r{replicate}") for route in common.ROUTES}
        all_runs_complete = all(run.get("status") == "challenge_complete" for run in results.values())
        pair_result = {"gate": gate, "runs": results,
                       "status": ("complete" if gate["pass"] and all_runs_complete
                                  else "challenge_baseline_gate_failed" if not gate["pass"]
                                  else "challenge_run_invalid")}
        if gate["pass"] and all(run.get("status") == "challenge_complete" for run in results.values()):
            endpoints = ("map_mmHg", "systolic_mmHg", "diastolic_mmHg",
                         "svr_mmHg_s_mL", "cardiac_output_L_min", "heart_rate_per_min",
                         "aortic_sodium_mEq_L", "renal_plasma_flow_mL_min",
                         "urine_production_mL_min", "urinary_sodium_output_mg_min")
            contrasts = {}
            for endpoint in endpoints:
                d = results["direct"]["response"][endpoint]
                m = results["modifier"]["response"][endpoint]
                contrasts[endpoint] = {}
                for summary in ("max_delta", "min_delta", "max_abs_delta"):
                    dv, mv = d[summary], m[summary]
                    contrasts[endpoint][summary] = {
                        "direct": dv, "modifier": mv,
                        "direct_minus_modifier": dv - mv,
                        "relative_to_abs_modifier": (dv - mv) / abs(mv) if mv != 0 else None,
                    }
            pair_result["direct_minus_modifier_contrasts"] = contrasts
        return pair_result
    except Exception:
        for proc in procs.values():
            if proc.poll() is None:
                try:
                    send_pair_decision(proc, "NO")
                except Exception:
                    proc.kill()
        for proc in procs.values():
            try:
                proc.communicate(timeout=5)
            except Exception:
                proc.kill()
        raise


def summarize_repeatability(manifest):
    report = {}
    for target in common.TARGETS:
        for route in common.ROUTES:
            key = f"{target}/{route}"
            first = case_path(target, route, 1, "challenge")
            second = case_path(target, route, 2, "challenge")
            summary_paths = [first / "summary.json", second / "summary.json"]
            trace_paths = [first / "challenge_trace.csv.gz", second / "challenge_trace.csv.gz"]
            if not all(p.exists() for p in summary_paths + trace_paths):
                report[key] = {"status": "one_or_both_repeats_not_completed"}
                continue
            summaries = [json.loads(p.read_text()) for p in summary_paths]
            if not all(s.get("status") == "challenge_complete" for s in summaries):
                report[key] = {"status": "one_or_both_repeats_invalid",
                               "repeat_statuses": [s.get("status") for s in summaries]}
                continue
            a, b = (pd.read_csv(p) for p in trace_paths)
            if a.shape != b.shape:
                report[key] = {"status": "trace_shape_mismatch", "shape_repeat_1": list(a.shape), "shape_repeat_2": list(b.shape)}
                continue
            numeric = [c for c in a.select_dtypes(include="number").columns if c != "elapsed_s"]
            maximum = {c: float((a[c] - b[c]).abs().max()) for c in numeric}
            events_equal = summaries[0].get("event_first_observed_elapsed_s") == summaries[1].get("event_first_observed_elapsed_s")
            report[key] = {"status": "compared", "max_abs_numeric_difference": maximum,
                           "event_onsets_identical": events_equal,
                           "event_onsets_repeat_1": summaries[0].get("event_first_observed_elapsed_s"),
                           "event_onsets_repeat_2": summaries[1].get("event_first_observed_elapsed_s"),
                           "exact_numeric_trace_match": all(v == 0 for v in maximum.values()),
                           "exact_repeat_match": all(v == 0 for v in maximum.values()) and events_equal}
    return report


def plan():
    return {
        "screening_baseline_processes": len(common.TARGETS) * len(common.ROUTES) * len(common.REPLICATES),
        "challenge_runs": len(common.execution_matrix()),
        "challenge_pairs": len(common.TARGETS) * len(common.REPLICATES),
        "challenge_paths": [str(case_path(t, r, rep, "challenge").relative_to(ROOT))
                            for t, r, rep in common.execution_matrix()],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--target", choices=common.TARGETS)
    parser.add_argument("--route", choices=common.ROUTES)
    parser.add_argument("--replicate", type=int, choices=common.REPLICATES)
    parser.add_argument("--phase", choices=("baseline", "challenge"))
    parser.add_argument("--wait-for-pair", action="store_true")
    parser.add_argument("--attempt-label", help="unique child directory name; required for a real run")
    parser.add_argument("--plan-only", action="store_true", help="validate locks and print the run matrix without creating outputs")
    args = parser.parse_args()
    global OUT, ATTEMPT_LABEL
    if args.child:
        if not all((args.target, args.route, args.replicate, args.phase, args.attempt_label)):
            parser.error("--child requires target, route, replicate, phase, and attempt label")
        ATTEMPT_LABEL = args.attempt_label
        OUT = common.attempt_output_directory(OUT_BASE, ATTEMPT_LABEL)
        run_process(args.target, args.route, args.replicate, args.phase, args.wait_for_pair)
        return

    hashes = verify_locked_inputs(require_committed=not args.plan_only)
    if args.plan_only:
        if args.attempt_label:
            ATTEMPT_LABEL = args.attempt_label
            OUT = common.attempt_output_directory(OUT_BASE, ATTEMPT_LABEL)
        print(json.dumps({"locks": hashes, "plan": plan()}, indent=2))
        return
    if not args.attempt_label:
        parser.error("--attempt-label is required for a real run to keep attempts separate")
    ATTEMPT_LABEL = args.attempt_label
    OUT = common.attempt_output_directory(OUT_BASE, ATTEMPT_LABEL)
    if OUT.exists():
        raise FileExistsError(f"output namespace already exists; refusing to mix/overwrite runs: {OUT}")
    OUT.mkdir(parents=True)
    manifest = {"status": "running", "attempt_label": ATTEMPT_LABEL, "locks": hashes,
                "plan": plan(), "baseline_screens": {}, "challenge_pairs": {}}
    (OUT / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    for target in common.TARGETS:
        for replicate in common.REPLICATES:
            runs = {}
            for route in common.ROUTES:
                try:
                    runs[route] = launch_baseline(target, route, replicate)
                except Exception as exc:
                    runs[route] = {"status": "runner_failure",
                                   "error": f"{type(exc).__name__}: {exc}"}
            baseline_runs_valid = all(run.get("status") == "baseline_complete" and "baseline" in run
                                      for run in runs.values())
            gate = baseline_runs_valid and common.pair_gate_passes(
                runs["direct"]["baseline"], runs["modifier"]["baseline"])
            manifest["baseline_screens"][f"{target}/replicate_{replicate:02d}"] = {
                "pass": gate, "runs": runs,
            }
            pair_dir = OUT / target / f"replicate_{replicate:02d}"
            pair_dir.mkdir(parents=True, exist_ok=True)
            (pair_dir / "baseline_pair_gate.json").write_text(json.dumps({"pass": gate}, indent=2) + "\n")
            (OUT / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    for target in common.TARGETS:
        for replicate in common.REPLICATES:
            key = f"{target}/replicate_{replicate:02d}"
            screens = manifest["baseline_screens"][key]
            if not screens["pass"]:
                manifest["challenge_pairs"][key] = {"status": "not_started_screen_pair_gate_failed"}
                continue
            try:
                result = challenge_pair(target, replicate, screens["runs"])
                manifest["challenge_pairs"][key] = result
            except Exception as exc:
                manifest["challenge_pairs"][key] = {
                    "status": "challenge_pair_runtime_failure",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            (OUT / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    had_failures = any(not v.get("pass", False) for v in manifest["baseline_screens"].values()) or any(
        v.get("status") not in (None, "complete") and not v.get("gate", {}).get("pass", False)
        for v in manifest["challenge_pairs"].values())
    manifest["repeatability"] = summarize_repeatability(manifest)
    had_failures = had_failures or any(v.get("status") != "compared" or not v.get("exact_repeat_match")
                                        for v in manifest["repeatability"].values())
    manifest["status"] = "complete_with_failures" if had_failures else "complete"
    (OUT / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"status": manifest["status"], "manifest": str((OUT / 'run_manifest.json').relative_to(ROOT))}, indent=2))


if __name__ == "__main__":
    main()
