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
OUT = ROOT / "results/pressure_matched_routes_v2"
PRIVATE = OUT / "private"
PROTOCOL = ROOT / "config/pressure_matched_route_v1.json"
STAGE0_GATE = OUT / "stage0_regression_gate.json"

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
    (PRIVATE / "stage0_repeats").mkdir(parents=True, exist_ok=True)


def _gate_file_path(value: str) -> Path:
    if value.startswith("{HTN_COUPLING_ROOT}/"):
        return ROOT / value.removeprefix("{HTN_COUPLING_ROOT}/")
    if value.startswith("{PULSE_ROOT}/"):
        return PULSE / value.removeprefix("{PULSE_ROOT}/")
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def require_stage0() -> dict:
    gate = json.loads(STAGE0_GATE.read_text())
    protocol = load_protocol()
    expected_revision = protocol["pulse_revision"]
    current_revision = subprocess.check_output(
        ["git", "-C", str(PULSE), "rev-parse", "HEAD"], text=True).strip()
    if current_revision != expected_revision or gate.get("pulse_revision") != expected_revision:
        raise RuntimeError("Pulse source, Stage 0 gate, and amended protocol revisions differ")
    if not gate.get("passed"):
        raise RuntimeError("Amended Stage 0 repeatability gate is not passing")
    current = [sha256(_gate_file_path(item["path"])) for item in gate["files"]]
    if len(set(current + [gate["expected_sha256"]])) != 1:
        raise RuntimeError("Amended Stage 0 files no longer match their recorded gate")
    return gate


def stage0_gate() -> dict:
    """Validate and record the two independent Stage 0 rerun artifacts."""
    protocol = load_protocol()
    expected_revision = protocol["pulse_revision"]
    revision = subprocess.check_output(
        ["git", "-C", str(PULSE), "rev-parse", "HEAD"], text=True).strip()
    if revision != expected_revision:
        raise RuntimeError(f"Expected Pulse {expected_revision}; found {revision}")
    base = PRIVATE / "stage0_repeats"
    records = []
    for index in (1, 2):
        csv_path = base / f"rerun_{index}.csv"
        log_path = base / f"rerun_{index}.log"
        if not csv_path.is_file() or not log_path.is_file():
            raise RuntimeError(f"Missing Stage 0 rerun {index} CSV or log")
        log = log_path.read_text(errors="replace")
        if f"GitHash : {revision[:9]}" not in log:
            raise RuntimeError(f"Stage 0 rerun {index} log does not identify the pinned Pulse build")
        records.append({"role": f"independent_rerun_{index}",
                        "path": "{HTN_COUPLING_ROOT}/" +
                                str(csv_path.relative_to(ROOT)),
                        "bytes": csv_path.stat().st_size,
                        "sha256": sha256(csv_path)})
    hashes = {item["sha256"] for item in records}
    sizes = {item["bytes"] for item in records}
    passed = len(hashes) == 1 and len(sizes) == 1
    result = {"created_utc": datetime.now(timezone.utc).isoformat(),
              "pulse_revision": revision,
              "previous_gate_sha256": json.loads(
                  (ROOT / "results/stage2/stage0_regression_gate.json").read_text()
              )["expected_sha256"],
              "expected_sha256": records[0]["sha256"] if passed else None,
              "passed": passed, "files": records}
    STAGE0_GATE.parent.mkdir(parents=True, exist_ok=True)
    STAGE0_GATE.write_text(json.dumps(result, indent=2) + "\n")
    if not passed:
        raise RuntimeError("Amended Stage 0 independent reruns do not match byte-for-byte")
    return result


def case_dir(case_id: str) -> Path:
    path = PRIVATE / "cases" / case_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def objective(result: dict, target: dict, protocol: dict) -> float:
    scale = protocol["pressure_match"]["objective_pressure_scale_mmHg"]
    return ((result["systolic_mmHg"] - target["achieved_systolic_mmHg"]) / scale) ** 2 + (
        (result["diastolic_mmHg"] - target["achieved_diastolic_mmHg"]) / scale) ** 2


