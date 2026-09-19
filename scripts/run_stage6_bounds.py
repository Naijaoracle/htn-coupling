#!/usr/bin/env python3
"""Evaluate the Stage 6 configurable patient pressure envelope.

Generated patient definitions and participant-level rows remain beneath the
untracked private directory.  Only aggregate results are intended for commit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import os
import re
import subprocess
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
PULSE = Path(os.environ.get("PULSE_ROOT", "../pulse-physiology-engine"))
BIN = Path(os.environ.get("PULSE_BIN", PULSE / "build/install/bin")).resolve()
OUT = ROOT / "results/stage6"
PRIVATE = OUT / "private"
CASES = PRIVATE / "cases"
STATE = ROOT / "results/stage2/private/cache/StandardMale_stage2_baseline.json"
STAGE2 = ROOT / "results/stage2"
STAGE0_HASH = "462c43248785ce45771b056b53443252414ec066ae50bee0d3b276a42fcfab0a"

# Predeclared research envelope. Pulse's upstream-compatible defaults remain
# 90--120/60--80 and 0.75 when these optional patient fields are absent.
ENVELOPE = {
    "systolic_min_mmHg": 60.0,
    "systolic_max_mmHg": 200.0,
    "diastolic_min_mmHg": 40.0,
    "diastolic_max_mmHg": 130.0,
    "ratio_max": 0.95,
}

GRID = [
    (120, 80), (130, 80), (140, 80), (140, 90), (150, 90),
    (160, 90), (160, 100), (170, 100), (180, 100), (180, 110),
]

# These are successful Stage 2 cells. Their measured stock-engine pressures
# are used as direct-patient requests, so the comparison is at a shared target.
COMPARISON = [(1.2, 0.8), (1.4, 0.6), (1.6, 0.5)]

REGIONS = (
    "BrainVasculature", "LeftKidneyVasculature", "RightKidneyVasculature",
    "GutVasculature", "LiverVasculature", "MuscleVasculature",
    "SkinVasculature", "MyocardiumVasculature",
)

COLUMNS = [
    "time_s", "systolic_mmHg", "diastolic_mmHg", "map_mmHg",
    "heart_rate_per_min", "cardiac_output_L_min", "svr_mmHg_s_mL",
    "baroreceptor_heart_rate_scale", "baroreceptor_heart_elastance_scale",
    "baroreceptor_resistance_scale", "baroreceptor_compliance_scale",
    "aorta_inflow_mL_s", *[f"{x}_inflow_mL_min" for x in REGIONS],
]


def directories() -> None:
    for path in (OUT, PRIVATE, CASES):
        path.mkdir(parents=True, exist_ok=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def revision() -> str:
    return subprocess.check_output(
        ["git", "-C", str(PULSE), "rev-parse", "HEAD"], text=True).strip()


def pulse_symbols():
    from pulse.cdm.engine import SEDataRequest, SEDataRequestManager
    from pulse.cdm.patient import SEPatientConfiguration
    from pulse.cdm.patient_actions import SECardiovascularMechanicsModification
    from pulse.cdm.scalars import (FrequencyUnit, PressureTimePerVolumeUnit,
                                   PressureUnit, VolumePerTimeUnit)
    from pulse.engine.PulseEngine import PulseEngine
    if "PULSE_ROOT" in os.environ:
        import PyPulse
        expected = subprocess.check_output(
            ["git", "-C", str(PULSE.resolve()), "rev-parse", "--short=9", "HEAD"],
            text=True).strip()
        if PyPulse.__hash__ != expected:
            raise RuntimeError(
                f"Pulse Python binding hash {PyPulse.__hash__} does not match source {expected}")
    return locals()


def requests(s):
    r = s["SEDataRequest"]
    items = [
        r.create_physiology_request("SystolicArterialPressure", s["PressureUnit"].mmHg),
        r.create_physiology_request("DiastolicArterialPressure", s["PressureUnit"].mmHg),
        r.create_physiology_request("MeanArterialPressure", s["PressureUnit"].mmHg),
        r.create_physiology_request("HeartRate", s["FrequencyUnit"].Per_min),
        r.create_physiology_request("CardiacOutput", s["VolumePerTimeUnit"].L_Per_min),
        r.create_physiology_request(
            "SystemicVascularResistance", s["PressureTimePerVolumeUnit"].mmHg_s_Per_mL),
        r.create_physiology_request("BaroreceptorHeartRateScale"),
        r.create_physiology_request("BaroreceptorHeartElastanceScale"),
        r.create_physiology_request("BaroreceptorResistanceScale"),
        r.create_physiology_request("BaroreceptorComplianceScale"),
        r.create_liquid_compartment_request(
            "Aorta", "InFlow", s["VolumePerTimeUnit"].mL_Per_s),
    ]
    items.extend(r.create_liquid_compartment_request(
        name, "InFlow", s["VolumePerTimeUnit"].mL_Per_min) for name in REGIONS)
    return s["SEDataRequestManager"](items)


def patient_payload(name: str, systolic: float, diastolic: float) -> dict:
    pressure = lambda value: {"ScalarPressure": {"Value": value, "Unit": "mmHg"}}
    return {
        "Name": name,
        "Age": {"ScalarTime": {"Value": 44.0, "Unit": "yr"}},
        "Weight": {"ScalarMass": {"Value": 170.0, "Unit": "lb"}},
        "Height": {"ScalarLength": {"Value": 71.0, "Unit": "in"}},
        "BodyFatFraction": {"Scalar0To1": {"Value": 0.21}},
        "DiastolicArterialPressureBaseline": pressure(diastolic),
        "HeartRateBaseline": {"ScalarFrequency": {"Value": 72.0, "Unit": "1/min"}},
        "RespirationRateBaseline": {"ScalarFrequency": {"Value": 12.0, "Unit": "1/min"}},
        "SystolicArterialPressureBaseline": pressure(systolic),
        "SystolicArterialPressureBaselineMinimum": pressure(ENVELOPE["systolic_min_mmHg"]),
        "SystolicArterialPressureBaselineMaximum": pressure(ENVELOPE["systolic_max_mmHg"]),
        "DiastolicArterialPressureBaselineMinimum": pressure(ENVELOPE["diastolic_min_mmHg"]),
        "DiastolicArterialPressureBaselineMaximum": pressure(ENVELOPE["diastolic_max_mmHg"]),
        "DiastolicToSystolicPressureRatioMaximum": {
            "Scalar0To1": {"Value": ENVELOPE["ratio_max"]}},
    }


def stable_trace(engine, seconds: int = 12) -> pd.DataFrame:
    rows = []
    for _ in range(seconds * 50):
        if not engine.advance_time_s(0.02):
            raise RuntimeError("Pulse stopped while recording stable output")
        rows.append(dict(zip(COLUMNS, engine.pull_data().copy())))
    frame = pd.DataFrame(rows)
    if not np.isfinite(frame.select_dtypes("number").to_numpy()).all():
        raise RuntimeError("Pulse returned non-finite stable output")
    return frame


def endpoint(frame: pd.DataFrame) -> dict:
    values = frame.median(numeric_only=True).drop(labels="time_s").to_dict()
    values["pulse_pressure_mmHg"] = values["systolic_mmHg"] - values["diastolic_mmHg"]
    return values


def log_metrics(path: Path) -> dict:
    text = path.read_text(errors="replace") if path.exists() else ""
    tissue = re.findall(r"Successfully tuned tissue circuit at ([0-9.]+)s", text)
    convergence = re.findall(r"Convergence took ([0-9.]+)s to simulate ([0-9.]+)s", text)
    return {
        "tissue_tuning_simulated_s": float(tissue[-1]) if tissue else np.nan,
        "dynamic_stabilization_wall_s": float(convergence[-1][0]) if convergence else np.nan,
        "dynamic_stabilization_simulated_s": float(convergence[-1][1]) if convergence else np.nan,
        "cvp_out_of_range_warning_n": text.count("We're out of CVP range"),
        "outside_reference_warning_seen": "outside the reference envelope" in text,
    }


def direct_worker(job: dict) -> dict:
    tag = job["case_id"]
    case = CASES / tag
    case.mkdir(parents=True, exist_ok=True)
    patient = case / f"{tag}.json"
    patient.write_text(json.dumps(patient_payload(
        tag, job["requested_systolic_mmHg"], job["requested_diastolic_mmHg"]),
        indent=2) + "\n")
    log = case / "pulse.log"
    try:
        s = pulse_symbols()
        pc = s["SEPatientConfiguration"]()
        pc.set_data_root_dir(str(BIN))
        pc.set_patient_file(str(patient))
        engine = s["PulseEngine"](data_root_dir=str(BIN))
        engine.log_to_console(False)
        engine.set_log_filename(str(log))
        started = time.monotonic()
        initialized = engine.initialize_engine(pc, requests(s))
        wall = time.monotonic() - started
        if not initialized:
            raise RuntimeError("direct patient initialization returned false")
        trace = stable_trace(engine)
        if job.get("keep_trace"):
            trace.to_csv(case / "stable_trace.csv.gz", index=False, compression="gzip")
        result = {
            **job, "route": "direct", "status": "ok", "initialization_wall_s": wall,
            **endpoint(trace), **log_metrics(log),
        }
        result["systolic_residual_mmHg"] = (
            result["systolic_mmHg"] - job["requested_systolic_mmHg"])
        result["diastolic_residual_mmHg"] = (
            result["diastolic_mmHg"] - job["requested_diastolic_mmHg"])
        return result
    except Exception as exc:
        return {**job, "route": "direct", "status": "failed", "error": str(exc),
                "traceback": traceback.format_exc(), **log_metrics(log)}


def modifier_worker(job: dict) -> dict:
    tag = job["case_id"]
    case = CASES / tag
    case.mkdir(parents=True, exist_ok=True)
    log = case / "pulse.log"
    try:
        s = pulse_symbols()
        engine = s["PulseEngine"](data_root_dir=str(BIN))
        engine.log_to_console(False)
        engine.set_log_filename(str(log))
        if not engine.serialize_from_file(str(STATE), requests(s)):
            raise RuntimeError("could not load the stock StandardMale state")
        action = s["SECardiovascularMechanicsModification"]()
        action.get_modifiers().get_systemic_resistance_multiplier().set_value(
            job["resistance_multiplier"])
        action.get_modifiers().get_arterial_compliance_multiplier().set_value(
            job["compliance_multiplier"])
        started = time.monotonic()
        engine.process_action(action)
        wall = time.monotonic() - started
        if not engine.advance_time_s(0.02):
            raise RuntimeError("Pulse stopped after modifier restabilization")
        trace = stable_trace(engine)
        trace.to_csv(case / "stable_trace.csv.gz", index=False, compression="gzip")
        result = {
            **job, "route": "modifier", "status": "ok",
            "initialization_wall_s": wall, **endpoint(trace), **log_metrics(log),
        }
        result["systolic_residual_mmHg"] = (
            result["systolic_mmHg"] - job["requested_systolic_mmHg"])
        result["diastolic_residual_mmHg"] = (
            result["diastolic_mmHg"] - job["requested_diastolic_mmHg"])
        return result
    except Exception as exc:
        return {**job, "route": "modifier", "status": "failed", "error": str(exc),
                "traceback": traceback.format_exc(), **log_metrics(log)}


def parallel(jobs: list[dict], worker, workers: int, label: str) -> list[dict]:
    rows = []
    with ProcessPoolExecutor(
            max_workers=workers, mp_context=mp.get_context("spawn")) as pool:
        futures = [pool.submit(worker, job) for job in jobs]
        with tqdm(total=len(futures), desc=label, unit="run") as progress:
            for future in as_completed(futures):
                rows.append(future.result())
                progress.set_postfix(ok=sum(x.get("status") == "ok" for x in rows))
                progress.update()
    return rows


def run_grid(workers: int) -> pd.DataFrame:
    jobs = [{
        "case_id": f"grid_{s}_{d}", "requested_systolic_mmHg": float(s),
        "requested_diastolic_mmHg": float(d), "keep_trace": False,
    } for s, d in GRID]
    frame = pd.DataFrame(parallel(jobs, direct_worker, workers, "Direct pressure grid"))
    frame = frame.sort_values(["requested_systolic_mmHg", "requested_diastolic_mmHg"])
    frame.to_csv(OUT / "direct_pressure_grid.csv", index=False)
    return frame


def comparison_targets() -> list[dict]:
    frames = [pd.read_csv(STAGE2 / "reachability_sweep.csv"),
              pd.read_csv(STAGE2 / "extended_boundary_sweep.csv")]
    sweep = pd.concat(frames, ignore_index=True).drop_duplicates(
        ["resistance_multiplier", "compliance_multiplier"], keep="last")
    rows = []
    for index, (r_value, c_value) in enumerate(COMPARISON, 1):
        found = sweep[np.isclose(sweep.resistance_multiplier, r_value)
                      & np.isclose(sweep.compliance_multiplier, c_value)
                      & sweep.status.eq("ok")]
        if len(found) != 1:
            raise RuntimeError(f"Could not resolve Stage 2 cell R={r_value}, C={c_value}")
        row = found.iloc[0]
        rows.append({
            "pair_id": f"pair_{index}", "requested_systolic_mmHg":
                float(row.achieved_systolic_mmHg),
            "requested_diastolic_mmHg": float(row.achieved_diastolic_mmHg),
            "resistance_multiplier": r_value, "compliance_multiplier": c_value,
        })
    return rows


def cycle_shape(frame: pd.DataFrame) -> np.ndarray:
    from scipy.signal import find_peaks
    flow = frame.aorta_inflow_mL_s.to_numpy()
    peaks, _ = find_peaks(flow, distance=25, prominence=max(np.ptp(flow) * .2, 1e-6))
    if len(peaks) < 3:
        raise RuntimeError("could not identify stable aortic-flow cycles")
    cycles = []
    phase = np.linspace(0, 1, 501)
    for left, right in zip(peaks[-5:-1], peaks[-4:]):
        source = np.linspace(0, 1, right-left+1)
        cycles.append(np.interp(phase, source, flow[left:right+1]))
    mean = np.mean(cycles, axis=0)
    return (mean - mean.mean()) / np.ptp(mean)


def run_comparison(workers: int) -> pd.DataFrame:
    targets = comparison_targets()
    direct_jobs, modifier_jobs = [], []
    for target in targets:
        shared = {**target, "keep_trace": True}
        direct_jobs.append({**shared, "case_id": f"{target['pair_id']}_direct"})
        modifier_jobs.append({**shared, "case_id": f"{target['pair_id']}_modifier"})
    rows = parallel(direct_jobs, direct_worker, workers, "Direct route")
    rows += parallel(modifier_jobs, modifier_worker, workers, "Modifier route")
    frame = pd.DataFrame(rows).sort_values(["pair_id", "route"])
    frame.to_csv(OUT / "direct_vs_modifier_endpoints.csv", index=False)

    metrics = []
    endpoint_columns = [
        "systolic_mmHg", "diastolic_mmHg", "map_mmHg", "heart_rate_per_min",
        "cardiac_output_L_min", "svr_mmHg_s_mL",
        *[f"{x}_inflow_mL_min" for x in REGIONS],
    ]
    for pair_id, group in frame.groupby("pair_id"):
        if not group.status.eq("ok").all() or len(group) != 2:
            continue
        routes = group.set_index("route")
        row = {"pair_id": pair_id}
        for column in endpoint_columns:
            row[f"direct_{column}"] = routes.loc["direct", column]
            row[f"modifier_{column}"] = routes.loc["modifier", column]
            row[f"direct_minus_modifier_{column}"] = (
                routes.loc["direct", column] - routes.loc["modifier", column])
        direct_trace = pd.read_csv(CASES / f"{pair_id}_direct/stable_trace.csv.gz")
        modifier_trace = pd.read_csv(CASES / f"{pair_id}_modifier/stable_trace.csv.gz")
        dshape, mshape = cycle_shape(direct_trace), cycle_shape(modifier_trace)
        row["aortic_flow_normalized_shape_rmse"] = float(
            np.sqrt(np.mean((dshape-mshape)**2)))
        metrics.append(row)
    pd.DataFrame(metrics).to_csv(OUT / "direct_vs_modifier_differences.csv", index=False)
    return frame


def load_cohorts() -> dict[str, pd.DataFrame]:
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from run_stage2_tier0 import load_elsa, load_haalsi
    return {"HAALSI": load_haalsi(), "ELSA Wave 8": load_elsa()}


def pressure_flags(frame: pd.DataFrame, fork: bool) -> pd.Series:
    sbp, dbp = frame.systolic_mmHg, frame.diastolic_mmHg
    if fork:
        return (sbp.between(ENVELOPE["systolic_min_mmHg"], ENVELOPE["systolic_max_mmHg"])
                & dbp.between(ENVELOPE["diastolic_min_mmHg"], ENVELOPE["diastolic_max_mmHg"])
                & (dbp <= ENVELOPE["ratio_max"] * sbp) & (sbp > dbp))
    return (sbp.between(90, 120) & dbp.between(60, 80) & (dbp <= .75 * sbp))


def run_coverage() -> pd.DataFrame:
    summary, binders = [], []
    for cohort, raw in load_cohorts().items():
        frame = raw.dropna(subset=["systolic_mmHg", "diastolic_mmHg"]).copy()
        frame["bmi_kg_m2"] = frame.weight_kg / (frame.height_cm / 100) ** 2
        complete = frame[["age_years", "sex", "height_cm", "weight_kg"]].notna().all(axis=1)
        age = frame.age_years.between(18, 65)
        height = frame.height_cm.between(137.16, 213.36)
        bmi = frame.bmi_kg_m2.between(16, 30)
        sex = frame.sex.isin(["Male", "Female"])
        body = complete & age & height & bmi & sex
        before, after = pressure_flags(frame, False), pressure_flags(frame, True)
        wide = (frame.systolic_mmHg-frame.diastolic_mmHg >= 60)
        hypertensive = (frame.systolic_mmHg >= 140) | (frame.diastolic_mmHg >= 90)
        for label, pressure in (("upstream_default", before),
                                ("stage6_declared_envelope", after)):
            summary.append({
                "cohort": cohort, "configuration": label, "valid_pressure_n": len(frame),
                "pressure_representable_n": int(pressure.sum()),
                "pressure_representable_pct": 100*float(pressure.mean()),
                "pressure_excluded_n": int((~pressure).sum()),
                "pressure_excluded_pct": 100*float((~pressure).mean()),
                "full_constraints_representable_n": int((pressure & body).sum()),
                "full_constraints_representable_pct": 100*float((pressure & body).mean()),
                "wide_pulse_pressure_n": int(wide.sum()),
                "wide_pulse_pressure_representable_n": int((wide & pressure).sum()),
                "wide_pulse_pressure_representable_pct":
                    100*float((wide & pressure).sum()/wide.sum()) if wide.sum() else np.nan,
                "hypertensive_n": int(hypertensive.sum()),
                "hypertensive_pressure_representable_n": int((hypertensive & pressure).sum()),
                "hypertensive_pressure_representable_pct":
                    100*float((hypertensive & pressure).sum()/hypertensive.sum()),
            })
        eligible_pressure = after
        reasons = {
            "missing_body_data": ~complete,
            "age_outside_18_65": complete & ~age,
            "bmi_outside_16_30": complete & ~bmi,
            "height_outside_4.5_7_ft": complete & ~height,
            "sex_unresolved": complete & ~sex,
        }
        for name, mask in reasons.items():
            binders.append({
                "cohort": cohort, "constraint": name,
                "among_pressure_representable_n": int(eligible_pressure.sum()),
                "excluded_n": int((eligible_pressure & mask).sum()),
                "excluded_pct": 100*float((eligible_pressure & mask).sum()/eligible_pressure.sum()),
            })
    table = pd.DataFrame(summary)
    table.to_csv(OUT / "cohort_coverage_before_after.csv", index=False)
    pd.DataFrame(binders).to_csv(OUT / "post_pressure_binding_constraints.csv", index=False)
    (OUT / "coverage_configuration.json").write_text(json.dumps({
        "declared_stage6_envelope": ENVELOPE,
        "hard_physical_rules": ["SBP > 0", "DBP > 0", "SBP > DBP"],
        "unchanged_body_constraints": {
            "age_years": [18, 65], "bmi_kg_m2": [16, 30],
            "height_cm": [137.16, 213.36],
        },
        "wide_pulse_pressure_definition": "SBP - DBP >= 60 mmHg",
        "note": "Aggregate audit; no participant identifiers are written.",
    }, indent=2) + "\n")
    return table


def gate_record() -> dict:
    archived = BIN / "test_results/scenarios/patient/HemorrhageToShockResults.csv"
    fresh = PULSE / "data/human/adult/scenarios/patient/HemorrhageToShockResults.csv"
    rows = [{"role": role, "path": str(path), "bytes": path.stat().st_size,
             "sha256": sha256(path)} for role, path in
            (("archived_reference", archived), ("fresh_rerun", fresh))]
    result = {"pulse_revision": revision(), "expected_sha256": STAGE0_HASH,
              "passed": all(x["sha256"] == STAGE0_HASH for x in rows)
                        and len({x["bytes"] for x in rows}) == 1,
              "files": rows}
    (OUT / "stage0_regression_gate.json").write_text(json.dumps(result, indent=2)+"\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    parser.add_argument("--steps", nargs="+", choices=("grid", "compare", "coverage", "gate"),
                        default=["grid", "compare", "coverage", "gate"])
    args = parser.parse_args()
    directories()
    if "grid" in args.steps:
        print(run_grid(args.workers).to_string(index=False))
    if "compare" in args.steps:
        print(run_comparison(args.workers).to_string(index=False))
    if "coverage" in args.steps:
        print(run_coverage().to_string(index=False))
    if "gate" in args.steps:
        print(json.dumps(gate_record(), indent=2))


if __name__ == "__main__":
    main()
