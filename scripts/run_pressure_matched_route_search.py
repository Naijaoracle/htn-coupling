#!/usr/bin/env python3
"""Predeclared exact-SBP/DBP route-matching search.

Final evaluations are deliberately refused unless ``--final-search`` is given.
This prevents an accidental final run before the committed predeclaration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PULSE = Path(os.environ.get("PULSE_ROOT", ROOT / "../pulse-physiology-engine")).resolve()
OUT = ROOT / "results/pressure_matched_routes"
PRIVATE = OUT / "private"
PROTOCOL = ROOT / "config/pressure_matched_route_v1.json"

# Stage 6 supplies the established patient envelope, data requests, and
# stable-window implementation. It is imported without running its CLI.
sys.path.insert(0, str(ROOT / "scripts"))
import run_stage6_bounds as stage6  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_protocol() -> dict:
    return json.loads(PROTOCOL.read_text())


def directories() -> None:
    (PRIVATE / "cases").mkdir(parents=True, exist_ok=True)


def require_stage0() -> dict:
    gate_path = ROOT / "results/stage2/stage0_regression_gate.json"
    gate = json.loads(gate_path.read_text())
    if not gate.get("passed"):
        raise RuntimeError("Stage 0 regression gate is not passing")
    current = []
    for item in gate["files"]:
        recorded = item["path"]
        if recorded.startswith("{PULSE_ROOT}/"):
            path = PULSE / recorded.removeprefix("{PULSE_ROOT}/")
        elif recorded.startswith("{HTN_COUPLING_ROOT}/"):
            path = ROOT / recorded.removeprefix("{HTN_COUPLING_ROOT}/")
        else:
            path = Path(recorded)
            if not path.is_absolute():
                path = ROOT / path
        current.append(sha256(path))
    if len(set(current + [gate["expected_sha256"]])) != 1:
        raise RuntimeError("Stage 0 files no longer match their recorded gate")
    return gate


def case_dir(case_id: str) -> Path:
    path = PRIVATE / "cases" / case_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def objective(result: dict, target: dict, protocol: dict) -> float:
    scale = protocol["pressure_match"]["objective_pressure_scale_mmHg"]
    return ((result["systolic_mmHg"] - target["achieved_systolic_mmHg"]) / scale) ** 2 + (
        (result["diastolic_mmHg"] - target["achieved_diastolic_mmHg"]) / scale) ** 2


def evaluate(job: dict) -> dict:
    """Run one direct or modifier state and retain its trace only privately."""
    protocol = load_protocol()
    folder = case_dir(job["case_id"])
    log = folder / "pulse.log"
    try:
        symbols = stage6.pulse_symbols()
        engine = symbols["PulseEngine"](data_root_dir=str(stage6.BIN))
        engine.log_to_console(False)
        engine.set_log_filename(str(log))
        if job["route"] == "direct":
            patient = folder / "patient.json"
            patient.write_text(json.dumps(stage6.patient_payload(
                job["case_id"], job["requested_systolic_mmHg"],
                job["requested_diastolic_mmHg"]), indent=2) + "\n")
            configuration = symbols["SEPatientConfiguration"]()
            configuration.set_data_root_dir(str(stage6.BIN))
            configuration.set_patient_file(str(patient))
            started = time.monotonic()
            if not engine.initialize_engine(configuration, stage6.requests(symbols)):
                raise RuntimeError("direct patient initialization returned false")
        else:
            state = ROOT / "results/stage2/private/cache/StandardMale_stage2_baseline.json"
            if not engine.serialize_from_file(str(state), stage6.requests(symbols)):
                raise RuntimeError("could not load stock StandardMale state")
            action = symbols["SECardiovascularMechanicsModification"]()
            action.get_modifiers().get_systemic_resistance_multiplier().set_value(job["R"])
            action.get_modifiers().get_arterial_compliance_multiplier().set_value(job["C"])
            started = time.monotonic()
            engine.process_action(action)
            if not engine.advance_time_s(protocol["pressure_match"]["sample_interval_s"]):
                raise RuntimeError("Pulse stopped after modifier application")
        trace = stage6.stable_trace(engine, int(protocol["pressure_match"]["measurement_window_s"]))
        trace.to_csv(folder / "stable_trace.csv.gz", index=False, compression="gzip")
        values = stage6.endpoint(trace)
        values["stroke_volume_mL"] = (values["cardiac_output_L_min"] * 1000 /
                                      values["heart_rate_per_min"])
        return {**job, "status": "ok", "wall_s": time.monotonic() - started,
                **values, **stage6.log_metrics(log)}
    except Exception as exc:
        metrics = stage6.log_metrics(log)
        text = log.read_text(errors="replace") if log.exists() else ""
        message = (str(exc) + " " + text).lower()
        category = "evaluation_failure"
        if any(x in message for x in ("initialize", "patient", "stock standardmale")):
            category = "initialization_failure"
        elif any(x in message for x in ("non-finite", "stopped", "negative")):
            category = "numerical_or_physiological_failure"
        elif any(x in message for x in ("timeout", "converg")):
            category = "stabilization_failure"
        return {**job, "status": "failed", "failure_category": category,
                "error": str(exc), "traceback": traceback.format_exc(), **metrics}


def run_jobs(jobs: list[dict], workers: int) -> list[dict]:
    rows = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(evaluate, job) for job in jobs]
        for future in as_completed(futures):
            rows.append(future.result())
    return rows


def direct_states(workers: int) -> pd.DataFrame:
    protocol = load_protocol()
    jobs = [{"case_id": f"direct_{item['label']}", "route": "direct",
             "target": item["label"], "requested_systolic_mmHg": item["systolic"],
             "requested_diastolic_mmHg": item["diastolic"]}
            for item in protocol["targets_mmHg"]]
    frame = pd.DataFrame(run_jobs(jobs, workers)).sort_values("target")
    frame.to_csv(OUT / "direct_states.csv", index=False)
    return frame


def coarse_jobs(direct: pd.DataFrame) -> list[dict]:
    protocol = load_protocol()
    step = protocol["coarse_grid_steps"]
    domain = protocol["modifier_domain"]
    r_values = np.arange(domain["resistance_multiplier"][0],
                         domain["resistance_multiplier"][1] + step["resistance"] / 2,
                         step["resistance"])
    c_values = np.arange(domain["arterial_compliance_multiplier"][0],
                         domain["arterial_compliance_multiplier"][1] + step["compliance"] / 2,
                         step["compliance"])
    jobs = []
    for target in direct.itertuples(index=False):
        if target.status != "ok":
            continue
        for r_value in r_values:
            for c_value in c_values:
                jobs.append({"case_id": f"coarse_{target.target}_R{r_value:.3f}_C{c_value:.3f}",
                             "route": "modifier", "target": target.target,
                             "R": round(float(r_value), 6), "C": round(float(c_value), 6),
                             "requested_systolic_mmHg": target.requested_systolic_mmHg,
                             "requested_diastolic_mmHg": target.requested_diastolic_mmHg,
                             "achieved_systolic_mmHg": target.systolic_mmHg,
                             "achieved_diastolic_mmHg": target.diastolic_mmHg})
    return jobs


def coarse_search(workers: int) -> pd.DataFrame:
    direct = pd.read_csv(OUT / "direct_states.csv")
    rows = run_jobs(coarse_jobs(direct), workers)
    for row in rows:
        if row["status"] == "ok":
            row["J"] = objective(row, row, load_protocol())
    frame = pd.DataFrame(rows).sort_values(["target", "status", "J"], na_position="last")
    frame.to_csv(OUT / "search_evaluations.csv", index=False)
    return frame


def _residuals(row: dict, reference: dict) -> tuple[float, float]:
    return (row["systolic_mmHg"] - reference["systolic_mmHg"],
            row["diastolic_mmHg"] - reference["diastolic_mmHg"])


def _passes(row: dict, reference: dict, protocol: dict) -> bool:
    if row.get("status") != "ok":
        return False
    ds, dd = _residuals(row, reference)
    limits = protocol["pressure_match"]
    return (abs(ds) <= limits["maximum_absolute_sbp_residual_mmHg"] and
            abs(dd) <= limits["maximum_absolute_dbp_residual_mmHg"])


def _local_minima(frame: pd.DataFrame, target: str, spacing: float) -> list[dict]:
    rows = frame[(frame.target == target) & (frame.status == "ok")]
    values = {(round(float(r.R), 6), round(float(r.C), 6)): float(r.J)
              for r in rows.itertuples(index=False) if pd.notna(r.J)}
    minima = []
    for (r, c), value in values.items():
        adjacent = [values[(round(r + dr*spacing, 6), round(c + dc*spacing, 6))]
                    for dr in (-1, 0, 1) for dc in (-1, 0, 1) if dr or dc
                    if (round(r + dr*spacing, 6), round(c + dc*spacing, 6)) in values]
        tied_to_earlier = any(
            values[(round(r + dr*spacing, 6), round(c + dc*spacing, 6))] == value and
            (round(r + dr*spacing, 6), round(c + dc*spacing, 6)) < (r, c)
            for dr in (-1, 0, 1) for dc in (-1, 0, 1) if dr or dc
            if (round(r + dr*spacing, 6), round(c + dc*spacing, 6)) in values)
        if (not adjacent or value <= min(adjacent)) and not tied_to_earlier:
            minima.append({"R": r, "C": c, "J": value})
    return minima


def refine_search(workers: int) -> pd.DataFrame:
    """Refine successful local minima using the predeclared step sequence."""
    protocol = load_protocol()
    direct = pd.read_csv(OUT / "direct_states.csv").set_index("target")
    result = pd.read_csv(OUT / "search_evaluations.csv")
    bounds_r = protocol["modifier_domain"]["resistance_multiplier"]
    bounds_c = protocol["modifier_domain"]["arterial_compliance_multiplier"]
    previous = float(protocol["coarse_grid_steps"]["resistance"])
    for step in protocol["refinement_steps"]:
        jobs = []
        for target in direct.index:
            reference = direct.loc[target]
            if reference.status != "ok":
                continue
            minima = _local_minima(result, target, previous)
            seen = set()
            for minimum in minima:
                r0, r1 = max(bounds_r[0], minimum["R"]-previous), min(bounds_r[1], minimum["R"]+previous)
                c0, c1 = max(bounds_c[0], minimum["C"]-previous), min(bounds_c[1], minimum["C"]+previous)
                rs = np.arange(r0, r1 + step/2, step)
                cs = np.arange(c0, c1 + step/2, step)
                for rv in rs:
                    for cv in cs:
                        key = (target, round(float(rv), 6), round(float(cv), 6))
                        if key in seen:
                            continue
                        seen.add(key)
                        jobs.append({"case_id": f"refine_{target}_{step:g}_R{key[1]:.3f}_C{key[2]:.3f}",
                                     "route": "modifier", "target": target, "R": key[1], "C": key[2],
                                     "refinement_step": step,
                                     "requested_systolic_mmHg": reference.requested_systolic_mmHg,
                                     "requested_diastolic_mmHg": reference.requested_diastolic_mmHg,
                                     "achieved_systolic_mmHg": reference.systolic_mmHg,
                                     "achieved_diastolic_mmHg": reference.diastolic_mmHg})
        rows = run_jobs(jobs, workers)
        for row in rows:
            row["J"] = objective(row, row, protocol) if row["status"] == "ok" else np.nan
            if row["status"] != "ok" and "failure_category" not in row:
                row["failure_category"] = "evaluation_failure"
        if rows:
            result = pd.concat([result, pd.DataFrame(rows)], ignore_index=True)
            result = result.drop_duplicates(subset=["target", "R", "C"], keep="last")
        previous = float(step)
    result.to_csv(OUT / "search_evaluations.csv", index=False)
    return result


def finalize_search(workers: int) -> pd.DataFrame:
    """Independently rerun all tolerance-passing candidates and select primaries."""
    protocol = load_protocol()
    direct = pd.read_csv(OUT / "direct_states.csv").set_index("target")
    results = pd.read_csv(OUT / "search_evaluations.csv")
    candidates = []
    for row in results.to_dict("records"):
        reference = direct.loc[row["target"]]
        if _passes(row, reference, protocol):
            candidates.append(row)
    jobs = [{**row, "case_id": f"rerun_{row['case_id']}"} for row in candidates]
    repeats = run_jobs(jobs, workers) if jobs else []
    repeats_by_key = {(x.get("target"), float(x.get("R", -1)), float(x.get("C", -1))): x
                      for x in repeats}
    accepted_rows = []
    for row in candidates:
        reference = direct.loc[row["target"]]
        repeat = repeats_by_key.get((row["target"], float(row["R"]), float(row["C"])), {})
        row["rerun_status"] = repeat.get("status", "missing")
        if repeat.get("status") == "ok":
            ds, dd = _residuals(repeat, reference)
            row["rerun_systolic_residual_mmHg"] = ds
            row["rerun_diastolic_residual_mmHg"] = dd
            row["rerun_pass"] = _passes(repeat, reference, protocol)
        else:
            row["rerun_pass"] = False
        if row["rerun_pass"]:
            row["distance_from_stock"] = ((float(row["R"])-1)**2+(float(row["C"])-1)**2)**0.5
            accepted_rows.append(row)
    accepted_frame = pd.DataFrame(accepted_rows)
    accepted_frame.to_csv(OUT / "accepted_solutions.csv", index=False)
    if not accepted_frame.empty:
        primary = accepted_frame.sort_values(
            ["target", "distance_from_stock", "J", "R", "C"],
            ascending=[True, True, True, True, False]).groupby("target", as_index=False).first()
        primary.to_csv(OUT / "primary_solutions.csv", index=False)
    else:
        (OUT / "primary_solutions.csv").unlink(missing_ok=True)
    return accepted_frame


def manifest() -> None:
    gate = require_stage0()
    openbf = ROOT / "../openBF"
    try:
        openbf_revision = subprocess.check_output(
            ["git", "-C", str(openbf), "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        openbf_revision = None
    result = {"created_utc": datetime.now(timezone.utc).isoformat(),
              "protocol_sha256": sha256(PROTOCOL), "stage0_sha256": gate["expected_sha256"],
              "pulse_revision": subprocess.check_output(["git", "-C", str(PULSE), "rev-parse", "HEAD"], text=True).strip(),
              "openbf_revision": openbf_revision,
              "htn_coupling_revision": subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
              "python_version": sys.version, "platform": platform.platform(),
              "pulse_path": str(PULSE.resolve()), "openbf_path": str(openbf.resolve()),
              "htn_coupling_path": str(ROOT),
              "pulse_build_configuration": "not captured by this script"}
    (OUT / "run_manifest.json").write_text(json.dumps(result, indent=2) + "\n")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    parser.add_argument("--steps", nargs="+", choices=("manifest", "direct", "coarse", "refine", "finalize"), default=["manifest"])
    parser.add_argument("--final-search", action="store_true", help="permit direct and coarse model evaluations")
    args = parser.parse_args()
    directories()
    if any(step in {"direct", "coarse", "refine", "finalize"} for step in args.steps) and not args.final_search:
        raise SystemExit("Final evaluations require --final-search after predeclaration review")
    if "manifest" in args.steps:
        manifest()
    if "direct" in args.steps:
        print(direct_states(args.workers).to_string(index=False))
    if "coarse" in args.steps:
        print(coarse_search(args.workers).to_string(index=False))
    if "refine" in args.steps:
        print(refine_search(args.workers).to_string(index=False))
    if "finalize" in args.steps:
        print(finalize_search(args.workers).to_string(index=False))


if __name__ == "__main__":
    main()