def stationarity_metrics(trace: pd.DataFrame, protocol: dict) -> dict:
    """Measure pressure movement across equal bins in the declared window."""
    bins = int(protocol["pressure_match"]["stationarity"]["window_bins"])
    if len(trace) < bins:
        raise RuntimeError("stable trace is too short for stationarity assessment")
    index_bins = np.array_split(np.arange(len(trace)), bins)
    chunks = [trace.iloc[index] for index in index_bins]
    systolic = [float(chunk.systolic_mmHg.median()) for chunk in chunks]
    diastolic = [float(chunk.diastolic_mmHg.median()) for chunk in chunks]
    sbp_range = max(systolic) - min(systolic)
    dbp_range = max(diastolic) - min(diastolic)
    limits = protocol["pressure_match"]["stationarity"]
    return {
        "stationarity_sbp_bin_median_range_mmHg": sbp_range,
        "stationarity_dbp_bin_median_range_mmHg": dbp_range,
        "stationarity_pass": (
            sbp_range <= limits["maximum_sbp_bin_median_range_mmHg"] and
            dbp_range <= limits["maximum_dbp_bin_median_range_mmHg"]
        ),
    }


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
        stability = stationarity_metrics(trace, protocol)
        values["stroke_volume_mL"] = (values["cardiac_output_L_min"] * 1000 /
                                      values["heart_rate_per_min"])
        return {**job, "status": "ok", "wall_s": time.monotonic() - started,
                **values, **stability, **stage6.log_metrics(log)}
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
        if target.status != "ok" or not _stationarity_pass(
                getattr(target, "stationarity_pass", False)):
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
    path = OUT / "search_evaluations.csv"
    frame = pd.read_csv(path) if path.is_file() else pd.DataFrame()
    completed = completed_case_keys(frame)
    pending = [job for job in coarse_jobs(direct)
               if (job["target"], round(float(job["R"]), 6),
                   round(float(job["C"]), 6)) not in completed]
    protocol = load_protocol()
    chunk_size = max(4, workers * 4)
    for offset in range(0, len(pending), chunk_size):
        rows = run_jobs(pending[offset:offset + chunk_size], workers)
        for row in rows:
            row["J"] = objective(row, row, protocol) if row["status"] == "ok" else np.nan
        if rows:
            frame = pd.concat([frame, pd.DataFrame(rows)], ignore_index=True)
            frame = frame.drop_duplicates(subset=["target", "R", "C"], keep="last")
            completed.update((str(row["target"]), round(float(row["R"]), 6),
                              round(float(row["C"]), 6)) for row in rows)
        frame = frame.sort_values(["target", "status", "J"], na_position="last")
        frame.to_csv(path, index=False)
        print(f"coarse checkpoint: {min(offset + chunk_size, len(pending))}/"
              f"{len(pending)} new evaluations", flush=True)
    return frame


def _residuals(row: dict, reference: dict) -> tuple[float, float]:
    return (row["systolic_mmHg"] - reference["systolic_mmHg"],
            row["diastolic_mmHg"] - reference["diastolic_mmHg"])


def _stationarity_pass(value: object) -> bool:
    """Parse CSV booleans conservatively; missing and unknown values fail closed."""
    if pd.isna(value):
        return False
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes"}


def _passes(row: dict, reference: dict, protocol: dict) -> bool:
    if row.get("status") != "ok" or not _stationarity_pass(row.get("stationarity_pass", False)):
        return False
    ds, dd = _residuals(row, reference)
    limits = protocol["pressure_match"]
    return (abs(ds) <= limits["maximum_absolute_sbp_residual_mmHg"] and
            abs(dd) <= limits["maximum_absolute_dbp_residual_mmHg"])


