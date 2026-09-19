#!/usr/bin/env python3
"""Run a locked four-body pressure-matched norepinephrine study."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import statistics
import subprocess
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config/pressure_matched_drug_response_multibody_v1.json"
PROTOCOL_PATH = ROOT / "docs/PRESSURE_MATCHED_DRUG_RESPONSE_MULTIBODY_PROTOCOL.md"
PANEL_PATH = ROOT / "config/stage5_acute_panel_v1.json"
PULSE = Path(os.environ.get("PULSE_ROOT", "/tmp/pulse-checkpoint-restart")).resolve()
BIN = Path(os.environ.get("PULSE_BIN", "/tmp/pulse-checkpoint-install/bin")).resolve()
OUT_PUBLIC = ROOT / "results/pressure_matched_drug_response_multibody"
OUT_BASE = OUT_PUBLIC / "private"
SCRIPT_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import pressure_matched_multibody_helpers as helpers  # noqa: E402


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def config() -> dict:
    return json.loads(CONFIG_PATH.read_text())


def panel() -> list[dict]:
    return json.loads(PANEL_PATH.read_text())["bodies"]


def patient_payload(body: dict, systolic: float, diastolic: float, name: str) -> dict:
    pressure = lambda x: {"ScalarPressure": {"Value": float(x), "Unit": "mmHg"}}
    return {
        "Name": name,
        "Sex": body["sex"],
        "Age": {"ScalarTime": {"Value": body["age_years"], "Unit": "yr"}},
        "Weight": {"ScalarMass": {"Value": body["weight_kg"], "Unit": "kg"}},
        "Height": {"ScalarLength": {"Value": body["height_cm"], "Unit": "cm"}},
        "DiastolicArterialPressureBaseline": pressure(diastolic),
        "HeartRateBaseline": {"ScalarFrequency": {"Value": 72.0, "Unit": "1/min"}},
        "RespirationRateBaseline": {"ScalarFrequency": {"Value": 12.0, "Unit": "1/min"}},
        "SystolicArterialPressureBaseline": pressure(systolic),
        "SystolicArterialPressureBaselineMinimum": pressure(60.0),
        "SystolicArterialPressureBaselineMaximum": pressure(200.0),
        "DiastolicArterialPressureBaselineMinimum": pressure(40.0),
        "DiastolicArterialPressureBaselineMaximum": pressure(130.0),
        "DiastolicToSystolicPressureRatioMaximum": {"Scalar0To1": {"Value": 0.95}},
    }


def child_env() -> dict:
    env = os.environ.copy()
    env["PULSE_ROOT"] = str(PULSE)
    env["PULSE_BIN"] = str(BIN)
    roots = [str(BIN.parent / "python"), str(BIN)]
    env["PYTHONPATH"] = os.pathsep.join(roots + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    env["LD_LIBRARY_PATH"] = str(BIN) + (os.pathsep + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
    return env


def verify_inputs(require_committed: bool = True) -> dict:
    cfg = config()
    source_sha = subprocess.check_output(["git", "-C", str(PULSE), "rev-parse", "HEAD"], text=True).strip()
    if source_sha != cfg["pulse_revision"]:
        raise RuntimeError(f"Pulse source revision mismatch: {source_sha}")
    probe = subprocess.run([sys.executable, "-c", "import PyPulse; print(PyPulse.__hash__)"],
                           text=True, capture_output=True, env=child_env())
    binding = probe.stdout.strip().splitlines()[-1] if probe.returncode == 0 and probe.stdout.strip() else ""
    if binding != cfg["pulse_binding_hash"]:
        raise RuntimeError(f"Pulse binding mismatch: expected {cfg['pulse_binding_hash']}, got {binding}; {probe.stderr}")
    py_binding = BIN / "PyPulse.cpython-312-x86_64-linux-gnu.so"
    pulse_c = BIN / "libPulseC.so"
    if digest(py_binding) != cfg["pulse_python_binding_sha256"] or digest(pulse_c) != cfg["pulse_c_library_sha256"]:
        raise RuntimeError("installed Pulse shared-library hashes do not match the precommit")
    if digest(PANEL_PATH) != cfg["body_panel_source_sha256"]:
        raise RuntimeError("the source body panel changed after protocol preparation")
    gate_path = ROOT / "results/pressure_matched_routes_v2/stage0_regression_gate.json"
    if digest(gate_path) != cfg["stage0_gate_sha256"]:
        raise RuntimeError("the recorded Stage 0 gate manifest changed")
    gate = json.loads(gate_path.read_text())
    if not gate.get("passed") or gate.get("expected_sha256") != cfg["stage0_csv_sha256"]:
        raise RuntimeError("the pinned Stage 0 gate is not passing")
    for record in gate["files"]:
        path = Path(record["path"].replace("{HTN_COUPLING_ROOT}", str(ROOT)))
        if digest(path) != cfg["stage0_csv_sha256"]:
            raise RuntimeError(f"Stage 0 repeat does not match: {path}")
    if panel() != cfg["body_panel"]:
        raise RuntimeError("configured body panel differs from its source panel")
    if require_committed:
        for path in (CONFIG_PATH, PROTOCOL_PATH, PANEL_PATH, Path(__file__).resolve(),
                     SCRIPT_DIR / "pressure_matched_multibody_helpers.py",
                     ROOT / "test/test_pressure_matched_multibody.py"):
            rel = path.relative_to(ROOT).as_posix()
            subprocess.check_call(["git", "-C", str(ROOT), "cat-file", "-e", f"HEAD:{rel}"])
    return {"pulse_revision": source_sha, "pulse_binding_hash": binding,
            "stage0_gate_sha256": digest(gate_path),
            "stage0_reference_csv_sha256": cfg["stage0_csv_sha256"],
            "body_panel_sha256": digest(PANEL_PATH),
            "configuration_sha256": digest(CONFIG_PATH),
            "protocol_sha256": digest(PROTOCOL_PATH),
            "runner_sha256": digest(Path(__file__).resolve()),
            "helper_sha256": digest(SCRIPT_DIR / "pressure_matched_multibody_helpers.py"),
            "tests_sha256": digest(ROOT / "test/test_pressure_matched_multibody.py")}


def engine_symbols():
    os.environ["PULSE_ROOT"] = str(PULSE)
    os.environ["PULSE_BIN"] = str(BIN)
    sys.path.insert(0, str(BIN.parent / "python"))
    sys.path.insert(0, str(BIN))
    from pulse.cdm.engine import SEDataRequest, SEDataRequestManager
    from pulse.cdm.patient import SEPatientConfiguration
    from pulse.cdm.patient_actions import SECardiovascularMechanicsModification
    from pulse.cdm.scalars import (FrequencyUnit, PressureTimePerVolumeUnit,
                                   PressureUnit, VolumePerTimeUnit, VolumeUnit)
    from pulse.engine.PulseEngine import PulseEngine
    symbols = locals()
    import run_stage6_bounds as stage6
    return symbols, stage6


def make_body_state(body: dict, state_path: Path, base_payload_path: Path, log_path: Path) -> dict:
    symbols, stage6 = engine_symbols()
    configuration = symbols["SEPatientConfiguration"]()
    configuration.set_data_root_dir(str(BIN))
    configuration.set_patient_file(str(base_payload_path))
    engine = symbols["PulseEngine"](data_root_dir=str(BIN))
    engine.log_to_console(False)
    engine.set_log_filename(str(log_path))
    if not engine.initialize_engine(configuration, stage6.requests(symbols)):
        raise RuntimeError(f"failed initializing body base state: {body['body_id']}")
    if not engine.serialize_to_file(str(state_path)):
        raise RuntimeError(f"failed serializing body base state: {body['body_id']}")
    return {"body_id": body["body_id"], "state_sha256": digest(state_path),
            "state_bytes": state_path.stat().st_size}


def eval_point(job: dict) -> dict:
    """One fresh PulseEngine evaluation for a direct or modifier state."""
    symbols, stage6 = engine_symbols()
    folder = Path(job["folder"])
    folder.mkdir(parents=True, exist_ok=False)
    log = folder / "pulse.log"
    engine = symbols["PulseEngine"](data_root_dir=str(BIN))
    engine.log_to_console(False)
    engine.set_log_filename(str(log))
    if job["route"] == "direct":
        pc = symbols["SEPatientConfiguration"]()
        pc.set_data_root_dir(str(BIN))
        pc.set_patient_file(job["patient_path"])
        if not engine.initialize_engine(pc, stage6.requests(symbols)):
            raise RuntimeError("direct target initialization failed")
    else:
        if not engine.serialize_from_file(job["state_path"], stage6.requests(symbols)):
            raise RuntimeError("could not load body-specific modifier source state")
        action = symbols["SECardiovascularMechanicsModification"]()
        action.get_modifiers().get_systemic_resistance_multiplier().set_value(float(job["R"]))
        action.get_modifiers().get_arterial_compliance_multiplier().set_value(float(job["C"]))
        engine.process_action(action)
        if not engine.advance_time_s(0.02):
            raise RuntimeError("Pulse stopped after modifier action")
    trace = stage6.stable_trace(engine, 12)
    trace.insert(0, "elapsed_s", np.arange(1, len(trace) + 1) * 0.02)
    trace.to_csv(folder / "stable_trace.csv.gz", index=False, compression="gzip")
    values = stage6.endpoint(trace.drop(columns="elapsed_s"))
    chunks = np.array_split(trace, 4)
    sbp_bins = [float(x.systolic_mmHg.median()) for x in chunks]
    dbp_bins = [float(x.diastolic_mmHg.median()) for x in chunks]
    values.update({
        "stationarity_sbp_range_mmHg": max(sbp_bins) - min(sbp_bins),
        "stationarity_dbp_range_mmHg": max(dbp_bins) - min(dbp_bins),
        "stationarity_pass": max(sbp_bins) - min(sbp_bins) <= 0.25 and
                             max(dbp_bins) - min(dbp_bins) <= 0.25,
        "status": "ok", "body_id": job["body_id"], "route": job["route"],
        "case_id": job["case_id"], "R": job.get("R"), "C": job.get("C"),
        "wall_s": float(job.get("wall_s", 0.0)),
    })
    return values


def safe_eval(job: dict) -> dict:
    try:
        return eval_point(job)
    except Exception as exc:
        return {"status": "failed", "body_id": job.get("body_id"),
                "route": job.get("route"), "case_id": job.get("case_id"),
                "R": job.get("R"), "C": job.get("C"),
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc()}


def evaluate_jobs(jobs: list[dict], workers: int) -> list[dict]:
    if not jobs:
        return []
    rows = []
    with ProcessPoolExecutor(max_workers=workers, max_tasks_per_child=1) as pool:
        futures = {pool.submit(safe_eval, job): job for job in jobs}
        for future in as_completed(futures):
            rows.append(future.result())
    return rows


def score(row: dict, reference: dict) -> float:
    return ((float(row["systolic_mmHg"]) - float(reference["systolic_mmHg"])) ** 2 +
            (float(row["diastolic_mmHg"]) - float(reference["diastolic_mmHg"])) ** 2)


def within_match(row: dict, reference: dict) -> bool:
    return row.get("status") == "ok" and row.get("stationarity_pass") and all(
        abs(float(row[m]) - float(reference[m])) <= 0.25
        for m in ("systolic_mmHg", "diastolic_mmHg"))


def search_body(body: dict, reference: dict, state_path: Path,
                output: Path, workers: int) -> tuple[list[dict], dict | None]:
    spec = config()["pressure_match"]["search"]
    domain = config()["pressure_match"]["modifier_domain"]
    bounds = (domain["resistance_multiplier"], domain["arterial_compliance_multiplier"])
    du = spec["initial_central_difference_step"]["resistance_multiplier"]
    dv = spec["initial_central_difference_step"]["arterial_compliance_multiplier"]
    seen: dict[tuple[float, float], dict] = {}
    all_rows: list[dict] = []
    point = (spec["initial_point"]["resistance_multiplier"],
             spec["initial_point"]["arterial_compliance_multiplier"])

    def submit(points: list[tuple[float, float]]) -> list[dict]:
        fresh = []
        pending = set()
        for r, c in points:
            key = (round(float(r), 6), round(float(c), 6))
            if key not in seen and key not in pending and len(seen) + len(fresh) < spec["maximum_unique_evaluations_per_body"]:
                fresh.append(key)
                pending.add(key)
        jobs = []
        for r, c in fresh:
            idx = len(seen) + len(jobs) + 1
            jobs.append({"body_id": body["body_id"], "route": "modifier", "R": r, "C": c,
                         "case_id": f"{body['body_id']}_search_{idx:02d}",
                         "state_path": str(state_path),
                         "folder": str(output / "search" / body["body_id"] / f"eval_{idx:02d}")})
        rows = evaluate_jobs(jobs, workers)
        by_key = {(round(float(r["R"]), 6), round(float(r["C"]), 6)): r for r in rows}
        for key in fresh:
            row = by_key[key]
            row["objective_J"] = score(row, reference) if row["status"] == "ok" else None
            seen[key] = row
            all_rows.append(row)
        return [seen[(round(float(r), 6), round(float(c), 6))] for r, c in points
                if (round(float(r), 6), round(float(c), 6)) in seen]

    r0, c0 = point
    submit([point])
    best = seen[(round(r0, 6), round(c0, 6))]
    for iteration in range(spec["maximum_iterations"]):
        if within_match(best, reference):
            break
        if best.get("status") != "ok" or not best.get("stationarity_pass"):
            break
        r, c = float(best["R"]), float(best["C"])
        stencil = [(r + du, c), (r - du, c), (r, c + dv), (r, c - dv)]
        stencil = [(min(max(x, b[0]), b[1]), min(max(y, d[0]), d[1]))
                   for (x, y), b, d in [(p, bounds[0], bounds[1]) for p in stencil]]
        observed = submit(stencil)
        if len(observed) != 4:
            break
        matching_stencil = [row for row in observed if within_match(row, reference)]
        if matching_stencil:
            accepted = dict(min(matching_stencil, key=lambda row: score(row, reference)))
            accepted["independent_confirmation_passes"] = 0
            return all_rows, accepted
        f0 = np.array([float(best[m]) - float(reference[m])
                       for m in ("systolic_mmHg", "diastolic_mmHg")])
        jac = np.zeros((2, 2), dtype=float)
        valid = True
        for col, (plus_i, minus_i, step) in enumerate(((0, 1, du), (2, 3, dv))):
            plus, minus = observed[plus_i], observed[minus_i]
            plus_valid = plus.get("status") == "ok" and plus.get("stationarity_pass")
            minus_valid = minus.get("status") == "ok" and minus.get("stationarity_pass")
            if plus_valid and minus_valid and float(plus["R"] if col == 0 else plus["C"]) != float(minus["R"] if col == 0 else minus["C"]):
                denom = (float(plus["R"] if col == 0 else plus["C"]) -
                         float(minus["R"] if col == 0 else minus["C"]))
                jac[:, col] = np.array([float(plus[m]) - float(minus[m])
                                        for m in ("systolic_mmHg", "diastolic_mmHg")]) / denom
            elif plus_valid:
                denom = float(plus["R"] if col == 0 else plus["C"]) - (r if col == 0 else c)
                if abs(denom) < 1e-12:
                    valid = False
                else:
                    jac[:, col] = np.array([float(plus[m]) - float(best[m])
                                            for m in ("systolic_mmHg", "diastolic_mmHg")]) / denom
            elif minus_valid:
                denom = (r if col == 0 else c) - float(minus["R"] if col == 0 else minus["C"])
                if abs(denom) < 1e-12:
                    valid = False
                else:
                    jac[:, col] = np.array([float(best[m]) - float(minus[m])
                                            for m in ("systolic_mmHg", "diastolic_mmHg")]) / denom
            else:
                valid = False
        if not valid:
            break
        try:
            proposal = helpers.bounded_newton_proposal((r, c), f0, jac, bounds,
                                                        spec["maximum_coordinate_step"])
        except (ValueError, np.linalg.LinAlgError):
            break
        improved = False
        for backtrack in range(spec["maximum_backtracks_per_iteration"] + 1):
            frac = 0.5 ** backtrack
            candidate = (r + frac * (proposal[0] - r), c + frac * (proposal[1] - c))
            rows = submit([candidate])
            if not rows:
                continue
            candidate_row = rows[0]
            if candidate_row.get("status") == "ok" and candidate_row.get("stationarity_pass") and score(candidate_row, reference) < score(best, reference):
                best = candidate_row
                improved = True
                break
        if not improved:
            break
        if len(seen) >= spec["maximum_unique_evaluations_per_body"]:
            break
    if within_match(best, reference):
        accepted = dict(best)
        accepted["independent_confirmation_passes"] = 0
        return all_rows, accepted
    return all_rows, None


def output_case(attempt: Path, body_id: str, route: str, replicate: int, phase: str) -> Path:
    return attempt / body_id / f"replicate_{replicate:02d}" / route / phase


def launch_child(attempt_label: str, body_id: str, route: str,
                 replicate: int, phase: str, wait: bool = False):
    command = [sys.executable, str(Path(__file__).resolve()), "--child",
               "--attempt-label", attempt_label, "--body-id", body_id,
               "--route", route, "--replicate", str(replicate), "--phase", phase]
    if wait:
        command.append("--wait-for-pair")
    return command


def configure_singlebody_runtime(body_id: str, attempt: Path, output: Path,
                                 state: Path, payload_root: Path, selected: dict) -> None:
    os.environ["PULSE_ROOT"] = str(PULSE)
    os.environ["PULSE_BIN"] = str(BIN)
    sys.path.insert(0, str(BIN.parent / "python"))
    sys.path.insert(0, str(BIN))
    import run_pressure_matched_drug_response_confirmatory as one
    import pressure_matched_drug_response_common as common
    common.TARGETS = (body_id,)
    common.REPLICATES = (1, 2)
    one.PULSE, one.BIN = PULSE, BIN
    one.OUT_BASE, one.OUT = attempt, output
    one.ATTEMPT_LABEL = attempt.name
    one.BASES = payload_root
    one.STATE = state
    target_cfg = {body_id: {"modifier_R": float(selected["R"]), "modifier_C": float(selected["C"])} }
    body = next(b for b in config()["body_panel"] if b["body_id"] == body_id)
    dose = config()["challenge"]
    rate = helpers.norepinephrine_rate_mL_s(dose["dose_ug_kg_min"], body["weight_kg"], dose["concentration_ug_mL"])
    challenge = {"substance": dose["substance"], "dose_ug_kg_min": dose["dose_ug_kg_min"],
                 "concentration_ug_mL": dose["concentration_ug_mL"], "pulse_rate_mL_s": rate,
                 "infusion_duration_s": dose["infusion_duration_s"],
                 "reservoir_volume_mL": rate * dose["infusion_duration_s"] + 0.01,
                 "administered_mass_ug": body["weight_kg"] * dose["dose_ug_kg_min"] * dose["infusion_duration_s"] / 60.0}
    one.load_config = lambda: {"targets": target_cfg, "challenge": challenge}
    return one, common


def child_run(args) -> None:
    attempt = helpers.attempt_output_directory(OUT_BASE, args.attempt_label)
    selected = json.loads((attempt / "matched_states.json").read_text())[args.body_id]
    body = next(x for x in config()["body_panel"] if x["body_id"] == args.body_id)
    state = attempt / "inputs" / args.body_id / "base_state.json"
    payload_root = attempt / "inputs"
    output = attempt
    one, _ = configure_singlebody_runtime(args.body_id, attempt, output, state,
                                           payload_root, selected)
    one.run_process(args.body_id, args.route, args.replicate, args.phase, args.wait_for_pair)


def read_result(proc, label: str, ready: bool = False) -> dict:
    if ready:
        while True:
            line = proc.stdout.readline()
            if not line:
                raise RuntimeError(f"{label} exited before READY: {proc.stderr.read()}")
            if line.startswith("READY:"):
                return json.loads(line[len("READY:"):])
    stdout, stderr = proc.communicate()
    if proc.returncode:
        raise RuntimeError(f"{label} failed:\n{stdout}\n{stderr}")
    line = next((x for x in reversed(stdout.splitlines()) if x.startswith("RESULT:")), None)
    if line is None:
        raise RuntimeError(f"{label} returned no RESULT:\n{stdout}\n{stderr}")
    return json.loads(line[len("RESULT:"):])


def run_challenge_pair(attempt_label: str, body_id: str, replicate: int,
                       screens: dict, selected: dict) -> dict:
    attempt = helpers.attempt_output_directory(OUT_BASE, attempt_label)
    configure_singlebody_runtime(body_id, attempt, attempt, attempt / "inputs" / body_id / "base_state.json",
                                 attempt / "inputs", selected)
    import run_pressure_matched_drug_response_confirmatory as one
    import pressure_matched_drug_response_common as common
    procs = {}
    ready = {}
    try:
        for route in ("direct", "modifier"):
            cmd = launch_child(attempt_label, body_id, route, replicate, "challenge", wait=True)
            procs[route] = subprocess.Popen(cmd, text=True, stdin=subprocess.PIPE,
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            env=child_env(), bufsize=1)
        for route in ("direct", "modifier"):
            ready[route] = read_result(procs[route], f"{body_id}/{route}/r{replicate}", ready=True)
        pair = {route: ready[route]["baseline"] for route in ready}
        gate = {
            "screen_pair_pass": common.pair_gate_passes(screens["direct"]["baseline"], screens["modifier"]["baseline"]),
            "challenged_pair_pass": common.pair_gate_passes(pair["direct"], pair["modifier"]),
            "direct_against_screened_modifier_pass": common.challenge_gate_passes(pair["direct"], screens["modifier"]["baseline"]),
            "modifier_against_screened_direct_pass": common.challenge_gate_passes(pair["modifier"], screens["direct"]["baseline"]),
        }
        gate["pass"] = all(gate.values())
        gate_path = output_case(attempt, body_id, "direct", replicate, "challenge").parent / "challenge_pair_gate.json"
        gate_path.parent.mkdir(parents=True, exist_ok=True)
        gate_path.write_text(json.dumps(gate, indent=2) + "\n")
        for proc in procs.values():
            proc.stdin.write(("GO" if gate["pass"] else "NO") + "\n")
            proc.stdin.flush()
        runs = {route: read_result(proc, f"{body_id}/{route}/r{replicate}")
                for route, proc in procs.items()}
        status = "complete" if gate["pass"] and all(r.get("status") == "challenge_complete" for r in runs.values()) else "challenge_gate_failed" if not gate["pass"] else "challenge_invalid"
        result = {"status": status, "gate": gate, "runs": runs}
        if status == "complete":
            endpoints = ("map_mmHg", "systolic_mmHg", "diastolic_mmHg", "svr_mmHg_s_mL",
                         "cardiac_output_L_min", "heart_rate_per_min", "aortic_sodium_mEq_L",
                         "renal_plasma_flow_mL_min", "urine_production_mL_min")
            result["contrasts"] = {}
            for endpoint in endpoints:
                result["contrasts"][endpoint] = {}
                for metric in ("max_delta", "min_delta", "max_abs_delta"):
                    d = float(runs["direct"]["response"][endpoint][metric])
                    m = float(runs["modifier"]["response"][endpoint][metric])
                    result["contrasts"][endpoint][metric] = {
                        "direct": d, "modifier": m,
                        "direct_minus_modifier": d - m,
                    }
        return result
    finally:
        for proc in procs.values():
            if proc.poll() is None:
                try:
                    proc.stdin.write("NO\n"); proc.stdin.flush()
                except Exception:
                    proc.kill()
        for proc in procs.values():
            try:
                proc.communicate(timeout=10)
            except Exception:
                proc.kill()


def run_parent(args) -> None:
    locks = verify_inputs(require_committed=not args.plan_only)
    panel_cfg = config()
    if args.plan_only:
        print(json.dumps({"locks": locks,
                          "body_ids": [b["body_id"] for b in panel_cfg["body_panel"]],
                          "target": panel_cfg["target"],
                          "search_cap": panel_cfg["pressure_match"]["search"]["maximum_unique_evaluations_per_body"],
                          "challenge_runs_max": len(panel_cfg["body_panel"]) * 2 * 2}, indent=2))
        return
    if not args.attempt_label:
        raise ValueError("--attempt-label is required for a run")
    attempt = helpers.attempt_output_directory(OUT_BASE, args.attempt_label)
    if attempt.exists():
        raise FileExistsError(f"refusing to reuse existing attempt namespace: {attempt}")
    attempt.mkdir(parents=True)
    (attempt / "inputs").mkdir()
    manifest = {"status": "running", "attempt_label": args.attempt_label,
                "started_utc": datetime.now(timezone.utc).isoformat(), "locks": locks,
                "body_results": {}, "challenge_runs": {}}
    (attempt / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    all_search = []
    matched = {}
    direct_refs = {}
    for body in panel_cfg["body_panel"]:
        body_root = attempt / "inputs" / body["body_id"]
        body_root.mkdir()
        base_payload = body_root / "base_patient.json"
        direct_payload = attempt / "inputs" / f"direct_{body['body_id']}" / "patient.json"
        base_payload.write_text(json.dumps(patient_payload(body, 114.0, 73.5, f"{body['body_id']}_base"), indent=2) + "\n")
        direct_payload.parent.mkdir(parents=True)
        direct_payload.write_text(json.dumps(patient_payload(body, 140.0, 90.0, f"{body['body_id']}_direct_140_90"), indent=2) + "\n")
        state_path = body_root / "base_state.json"
        try:
            source_record = make_body_state(body, state_path, base_payload, body_root / "base_init.log")
            source_record.update({"base_patient_sha256": digest(base_payload),
                                  "direct_patient_sha256": digest(direct_payload)})
            direct_job = {"body_id": body["body_id"], "route": "direct", "case_id": f"{body['body_id']}_direct_target",
                          "patient_path": str(direct_payload),
                          "folder": str(attempt / "matching" / body["body_id"] / "direct")}
            direct_row = evaluate_jobs([direct_job], 1)[0]
            direct_refs[body["body_id"]] = direct_row
            if direct_row.get("status") != "ok" or not direct_row.get("stationarity_pass"):
                manifest["body_results"][body["body_id"]] = {"status": "direct_target_invalid",
                    "body": body, "source": source_record, "direct": direct_row}
                (attempt / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
                continue
            evaluations, selected = search_body(body, direct_row, state_path, attempt, args.workers)
            all_search.extend(evaluations)
            body_result = {"body": body, "source": source_record, "direct": direct_row,
                           "search_evaluations": len(evaluations), "selected": selected}
            if selected is not None:
                confirm_jobs = []
                confirm_root = attempt / "confirmation" / body["body_id"]
                for rep in (1, 2):
                    confirm_jobs.append({"body_id": body["body_id"], "route": "modifier",
                        "R": selected["R"], "C": selected["C"], "case_id": f"{body['body_id']}_confirmation_{rep}",
                        "state_path": str(state_path), "folder": str(confirm_root / f"repeat_{rep:02d}")})
                confirmations = evaluate_jobs(confirm_jobs, 1)
                pass_flags = [within_match(row, direct_row) for row in confirmations]
                selected["independent_confirmation_passes"] = sum(pass_flags)
                selected["confirmation_runs"] = confirmations
                selected["accepted"] = all(pass_flags)
                body_result["selected"] = selected
                if selected["accepted"]:
                    matched[body["body_id"]] = selected
            body_result["status"] = "accepted_pair" if body["body_id"] in matched else "no_accepted_pair"
            manifest["body_results"][body["body_id"]] = body_result
        except Exception as exc:
            manifest["body_results"][body["body_id"]] = {"status": "setup_or_search_failure",
                "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()}
        pd.DataFrame(all_search).to_csv(attempt / "search_evaluations_private.csv", index=False)
        (attempt / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (attempt / "matched_states.json").write_text(json.dumps(matched, indent=2) + "\n")
    for body_id, selected in matched.items():
        screens = {route: {} for route in ("direct", "modifier")}
        for rep in (1, 2):
            for route in ("direct", "modifier"):
                cmd = launch_child(args.attempt_label, body_id, route, rep, "baseline")
                proc = subprocess.run(cmd, text=True, capture_output=True, env=child_env())
                if proc.returncode:
                    raise RuntimeError(f"baseline screen failed {body_id}/{route}/r{rep}: {proc.stdout}\n{proc.stderr}")
                line = next((x for x in reversed(proc.stdout.splitlines()) if x.startswith("RESULT:")), None)
                if line is None:
                    raise RuntimeError(f"missing baseline result {body_id}/{route}/r{rep}: {proc.stdout}")
                result = json.loads(line[len("RESULT:"):])
                screens[route][rep] = result
            d, m = screens["direct"][rep].get("baseline", {}), screens["modifier"][rep].get("baseline", {})
            from pressure_matched_drug_response_common import pair_gate_passes
            pair_gate = pair_gate_passes(d, m)
            (output_case(attempt, body_id, "direct", rep, "baseline").parent / "baseline_pair_gate.json").write_text(json.dumps({"pass": pair_gate}, indent=2) + "\n")
        manifest["body_results"][body_id]["baseline_screens"] = screens
        manifest["body_results"][body_id]["baseline_pair_pass_by_replicate"] = {
            str(rep): (screens["direct"][rep].get("status") == "baseline_complete" and
                      screens["modifier"][rep].get("status") == "baseline_complete" and
                      pair_gate_passes(screens["direct"][rep]["baseline"], screens["modifier"][rep]["baseline"]))
            for rep in (1, 2)}
        (attempt / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        for rep in (1, 2):
            key = f"{body_id}/replicate_{rep:02d}"
            if not manifest["body_results"][body_id]["baseline_pair_pass_by_replicate"][str(rep)]:
                manifest["challenge_runs"][key] = {"status": "not_started_baseline_gate_failed"}
                continue
            try:
                screens_for_repeat = {route: screens[route][rep] for route in ("direct", "modifier")}
                result = run_challenge_pair(args.attempt_label, body_id, rep, screens_for_repeat, selected)
                manifest["challenge_runs"][key] = result
            except Exception as exc:
                manifest["challenge_runs"][key] = {"status": "pair_runtime_failure",
                    "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()}
            (attempt / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    pd.DataFrame(all_search).to_csv(attempt / "search_evaluations.csv", index=False)
    aggregates, contrasts, repeatability = build_aggregates(manifest, attempt)
    aggregates.to_csv(attempt / "aggregate.csv", index=False)
    contrasts.to_csv(attempt / "paired_contrasts.csv", index=False)
    repeatability.to_csv(attempt / "repeatability.csv", index=False)
    manifest["status"] = "complete" if len(matched) == len(panel_cfg["body_panel"]) and len(aggregates) == 16 and aggregates.status.eq("challenge_complete").all() else "complete_with_failures"
    manifest["completed_utc"] = datetime.now(timezone.utc).isoformat()
    manifest["summary"] = {"bodies_in_panel": len(panel_cfg["body_panel"]), "accepted_pairs": len(matched),
                           "challenge_runs": len(aggregates), "complete_challenge_runs": int(aggregates.status.eq("challenge_complete").sum())}
    (attempt / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    write_public_results(manifest, all_search, aggregates, contrasts, repeatability)
    print(json.dumps({"status": manifest["status"], "manifest": str((OUT_PUBLIC / "manifest.json").relative_to(ROOT)),
                      "matched_body_n": len(matched)}, indent=2))


def write_public_results(manifest: dict, search_rows: list[dict], aggregates: pd.DataFrame,
                         contrasts: pd.DataFrame, repeatability: pd.DataFrame) -> None:
    OUT_PUBLIC.mkdir(parents=True, exist_ok=True)
    search = pd.DataFrame(search_rows)
    if not search.empty:
        allowed = [c for c in ("body_id", "case_id", "route", "R", "C", "status",
                    "systolic_mmHg", "diastolic_mmHg", "map_mmHg", "heart_rate_per_min",
                    "cardiac_output_L_min", "svr_mmHg_s_mL", "stationarity_sbp_range_mmHg",
                    "stationarity_dbp_range_mmHg", "stationarity_pass", "objective_J") if c in search]
        search[allowed].to_csv(OUT_PUBLIC / "search_evaluations.csv", index=False)
    aggregates.to_csv(OUT_PUBLIC / "aggregate.csv", index=False)
    contrasts.to_csv(OUT_PUBLIC / "paired_contrasts.csv", index=False)
    repeatability.to_csv(OUT_PUBLIC / "repeatability.csv", index=False)
    body_rows = []
    for body_id, result in manifest["body_results"].items():
        selected = result.get("selected") or {}
        direct = result.get("direct") or {}
        body = result.get("body") or {}
        body_rows.append({"body_id": body_id, "sex": body.get("sex"), "age_years": body.get("age_years"),
            "height_cm": body.get("height_cm"), "weight_kg": body.get("weight_kg"),
            "bmi_kg_m2": helpers.body_bmi_kg_m2(body) if body else None,
            "status": result.get("status"), "direct_sbp_mmHg": direct.get("systolic_mmHg"),
            "direct_dbp_mmHg": direct.get("diastolic_mmHg"), "modifier_R": selected.get("R"),
            "modifier_C": selected.get("C"), "modifier_sbp_mmHg": selected.get("systolic_mmHg"),
            "modifier_dbp_mmHg": selected.get("diastolic_mmHg"),
            "search_evaluations": result.get("search_evaluations"),
            "independent_confirmation_passes": selected.get("independent_confirmation_passes"),
            "accepted": selected.get("accepted", False)})
    pd.DataFrame(body_rows).to_csv(OUT_PUBLIC / "matched_states.csv", index=False)
    public_body_details = {}
    for body_id, result in manifest["body_results"].items():
        selected = result.get("selected") or {}
        direct = result.get("direct") or {}
        public_body_details[body_id] = {
            "body": result.get("body"), "status": result.get("status"),
            "base_state_sha256": (result.get("source") or {}).get("state_sha256"),
            "base_patient_sha256": (result.get("source") or {}).get("base_patient_sha256"),
            "direct_patient_sha256": (result.get("source") or {}).get("direct_patient_sha256"),
            "direct_target": {k: direct.get(k) for k in ("status", "systolic_mmHg", "diastolic_mmHg", "stationarity_pass")},
            "search_evaluations": result.get("search_evaluations"),
            "selected_modifier": {k: selected.get(k) for k in ("R", "C", "systolic_mmHg", "diastolic_mmHg", "stationarity_pass", "independent_confirmation_passes", "accepted")},
            "baseline_pair_pass_by_replicate": result.get("baseline_pair_pass_by_replicate"),
        }
    public_manifest = {
        "status": manifest["status"], "attempt_label": manifest["attempt_label"],
        "started_utc": manifest.get("started_utc"), "completed_utc": manifest.get("completed_utc"),
        "locks": manifest["locks"], "body_details": public_body_details,
        "challenge_pair_statuses": {key: {"status": value.get("status"), "gate": value.get("gate")}
                                     for key, value in manifest.get("challenge_runs", {}).items()},
        "summary": manifest.get("summary"),
        "raw_traces_location": "private ignored results directory; not tracked",
    }
    (OUT_PUBLIC / "manifest.json").write_text(json.dumps(public_manifest, indent=2) + "\n")


def build_aggregates(manifest: dict, attempt: Path):
    rows, contrast_rows, repeat_rows = [], [], []
    for body_id in manifest["body_results"]:
        for rep in (1, 2):
            pair = manifest.get("challenge_runs", {}).get(f"{body_id}/replicate_{rep:02d}", {})
            for route in ("direct", "modifier"):
                run = pair.get("runs", {}).get(route, {})
                baseline = run.get("baseline", {})
                response = run.get("response", {})
                rows.append({"body_id": body_id, "replicate": rep, "route": route,
                    "status": run.get("status", pair.get("status", "not_run")),
                    "baseline_sbp_mmHg": baseline.get("systolic_mmHg"),
                    "baseline_dbp_mmHg": baseline.get("diastolic_mmHg"),
                    "baseline_map_mmHg": baseline.get("map_mmHg"),
                    "baseline_svr_mmHg_s_mL": baseline.get("svr_mmHg_s_mL"),
                    "baseline_hr_per_min": baseline.get("heart_rate_per_min"),
                    "baseline_renal_plasma_flow_mL_min": baseline.get("renal_plasma_flow_mL_min"),
                    "baseline_urine_production_mL_min": baseline.get("urine_production_mL_min"),
                    "baseline_sodium_mEq_L": baseline.get("aortic_sodium_mEq_L"),
                    "peak_delta_map_mmHg": response.get("map_mmHg", {}).get("max_delta"),
                    "peak_delta_svr_mmHg_s_mL": response.get("svr_mmHg_s_mL", {}).get("max_delta"),
                    "maximum_absolute_delta_hr_per_min": response.get("heart_rate_per_min", {}).get("max_abs_delta"),
                    "minimum_delta_co_L_min": response.get("cardiac_output_L_min", {}).get("min_delta"),
                    "dose_ug_kg_min": run.get("dose_ug_kg_min"),
                    "infusion_rate_mL_s": run.get("rate_mL_s"),
                    "nominal_volume_equivalent_mL": run.get("nominal_volume_equivalent_mL"),
                    "event_first_observed_elapsed_s": json.dumps(run.get("event_first_observed_elapsed_s", {}), sort_keys=True)})
            if pair.get("status") == "complete":
                for endpoint, metrics in pair.get("contrasts", {}).items():
                    for metric, values in metrics.items():
                        contrast_rows.append({"body_id": body_id, "replicate": rep,
                            "endpoint": endpoint, "summary": metric,
                            "direct": values["direct"], "modifier": values["modifier"],
                            "direct_minus_modifier": values["direct_minus_modifier"]})
        for route in ("direct", "modifier"):
            a_path = output_case(attempt, body_id, route, 1, "challenge") / "challenge_trace.csv.gz"
            b_path = output_case(attempt, body_id, route, 2, "challenge") / "challenge_trace.csv.gz"
            record = {"body_id": body_id, "route": route, "status": "missing_trace"}
            if a_path.exists() and b_path.exists():
                a, b = pd.read_csv(a_path), pd.read_csv(b_path)
                if a.shape == b.shape:
                    numeric = [c for c in a.select_dtypes(include="number").columns if c != "elapsed_s"]
                    diffs = {c: float((a[c] - b[c]).abs().max()) for c in numeric}
                    sa_path = output_case(attempt, body_id, route, 1, "challenge") / "summary.json"
                    sb_path = output_case(attempt, body_id, route, 2, "challenge") / "summary.json"
                    sa, sb = json.loads(sa_path.read_text()), json.loads(sb_path.read_text())
                    event_equal = sa.get("event_first_observed_elapsed_s") == sb.get("event_first_observed_elapsed_s")
                    record.update({"status": "compared", "exact_numeric_trace_match": all(v == 0 for v in diffs.values()),
                                   "event_onsets_identical": event_equal,
                                   "max_abs_numeric_difference": max(diffs.values(), default=0.0)})
            repeat_rows.append(record)
    return pd.DataFrame(rows), pd.DataFrame(contrast_rows), pd.DataFrame(repeat_rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--attempt-label")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--body-id")
    parser.add_argument("--route", choices=("direct", "modifier"))
    parser.add_argument("--replicate", type=int, choices=(1, 2))
    parser.add_argument("--phase", choices=("baseline", "challenge"))
    parser.add_argument("--wait-for-pair", action="store_true")
    args = parser.parse_args()
    if args.child:
        if not all((args.attempt_label, args.body_id, args.route, args.replicate, args.phase)):
            parser.error("child mode needs attempt, body, route, replicate, and phase")
        child_run(args)
    else:
        run_parent(args)


if __name__ == "__main__":
    main()