def completed_case_keys(frame: pd.DataFrame) -> set[tuple[str, float, float]]:
    """Return parameter points with a completed evaluation to avoid rerunning them."""
    if frame.empty or not {"target", "R", "C", "status"}.issubset(frame.columns):
        return set()
    completed = frame[frame.status.isin(("ok", "failed"))]
    return {(str(row.target), round(float(row.R), 6), round(float(row.C), 6))
            for row in completed.itertuples(index=False)
            if pd.notna(row.R) and pd.notna(row.C)}


def _local_minima(frame: pd.DataFrame, target: str, spacing: float) -> list[dict]:
    if "stationarity_pass" not in frame.columns:
        return []
    stationary = frame.stationarity_pass.map(_stationarity_pass)
    rows = frame[(frame.target == target) & (frame.status == "ok") & stationary]
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
        completed = completed_case_keys(result)
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
                        if key in seen or key in completed:
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
        # Persist each completed stage so an interrupted finer search retains
        # its results instead of keeping them only in memory.
        result.to_csv(OUT / "search_evaluations.csv", index=False)
        if "refinement_step" in result:
            checkpoint = result[result.refinement_step.eq(step)]
            checkpoint.to_csv(OUT / f"search_checkpoint_refine_{step:g}.csv", index=False)
        previous = float(step)
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
    pd.DataFrame(repeats).to_csv(OUT / "confirmation_evaluations.csv", index=False)
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


def targeted_historical_panel(workers: int = 3, replicates: int = 3) -> pd.DataFrame:
    """Run historical coordinates in fresh worker processes before any new grid."""
    direct = direct_states(workers)
    if not all(row.status == "ok" and _stationarity_pass(row.stationarity_pass)
               for row in direct.itertuples(index=False)):
        raise RuntimeError("A direct target failed; stopping before modifier evaluations")
    coordinates = {
        "mild": (1.300, 0.720),
        "intermediate": (1.720, 0.600),
        "higher": (1.995, 0.465),
    }
    direct_by_target = direct.set_index("target")
    protocol = load_protocol()
    records: list[dict] = []
    output = OUT / "targeted_historical_panel.csv"
    for target, (resistance, compliance) in coordinates.items():
        reference = direct_by_target.loc[target]
        for replicate in range(1, replicates + 1):
            job = {
                "case_id": f"targeted_{target}_rep{replicate}_R{resistance:.3f}_C{compliance:.3f}",
                "route": "modifier", "target": target,
                "R": resistance, "C": compliance, "replicate": replicate,
                "requested_systolic_mmHg": reference.requested_systolic_mmHg,
                "requested_diastolic_mmHg": reference.requested_diastolic_mmHg,
                "achieved_systolic_mmHg": reference.systolic_mmHg,
                "achieved_diastolic_mmHg": reference.diastolic_mmHg,
                "keep_trace": True,
            }
            # A one-job executor is created and destroyed for every replicate,
            # guaranteeing that repeats use distinct OS processes.
            result = run_jobs([job], workers=1)[0]
            if result["status"] == "ok":
                objective_target = {
                    "achieved_systolic_mmHg": reference.systolic_mmHg,
                    "achieved_diastolic_mmHg": reference.diastolic_mmHg,
                }
                result["J"] = objective(result, objective_target, protocol)
                ds, dd = _residuals(result, reference)
                result["systolic_residual_mmHg"] = ds
                result["diastolic_residual_mmHg"] = dd
            records.append(result)
            pd.DataFrame(records).to_csv(output, index=False)
    return pd.DataFrame(records)


def manifest() -> None:
    gate = require_stage0()
    openbf = ROOT / "../openBF"
    try:
        openbf_revision = subprocess.check_output(
            ["git", "-C", str(openbf), "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        openbf_revision = None
    try:
        pulse_upstream_revision = subprocess.check_output(
            ["git", "-C", str(PULSE), "rev-parse", "refs/remotes/origin/stable"],
            text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        pulse_upstream_revision = None
    build_dir = Path(os.environ.get("PULSE_BUILD_DIR", PULSE / "build")).resolve()
    cache = build_dir / "CMakeCache.txt"
    build_keys = ("CMAKE_BUILD_TYPE", "CMAKE_CXX_COMPILER", "CMAKE_CXX_FLAGS_RELEASE",
                  "CMAKE_INSTALL_PREFIX", "Pulse_GEN_DATA", "Pulse_JAVA_API",
                  "Pulse_PYTHON_API", "Pulse_SUPERBUILD", "protobuf_DIR",
                  "Eigen3_DIR", "pybind11_DIR")
    build_config = {}
    if cache.is_file():
        lines = cache.read_text(errors="replace").splitlines()
        for key in build_keys:
            prefix = f"{key}:"
            line = next((item for item in lines if item.startswith(prefix)), None)
            if line:
                value = line.split("=", 1)[1]
                if key == "CMAKE_INSTALL_PREFIX":
                    value = "{PULSE_BUILD_DIR}/install"
                elif key.endswith("_DIR"):
                    value = "locally cached dependency package"
                build_config[key] = value
    stage0_log = _gate_file_path(gate["files"][0]["path"]).with_suffix(".log")
    log_text = stage0_log.read_text(errors="replace") if stage0_log.exists() else ""
    runtime_hash = next((line.split(":", 1)[1].strip() for line in log_text.splitlines()
                         if "GitHash :" in line), None)
    build_time = next((line.split(":", 1)[1].strip() for line in log_text.splitlines()
                       if "Build Time :" in line), None)
    try:
        julia_version = subprocess.check_output(["julia", "--version"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        julia_version = None
    result = {"created_utc": datetime.now(timezone.utc).isoformat(),
              "protocol_sha256": sha256(PROTOCOL),
              "stage0_sha256": gate["expected_sha256"],
              "pulse_revision": subprocess.check_output(
                  ["git", "-C", str(PULSE), "rev-parse", "HEAD"], text=True).strip(),
              "pulse_upstream_revision": pulse_upstream_revision,
              "pulse_runtime_git_hash": runtime_hash,
              "pulse_runtime_build_time": build_time,
              "pulse_build_configuration": build_config,
              "openbf_revision": openbf_revision,
              "htn_coupling_revision": subprocess.check_output(
                  ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
              "htn_coupling_worktree_status": subprocess.check_output(
                  ["git", "-C", str(ROOT), "status", "--short"], text=True).splitlines(),
              "julia_version": julia_version, "python_version": sys.version,
              "platform": platform.platform(),
              "pulse_path": "{PULSE_ROOT}",
              "pulse_runtime_data_root": "{PULSE_BIN}",
              "pulse_build_path": "{PULSE_BUILD_DIR}",
              "openbf_path": "{OPENBF_ROOT}",
              "htn_coupling_path": "{HTN_COUPLING_ROOT}"}
    (OUT / "run_manifest.json").write_text(json.dumps(result, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    parser.add_argument("--steps", nargs="+", choices=("stage0-gate", "manifest", "targeted-panel", "direct", "coarse", "refine", "finalize"), default=["manifest"])
    parser.add_argument("--final-search", action="store_true", help="permit direct and coarse model evaluations")
    args = parser.parse_args()
    directories()
    evaluation_steps = {"targeted-panel", "direct", "coarse", "refine", "finalize"}
    if any(step in evaluation_steps for step in args.steps) and not args.final_search:
        raise SystemExit("Final evaluations require --final-search after predeclaration review")
    if any(step in evaluation_steps for step in args.steps):
        require_stage0()
    if "stage0-gate" in args.steps:
        print(json.dumps(stage0_gate(), indent=2))
    if "manifest" in args.steps:
        manifest()
    if "targeted-panel" in args.steps:
        print(targeted_historical_panel(args.workers).to_string(index=False))
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
