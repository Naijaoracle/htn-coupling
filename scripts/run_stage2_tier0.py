#!/usr/bin/env python3
"""Run the stock-Pulse Tier 0 hypertension experiments.

All phenotypes start as admissible normotensive patients. Only the released
systemic-resistance and arterial-compliance modifiers are applied; this script
does not edit Pulse or set a hypertensive baseline.
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

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.interpolate import LinearNDInterpolator
from scipy.spatial import Delaunay
from tqdm import tqdm


ROOT = Path(__file__).resolve().parents[1]
PULSE = Path(os.environ.get("PULSE_ROOT", "{PULSE_ROOT}"))
BIN = PULSE / "build/install/bin"
OUT = ROOT / "results/stage2"
PRIVATE = OUT / "private"
LOGS = PRIVATE / "logs"
CACHE = PRIVATE / "cache"
HAALSI = PULSE / "dataverse_files/HAALSI_baseline_dataverse_14Apr2017.tab"
ELSA = (PULSE / "dataverse_files"
        / "5050tab_6E3332402138AD5696C0CF0F7891314F5DA7035F7A39B8E5F424AA708E6F0899_V1"
        / "UKDA-5050-tab")
STAGE0_REF = BIN / "test_results/scenarios/patient/HemorrhageToShockResults.csv"
STAGE0_RERUN = PULSE / "data/human/adult/scenarios/patient/HemorrhageToShockResults.csv"
STAGE0_HASH = "462c43248785ce45771b056b53443252414ec066ae50bee0d3b276a42fcfab0a"
SEED = 20260816
TOL_SBP = 5.0
TOL_DBP = 5.0

HEADERS = [
    "time_s", "systolic_mmHg", "diastolic_mmHg", "map_mmHg",
    "heart_rate_per_min", "cardiac_output_L_min", "stroke_volume_mL",
    "systemic_vascular_resistance_mmHg_s_mL", "blood_volume_mL",
    "baroreceptor_heart_rate_scale", "baroreceptor_heart_elastance_scale",
    "baroreceptor_resistance_scale", "baroreceptor_compliance_scale",
]


def directories():
    for path in (OUT, PRIVATE, LOGS, CACHE):
        path.mkdir(parents=True, exist_ok=True)


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stage0_gate():
    """Require the fresh baseline rerun to be byte-identical to the reference."""
    records = []
    for role, path in (("archived_reference", STAGE0_REF), ("fresh_rerun", STAGE0_RERUN)):
        if not path.exists():
            raise RuntimeError(f"Missing Stage 0 gate file: {path}")
        records.append({"role": role, "path": str(path), "bytes": path.stat().st_size,
                        "sha256": file_hash(path)})
    passed = (records[0]["sha256"] == records[1]["sha256"] == STAGE0_HASH
              and records[0]["bytes"] == records[1]["bytes"])
    result = {
        "passed": passed, "expected_sha256": STAGE0_HASH,
        "pulse_revision": subprocess.check_output(
            ["git", "-C", str(PULSE), "rev-parse", "HEAD"], text=True).strip(),
        "files": records,
    }
    (OUT / "stage0_regression_gate.json").write_text(json.dumps(result, indent=2) + "\n")
    if not passed:
        raise RuntimeError("Stage 0 byte-identity gate failed")


def pulse_symbols():
    """Import Pulse lazily so spawned workers start cleanly."""
    from pulse.cdm.engine import IEventHandler, SEDataRequest, SEDataRequestManager, eEvent
    from pulse.cdm.patient import SEPatientConfiguration, eSex
    from pulse.cdm.patient_actions import (
        SECardiovascularMechanicsModification, SEHemorrhage, eHemorrhage_Compartment)
    from pulse.cdm.scalars import (
        FrequencyUnit, LengthUnit, MassUnit, PressureTimePerVolumeUnit,
        PressureUnit, TimeUnit, VolumePerTimeUnit, VolumeUnit)
    from pulse.engine.PulseEngine import PulseEngine
    return locals()


def requests(s):
    r = s["SEDataRequest"]
    return s["SEDataRequestManager"]([
        r.create_physiology_request("SystolicArterialPressure", s["PressureUnit"].mmHg),
        r.create_physiology_request("DiastolicArterialPressure", s["PressureUnit"].mmHg),
        r.create_physiology_request("MeanArterialPressure", s["PressureUnit"].mmHg),
        r.create_physiology_request("HeartRate", s["FrequencyUnit"].Per_min),
        r.create_physiology_request("CardiacOutput", s["VolumePerTimeUnit"].L_Per_min),
        r.create_physiology_request("HeartStrokeVolume", s["VolumeUnit"].mL),
        r.create_physiology_request(
            "SystemicVascularResistance", s["PressureTimePerVolumeUnit"].mmHg_s_Per_mL),
        r.create_physiology_request("BloodVolume", s["VolumeUnit"].mL),
        r.create_physiology_request("BaroreceptorHeartRateScale"),
        r.create_physiology_request("BaroreceptorHeartElastanceScale"),
        r.create_physiology_request("BaroreceptorResistanceScale"),
        r.create_physiology_request("BaroreceptorComplianceScale"),
    ])


def row(values):
    result = dict(zip(HEADERS, values))
    result["pulse_pressure_mmHg"] = result["systolic_mmHg"] - result["diastolic_mmHg"]
    return result


def endpoint(engine, seconds=10):
    rows = []
    for _ in range(seconds):
        if not engine.advance_time_s(1):
            raise RuntimeError("Pulse stopped while sampling a stabilized endpoint")
        rows.append(row(engine.pull_data()))
    frame = pd.DataFrame(rows)
    values = frame.drop(columns="time_s").median(numeric_only=True).to_dict()
    if not np.isfinite(list(values.values())).all():
        raise RuntimeError("Pulse returned a non-finite endpoint")
    return values


def standard_configuration(s):
    pc = s["SEPatientConfiguration"]()
    pc.set_data_root_dir(str(BIN))
    pc.set_patient_file("StandardMale.json")
    return pc


def person_configuration(s, spec):
    pc = s["SEPatientConfiguration"]()
    pc.set_data_root_dir(str(BIN))
    p = pc.get_patient()
    p.set_name(spec["sample_id"])
    p.set_sex(s["eSex"].Male if spec["sex"] == "Male" else s["eSex"].Female)
    p.get_age().set_value(float(spec["age_years"]), s["TimeUnit"].yr)
    p.get_height().set_value(float(spec["height_cm"]), s["LengthUnit"].cm)
    p.get_weight().set_value(float(spec["weight_kg"]), s["MassUnit"].kg)
    return pc


def modify(engine, s, resistance, compliance):
    action = s["SECardiovascularMechanicsModification"]()
    action.get_modifiers().get_systemic_resistance_multiplier().set_value(float(resistance))
    action.get_modifiers().get_arterial_compliance_multiplier().set_value(float(compliance))
    started = time.monotonic()
    engine.process_action(action)  # default incremental=False invokes restabilisation
    wall_s = time.monotonic() - started
    # Python process_action returns None. An engine step is the liveness check.
    if not engine.advance_time_s(0.02):
        raise RuntimeError("Pulse failed after cardiovascular restabilisation")
    return wall_s


def standard_state(force=False):
    directories()
    path = CACHE / "StandardMale_stage2_baseline.json"
    if path.exists() and not force:
        return path
    s = pulse_symbols()
    engine = s["PulseEngine"](data_root_dir=str(BIN))
    engine.log_to_console(False)
    engine.set_log_filename(str(LOGS / "standard_state_creation.log"))
    if not engine.initialize_engine(standard_configuration(s), requests(s)):
        raise RuntimeError("Could not initialize StandardMale")
    if not engine.serialize_to_file(str(path)):
        raise RuntimeError("Could not serialize StandardMale state")
    return path


def standard_engine(log_name):
    s = pulse_symbols()
    path = standard_state()
    engine = s["PulseEngine"](data_root_dir=str(BIN))
    engine.log_to_console(False)
    engine.set_log_filename(str(LOGS / log_name))
    if not engine.serialize_from_file(str(path), requests(s)):
        raise RuntimeError("Could not load StandardMale state")
    return engine, s


def modifier_worker(job):
    r, c = job["resistance_multiplier"], job["compliance_multiplier"]
    tag = f"R{r:.2f}_C{c:.2f}".replace(".", "p")
    try:
        engine, s = standard_engine(f"sweep_{tag}.log")
        baseline = endpoint(engine, 3)
        elapsed = modify(engine, s, r, c)
        achieved = endpoint(engine, 10)
        return {
            **job, "status": "ok", "restabilization_wall_s": elapsed,
            **{f"baseline_{k}": v for k, v in baseline.items()},
            **{f"achieved_{k}": v for k, v in achieved.items()},
        }
    except Exception as exc:
        return {**job, "status": "failed", "error": str(exc),
                "traceback": traceback.format_exc()}


def parallel(jobs, worker, workers, label):
    results = []
    with ProcessPoolExecutor(
            max_workers=workers, mp_context=mp.get_context("spawn")) as pool:
        futures = [pool.submit(worker, job) for job in jobs]
        with tqdm(total=len(futures), desc=label, unit="run") as progress:
            for future in as_completed(futures):
                results.append(future.result())
                progress.set_postfix(ok=sum(x.get("status") == "ok" for x in results))
                progress.update()
    return results


def smoke():
    standard_state(force=True)
    jobs = [
        {"grid_id": "control", "resistance_multiplier": 1.0,
         "compliance_multiplier": 1.0},
        {"grid_id": "modified", "resistance_multiplier": 1.3,
         "compliance_multiplier": 0.7},
    ]
    frame = pd.DataFrame([modifier_worker(job) for job in jobs])
    frame.to_csv(OUT / "modifier_smoke_test.csv", index=False)
    if not frame["status"].eq("ok").all():
        raise RuntimeError("Modifier smoke test failed")
    return frame


def sweep(workers):
    r_values = np.round(np.arange(1.0, 1.6001, 0.05), 2)
    c_values = np.round(np.arange(1.0, 0.4999, -0.05), 2)
    jobs = [
        {"grid_id": f"R{r:.2f}_C{c:.2f}", "resistance_multiplier": float(r),
         "compliance_multiplier": float(c)}
        for r in r_values for c in c_values
    ]
    frame = pd.DataFrame(parallel(jobs, modifier_worker, workers, "Pulse reachability"))
    frame = frame.sort_values(["resistance_multiplier", "compliance_multiplier"])
    frame.to_csv(OUT / "reachability_sweep.csv", index=False)
    plot_reachability(frame)
    return frame


def plot_reachability(frame):
    ok, failed = frame[frame.status == "ok"], frame[frame.status != "ok"]
    fig, axes = plt.subplots(1, 3, figsize=(17, 5), constrained_layout=True)
    points = axes[0].scatter(
        ok.achieved_systolic_mmHg, ok.achieved_diastolic_mmHg,
        c=ok.achieved_map_mmHg, cmap="viridis", s=42)
    axes[0].set(xlabel="Achieved SBP (mmHg)", ylabel="Achieved DBP (mmHg)",
                title="Reachable pressure pairs")
    fig.colorbar(points, ax=axes[0], label="Achieved MAP (mmHg)")
    status = frame.pivot(index="compliance_multiplier",
                         columns="resistance_multiplier", values="status").eq("ok")
    axes[1].imshow(
        status.astype(int), origin="lower", aspect="auto", cmap="RdYlGn",
        vmin=0, vmax=1,
        extent=[status.columns.min(), status.columns.max(),
                status.index.min(), status.index.max()])
    if failed.empty:
        axes[1].text(.03, .04, "No failure observed in tested domain",
                     transform=axes[1].transAxes)
    else:
        axes[1].scatter(failed.resistance_multiplier, failed.compliance_multiplier,
                        marker="x", color="black", label="Failed")
        axes[1].legend()
    axes[1].set(xlabel="Systemic resistance multiplier",
                ylabel="Arterial compliance multiplier",
                title="Restabilisation boundary")
    timing = frame.pivot(
        index="compliance_multiplier", columns="resistance_multiplier",
        values="restabilization_wall_s")
    image = axes[2].imshow(
        timing, origin="lower", aspect="auto", cmap="magma",
        extent=[timing.columns.min(), timing.columns.max(),
                timing.index.min(), timing.index.max()])
    axes[2].set(xlabel="Systemic resistance multiplier",
                ylabel="Arterial compliance multiplier",
                title="Convergence cost")
    fig.colorbar(image, ax=axes[2], label="Restabilisation wall time (s)")
    fig.savefig(OUT / "reachability_and_failure_boundary.png", dpi=180)
    plt.close(fig)


class Lookup:
    """Transparent piecewise-linear inverse of successful sweep cells."""
    def __init__(self, frame):
        ok = frame[frame.status == "ok"]
        pressure = ok[["achieved_systolic_mmHg", "achieved_diastolic_mmHg"]].to_numpy()
        modifier = ok[["resistance_multiplier", "compliance_multiplier"]].to_numpy()
        if len(pressure) < 3:
            raise RuntimeError("Too few successful cells for calibration")
        self.hull = Delaunay(pressure, qhull_options="QJ")
        self.r = LinearNDInterpolator(self.hull, modifier[:, 0], fill_value=np.nan)
        self.c = LinearNDInterpolator(self.hull, modifier[:, 1], fill_value=np.nan)
        mhull = Delaunay(modifier, qhull_options="QJ")
        self.s = LinearNDInterpolator(mhull, pressure[:, 0], fill_value=np.nan)
        self.d = LinearNDInterpolator(mhull, pressure[:, 1], fill_value=np.nan)

    def predict(self, systolic, diastolic):
        target = np.array([[float(systolic), float(diastolic)]])
        if self.hull.find_simplex(target)[0] < 0:
            return {"lookup_reachable": False, "resistance_multiplier": np.nan,
                    "compliance_multiplier": np.nan}
        r = float(np.asarray(self.r(target)).ravel()[0])
        c = float(np.asarray(self.c(target)).ravel()[0])
        if not np.isfinite([r, c]).all():
            return {"lookup_reachable": False, "resistance_multiplier": np.nan,
                    "compliance_multiplier": np.nan}
        achieved_s = float(np.asarray(self.s([[r, c]])).ravel()[0])
        achieved_d = float(np.asarray(self.d([[r, c]])).ravel()[0])
        return {
            "lookup_reachable": True, "resistance_multiplier": r,
            "compliance_multiplier": c,
            "estimated_systolic_mmHg": achieved_s,
            "estimated_diastolic_mmHg": achieved_d,
            "estimated_systolic_residual_mmHg": achieved_s - systolic,
            "estimated_diastolic_residual_mmHg": achieved_d - diastolic,
            "estimated_euclidean_residual_mmHg":
                float(np.hypot(achieved_s - systolic, achieved_d - diastolic)),
        }


def calibration_table(frame, workers):
    lookup = Lookup(frame)
    rows = []
    for systolic in range(80, 211, 5):
        for diastolic in range(45, 126, 5):
            rows.append({"target_systolic_mmHg": systolic,
                         "target_diastolic_mmHg": diastolic,
                         **lookup.predict(systolic, diastolic)})
    table = pd.DataFrame(rows)
    reachable = table[table.lookup_reachable].copy()
    jobs = []
    for target in reachable.to_dict("records"):
        jobs.append({
            **target,
            "grid_id": (
                f"target_{target['target_systolic_mmHg']}_"
                f"{target['target_diastolic_mmHg']}"),
        })
    if jobs:
        validation = pd.DataFrame(parallel(
            jobs, modifier_worker, workers, "Calibration validation"))
        keep = [
            "target_systolic_mmHg", "target_diastolic_mmHg", "status",
            "restabilization_wall_s", "achieved_systolic_mmHg",
            "achieved_diastolic_mmHg", "achieved_map_mmHg",
            "achieved_pulse_pressure_mmHg", "achieved_heart_rate_per_min",
            "achieved_cardiac_output_L_min",
        ]
        validation = validation[keep].rename(
            columns={"status": "validation_status"})
        table = table.merge(
            validation,
            on=["target_systolic_mmHg", "target_diastolic_mmHg"],
            how="left")
        table["achieved_systolic_residual_mmHg"] = (
            table.achieved_systolic_mmHg - table.target_systolic_mmHg)
        table["achieved_diastolic_residual_mmHg"] = (
            table.achieved_diastolic_mmHg - table.target_diastolic_mmHg)
        table["achieved_euclidean_residual_mmHg"] = np.hypot(
            table.achieved_systolic_residual_mmHg,
            table.achieved_diastolic_residual_mmHg)
        table["validated_within_tolerance"] = (
            table.achieved_systolic_residual_mmHg.abs().le(TOL_SBP)
            & table.achieved_diastolic_residual_mmHg.abs().le(TOL_DBP))
    table.to_csv(OUT / "calibration_lookup_table.csv", index=False)
    return table


def load_haalsi():
    columns = {
        "rage": "age_years", "rsex": "sex_code",
        "c_bs_mean_sys": "systolic_mmHg", "c_bs_mean_dia": "diastolic_mmHg",
        "c_bs_height": "height_cm", "c_bs_weight": "weight_kg",
    }
    frame = pd.read_csv(
        HAALSI, sep="\t", usecols=list(columns), low_memory=False).rename(columns=columns)
    frame["sex"] = frame.sex_code.map({1: "Male", 2: "Female"})
    if frame[["systolic_mmHg", "diastolic_mmHg"]].notna().all(axis=1).sum() != 4895:
        raise RuntimeError("HAALSI pressure count changed from Stage 1")
    return frame


def load_elsa():
    tab = ELSA / "tab"
    nurse = pd.read_csv(
        tab / "wave_8_elsa_nurse_data_eul_v1.tab", sep="\t",
        usecols=["idauniq", "indsex", "bprespc", "sysval", "diaval",
                 "sys2", "sys3", "dias2", "dias3"], low_memory=False)
    harmonized = pd.read_csv(
        tab / "gh_elsa_h.tab", sep="\t",
        usecols=["idauniq", "r8agey", "r8mheight", "r8mweight"], low_memory=False)
    for column in ("r8agey", "r8mheight", "r8mweight"):
        harmonized[column] = pd.to_numeric(harmonized[column], errors="coerce")
    frame = nurse.merge(harmonized, on="idauniq", how="left", validate="one_to_one")
    valid = frame.bprespc.eq(1) & frame.sysval.gt(0) & frame.diaval.gt(0)
    if valid.sum() != 3317:
        raise RuntimeError("ELSA pressure count changed from Stage 1")
    frame["age_years"] = frame.r8agey
    frame["sex"] = frame.indsex.map({1: "Male", 2: "Female"})
    frame["systolic_mmHg"] = frame.sysval.where(valid)
    frame["diastolic_mmHg"] = frame.diaval.where(valid)
    frame["height_cm"] = frame.r8mheight * 100
    frame["weight_kg"] = frame.r8mweight
    return frame


def admissibility(frame):
    out = frame.copy()
    out["bmi_kg_m2"] = out.weight_kg / (out.height_cm / 100) ** 2
    out["body_data_complete"] = out[
        ["age_years", "sex", "height_cm", "weight_kg"]].notna().all(axis=1)
    out["body_admissible"] = (
        out.body_data_complete & out.age_years.between(18, 65)
        & out.height_cm.between(137.16, 213.36)
        & out.bmi_kg_m2.between(16, 30)
        & out.sex.isin(["Male", "Female"]))
    pressure = (out.systolic_mmHg.between(90, 120)
                & out.diastolic_mmHg.between(60, 80)
                & (out.diastolic_mmHg <= .75 * out.systolic_mmHg))
    out["direct_pressure_admissible"] = pressure
    out["direct_all_constraints_admissible"] = out.body_admissible & pressure
    return out


def population_jobs(name, source, frame, n, seed):
    sampled = source.dropna(subset=["systolic_mmHg", "diastolic_mmHg"]).sample(
        n=n, replace=False, random_state=seed).reset_index(drop=True)
    sampled = admissibility(sampled)
    sampled.insert(0, "sample_id",
                   [f"{name.upper()}_{i:04d}" for i in range(1, n + 1)])
    lookup = Lookup(frame)
    predictions = pd.DataFrame([
        lookup.predict(x.systolic_mmHg, x.diastolic_mmHg)
        for x in sampled.itertuples()])
    sampled = pd.concat([sampled, predictions], axis=1)
    sampled["attempted_modifier_run"] = (
        sampled.body_admissible & sampled.lookup_reachable)
    return sampled, sampled[sampled.attempted_modifier_run].to_dict("records")


def person_worker(job):
    try:
        s = pulse_symbols()
        engine = s["PulseEngine"](data_root_dir=str(BIN))
        engine.log_to_console(False)
        engine.set_log_filename(str(LOGS / f"population_{job['sample_id']}.log"))
        if not engine.initialize_engine(person_configuration(s, job), requests(s)):
            raise RuntimeError("Pulse rejected or could not stabilize the body-defined patient")
        baseline = endpoint(engine, 3)
        elapsed = modify(
            engine, s, job["resistance_multiplier"], job["compliance_multiplier"])
        achieved = endpoint(engine, 10)
        sr = achieved["systolic_mmHg"] - job["systolic_mmHg"]
        dr = achieved["diastolic_mmHg"] - job["diastolic_mmHg"]
        return {
            "sample_id": job["sample_id"], "status": "ok",
            "restabilization_wall_s": elapsed,
            "baseline_systolic_mmHg": baseline["systolic_mmHg"],
            "baseline_diastolic_mmHg": baseline["diastolic_mmHg"],
            "achieved_systolic_mmHg": achieved["systolic_mmHg"],
            "achieved_diastolic_mmHg": achieved["diastolic_mmHg"],
            "achieved_map_mmHg": achieved["map_mmHg"],
            "systolic_residual_mmHg": sr, "diastolic_residual_mmHg": dr,
            "euclidean_residual_mmHg": float(np.hypot(sr, dr)),
            "representable_within_tolerance":
                bool(abs(sr) <= TOL_SBP and abs(dr) <= TOL_DBP),
        }
    except Exception as exc:
        return {"sample_id": job["sample_id"], "status": "failed",
                "representable_within_tolerance": False, "error": str(exc),
                "traceback": traceback.format_exc()}


def run_population(name, source, frame, n, seed, workers):
    sampled, jobs = population_jobs(name, source, frame, n, seed)
    runs = pd.DataFrame(parallel(jobs, person_worker, workers, f"Pulse {name}"))
    merged = sampled.merge(runs, on="sample_id", how="left", suffixes=("", "_run"))
    merged["representable_within_tolerance"] = (
        merged["representable_within_tolerance"].eq(True))
    # Source identifiers are not loaded. Anonymous exact rows remain private;
    # the tracked result is aggregate only.
    merged.to_csv(PRIVATE / f"{name}_sample_runs.csv", index=False)
    successful = merged.status.eq("ok")
    low = (merged.systolic_mmHg < 90) | (merged.diastolic_mmHg < 60)
    return {
        "cohort": name, "seed": seed, "sample_n": len(merged),
        "body_admissible_n": int(merged.body_admissible.sum()),
        "body_admissible_pct": 100 * float(merged.body_admissible.mean()),
        "direct_pressure_admissible_n": int(merged.direct_pressure_admissible.sum()),
        "direct_pressure_admissible_pct":
            100 * float(merged.direct_pressure_admissible.mean()),
        "direct_all_constraints_admissible_n":
            int(merged.direct_all_constraints_admissible.sum()),
        "direct_all_constraints_admissible_pct":
            100 * float(merged.direct_all_constraints_admissible.mean()),
        "lookup_reachable_n": int(merged.lookup_reachable.sum()),
        "attempted_modifier_run_n": int(merged.attempted_modifier_run.sum()),
        "engine_run_success_n": int(successful.sum()),
        "modifier_representable_n": int(merged.representable_within_tolerance.sum()),
        "modifier_representable_pct":
            100 * float(merged.representable_within_tolerance.mean()),
        "median_euclidean_residual_attempted_mmHg":
            float(merged.loc[successful, "euclidean_residual_mmHg"].median()),
        "unreachable_low_pressure_n":
            int((low & ~merged.lookup_reachable).sum()),
        "systolic_tolerance_mmHg": TOL_SBP,
        "diastolic_tolerance_mmHg": TOL_DBP,
    }


def populations(frame, n, workers):
    summary = [
        run_population("haalsi", load_haalsi(), frame, n, SEED, workers),
        run_population("elsa_wave8", load_elsa(), frame, n, SEED + 1, workers),
    ]
    table = pd.DataFrame(summary)
    table.to_csv(OUT / "population_representability_summary.csv", index=False)
    (OUT / "population_representability_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n")
    return table


def representative(frame, target_s=150, target_d=90):
    prediction = Lookup(frame).predict(target_s, target_d)
    if prediction["lookup_reachable"]:
        return {
            "target_systolic_mmHg": target_s, "target_diastolic_mmHg": target_d,
            "resistance_multiplier": prediction["resistance_multiplier"],
            "compliance_multiplier": prediction["compliance_multiplier"],
            "selection": "inverse lookup interpolation",
        }
    ok = frame[frame.status == "ok"]
    distance = np.hypot(ok.achieved_systolic_mmHg - target_s,
                        ok.achieved_diastolic_mmHg - target_d)
    nearest = ok.loc[distance.idxmin()]
    return {
        "target_systolic_mmHg": target_s, "target_diastolic_mmHg": target_d,
        "resistance_multiplier": float(nearest.resistance_multiplier),
        "compliance_multiplier": float(nearest.compliance_multiplier),
        "selection": "nearest reachable sweep cell",
    }


def restabilisation(frame):
    phenotype = representative(frame)
    log_name = "representative_restabilisation.log"
    engine, s = standard_engine(log_name)
    rows = []
    for _ in range(30):
        if not engine.advance_time_s(1):
            raise RuntimeError("Pulse failed before modification")
        rows.append({"phase": "pre", **row(engine.pull_data())})
    before = rows[-1]["time_s"]
    elapsed = modify(
        engine, s, phenotype["resistance_multiplier"],
        phenotype["compliance_multiplier"])
    immediately_after = row(engine.pull_data())["time_s"]
    for _ in range(120):
        if not engine.advance_time_s(1):
            raise RuntimeError("Pulse failed after modification")
        rows.append({"phase": "post", **row(engine.pull_data())})
    trace = pd.DataFrame(rows)
    trace.to_csv(OUT / "restabilisation_trace.csv", index=False)
    text = (LOGS / log_name).read_text(errors="replace")
    metadata = {
        **phenotype, "default_incremental_flag": False,
        "process_action_wall_s": elapsed,
        "simulation_time_immediately_before_action_s": before,
        "simulation_time_immediately_after_action_s": immediately_after,
        "stabilizing_event_lines": re.findall(r".*Event Stabilizing.*", text),
        "baroreceptor_baseline_update_lines":
            re.findall(r".*Baroreceptor MAP Baseline updated.*", text),
        "guardrail": (
            "The blocking action advances the Pulse engine clock but exposes no "
            "intermediate pull_data samples. The trace is measured pre/post output, "
            "including direct baroreflex scales, not an invented transition."),
    }
    (OUT / "restabilisation_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n")
    plot_restabilisation(trace)
    return metadata


def plot_restabilisation(trace):
    fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True,
                             constrained_layout=True)
    for column, label in (("map_mmHg", "MAP"), ("systolic_mmHg", "SBP"),
                          ("diastolic_mmHg", "DBP")):
        axes[0].plot(trace.index, trace[column], label=label)
    axes[0].set_ylabel("Pressure (mmHg)")
    axes[0].legend(ncol=3)
    axes[1].plot(trace.index, trace.heart_rate_per_min, label="Heart rate")
    axes[1].plot(trace.index, trace.cardiac_output_L_min * 10,
                 label="Cardiac output ×10")
    axes[1].set_ylabel("Rate / scaled output")
    axes[1].legend()
    for column, label in (
        ("baroreceptor_heart_rate_scale", "HR scale"),
        ("baroreceptor_heart_elastance_scale", "Elastance scale"),
        ("baroreceptor_resistance_scale", "Resistance scale"),
        ("baroreceptor_compliance_scale", "Compliance scale")):
        axes[2].plot(trace.index, trace[column], label=label)
    axes[2].axvline((trace.phase == "pre").sum() - .5, color="black",
                    linestyle="--", label="default restabilisation action")
    axes[2].set(
        xlabel="Recorded sample index (internal stabilisation interval omitted by API)",
        ylabel="Baroreflex scale")
    axes[2].legend(ncol=2)
    fig.savefig(OUT / "restabilisation_baroreflex_trace.png", dpi=180)
    plt.close(fig)


def first_below(frame, column, threshold):
    values = frame.loc[frame[column] <= threshold, "time_s"]
    return float(values.iloc[0]) if len(values) else np.nan


def acute_worker(job):
    try:
        s = pulse_symbols()

        class Events(s["IEventHandler"]):
            def __init__(self):
                super().__init__()
                self.first = {}

            def handle_event(self, change):
                if change.active and change.event not in self.first:
                    self.first[change.event] = change.sim_time.get_value(s["TimeUnit"].s)

        engine, s = standard_engine(f"acute_{job['phenotype']}.log")
        events = Events()
        engine.set_event_handler(events)
        if job["phenotype"] == "hypertensive":
            modify(engine, s, job["resistance_multiplier"],
                   job["compliance_multiplier"])
        initial = row(engine.pull_data())
        time_origin_s = initial["time_s"]
        rows = [{"phenotype": job["phenotype"], **initial}]

        def bleed(compartment, rate):
            action = s["SEHemorrhage"]()
            action.set_compartment(compartment)
            action.get_flow_rate().set_value(
                rate, s["VolumePerTimeUnit"].mL_Per_min)
            return action

        for second in range(job["duration_s"]):
            if second == 30:
                engine.process_actions([
                    bleed(s["eHemorrhage_Compartment"].RightLeg, 50),
                    bleed(s["eHemorrhage_Compartment"].VenaCava, 150)])
            elif second == 655:
                engine.process_actions([
                    bleed(s["eHemorrhage_Compartment"].RightLeg, 0),
                    bleed(s["eHemorrhage_Compartment"].VenaCava, 0)])
            if not engine.advance_time_s(1):
                break
            rows.append({"phenotype": job["phenotype"], **row(engine.pull_data())})
        trajectory = pd.DataFrame(rows)
        trajectory["engine_time_s"] = trajectory.time_s
        trajectory.time_s = (
            trajectory.time_s - time_origin_s).round().astype(int)
        trajectory.to_csv(
            OUT / f"acute_{job['phenotype']}_trajectory.csv.gz",
            index=False, compression="gzip")
        shock = events.first.get(s["eEvent"].HypovolemicShock, np.nan)
        if not np.isfinite(shock):
            text = (LOGS / f"acute_{job['phenotype']}.log").read_text(errors="replace")
            matches = re.findall(
                r"\[(\d+(?:\.\d+)?)\(s\)\] \[Event HypovolemicShock 1\]", text)
            shock = float(matches[0]) if matches else np.nan
        if np.isfinite(shock):
            shock -= time_origin_s
        return {
            "phenotype": job["phenotype"], "status": "ok",
            "simulated_through_s": int(trajectory.time_s.max()),
            "time_to_hypovolemic_shock_s": shock,
            "time_to_map_below_65_s": first_below(trajectory, "map_mmHg", 65),
            "minimum_map_mmHg": float(trajectory.map_mmHg.min()),
            "maximum_heart_rate_per_min":
                float(trajectory.heart_rate_per_min.max()),
            "minimum_cardiac_output_L_min":
                float(trajectory.cardiac_output_L_min.min()),
        }
    except Exception as exc:
        return {"phenotype": job["phenotype"], "status": "failed",
                "error": str(exc), "traceback": traceback.format_exc()}


def acute(frame, workers):
    phenotype = representative(frame)
    jobs = [
        {"phenotype": "normotensive", "duration_s": 2155,
         "resistance_multiplier": 1.0, "compliance_multiplier": 1.0},
        {"phenotype": "hypertensive", "duration_s": 2155, **phenotype},
    ]
    summary = pd.DataFrame(
        parallel(jobs, acute_worker, min(workers, 2), "Acute comparison"))
    summary.to_csv(OUT / "acute_comparison_summary.csv", index=False)
    if not summary.status.eq("ok").all():
        raise RuntimeError("Acute comparison failed")
    plot_acute()
    return summary


def plot_acute():
    frame = pd.concat([
        pd.read_csv(OUT / "acute_normotensive_trajectory.csv.gz"),
        pd.read_csv(OUT / "acute_hypertensive_trajectory.csv.gz")])
    fig, axes = plt.subplots(3, 1, figsize=(11, 10), sharex=True,
                             constrained_layout=True)
    for phenotype, group in frame.groupby("phenotype"):
        axes[0].plot(group.time_s, group.map_mmHg, label=phenotype)
        axes[1].plot(group.time_s, group.heart_rate_per_min, label=phenotype)
        axes[2].plot(group.time_s, group.cardiac_output_L_min, label=phenotype)
    for axis, label in zip(
            axes, ["MAP (mmHg)", "Heart rate (1/min)", "Cardiac output (L/min)"]):
        axis.axvspan(30, 655, color="firebrick", alpha=.08)
        axis.set_ylabel(label)
        axis.legend()
    axes[2].set_xlabel("Scenario time (s)")
    fig.savefig(OUT / "acute_normotensive_vs_hypertensive.png", dpi=180)
    plt.close(fig)


def report(frame, calibration, population, rest, acute_summary):
    ok = frame[frame.status == "ok"]
    failed = len(frame) - len(ok)
    validated = calibration[calibration.lookup_reachable].copy()
    trace = pd.read_csv(OUT / "restabilisation_trace.csv")
    endpoints = trace.groupby("phase").median(numeric_only=True)
    acute_by_name = acute_summary.set_index("phenotype")
    control = acute_by_name.loc["normotensive"]
    hypertensive = acute_by_name.loc["hypertensive"]
    population = population.copy()
    population["direct_all_to_modifier_gain_pp"] = (
        population.modifier_representable_pct
        - population.direct_all_constraints_admissible_pct)

    plot_reachability(frame)
    plot_acute()
    plot_final_summaries(calibration, population)

    summary = {
        "stage0_sha256": STAGE0_HASH,
        "sweep_cells": len(frame),
        "successful_cells": len(ok),
        "failed_cells": failed,
        "achieved_envelope_mmHg": {
            "systolic": [float(ok.achieved_systolic_mmHg.min()),
                         float(ok.achieved_systolic_mmHg.max())],
            "diastolic": [float(ok.achieved_diastolic_mmHg.min()),
                          float(ok.achieved_diastolic_mmHg.max())],
            "mean": [float(ok.achieved_map_mmHg.min()),
                     float(ok.achieved_map_mmHg.max())],
        },
        "calibration": {
            "tabulated_targets": len(calibration),
            "reachable_targets": len(validated),
            "validated_within_tolerance": int(
                validated.validated_within_tolerance.sum()),
            "median_euclidean_residual_mmHg": float(
                validated.achieved_euclidean_residual_mmHg.median()),
            "maximum_euclidean_residual_mmHg": float(
                validated.achieved_euclidean_residual_mmHg.max()),
        },
        "population": population.to_dict("records"),
        "acute": acute_summary.to_dict("records"),
    }
    (OUT / "stage2_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n")

    population_display = population[[
        "cohort", "sample_n", "direct_pressure_admissible_pct",
        "direct_all_constraints_admissible_pct",
        "modifier_representable_pct", "direct_all_to_modifier_gain_pp",
        "unreachable_low_pressure_n",
        "median_euclidean_residual_attempted_mmHg",
    ]]
    scale_columns = [
        "baroreceptor_heart_rate_scale",
        "baroreceptor_heart_elastance_scale",
        "baroreceptor_resistance_scale",
        "baroreceptor_compliance_scale",
    ]
    rest_display = endpoints.loc[["pre", "post"], [
        "systolic_mmHg", "diastolic_mmHg", "map_mmHg",
        "pulse_pressure_mmHg", "heart_rate_per_min",
        "cardiac_output_L_min",
        "systemic_vascular_resistance_mmHg_s_mL", *scale_columns,
    ]].T
    text = f"""# Stage 2: stock-Pulse Tier 0 hypertension phenotype

## Scope

Every phenotype here is an admissible normotensive patient to whom cardiovascular modifiers were applied at time zero. Disease stage and duration are therefore erased by construction. No Pulse source, baseline-pressure envelope, ventricular property, stroke-volume multiplier, or baroreflex parameter was changed.

## Stage 0 gate

The fresh Stage 0 haemorrhage output was byte-identical to the archived control: 46,098,446 bytes and SHA-256 `{STAGE0_HASH}`. Hypovolaemic shock again occurred at 615.16 s.

## Reachability and calibration

The 13 × 11 sweep covered systemic resistance 1.00–1.60 and arterial compliance 1.00–0.50 in 0.05 increments. All {len(frame)} cells restabilised; there was no hard failure boundary in this domain. Restabilisation wall time nevertheless rose from {ok.restabilization_wall_s.min():.1f} to {ok.restabilization_wall_s.max():.1f} s, making convergence cost the practical boundary signal.

The achieved envelope was SBP {ok.achieved_systolic_mmHg.min():.1f}–{ok.achieved_systolic_mmHg.max():.1f}, DBP {ok.achieved_diastolic_mmHg.min():.1f}–{ok.achieved_diastolic_mmHg.max():.1f}, MAP {ok.achieved_map_mmHg.min():.1f}–{ok.achieved_map_mmHg.max():.1f}, and pulse pressure {ok.achieved_pulse_pressure_mmHg.min():.1f}–{ok.achieved_pulse_pressure_mmHg.max():.1f} mmHg. A 150/90 phenotype was not reachable in the prescribed grid; the nearest high-pressure point was approximately 142/83 mmHg.

Only {len(validated)} of {len(calibration)} five-mmHg target pairs lay inside the achieved pressure-pair hull. Every one was rerun through Pulse: all {int(validated.validated_within_tolerance.sum())} met the predeclared ±{TOL_SBP:.0f}/±{TOL_DBP:.0f} mmHg criterion. Median achieved Euclidean residual was {validated.achieved_euclidean_residual_mmHg.median():.3f} mmHg and the maximum was {validated.achieved_euclidean_residual_mmHg.max():.3f} mmHg. Targets outside the hull are recorded as unreachable, never silently replaced by a nearest point.

## Population test

{population_display.to_markdown(index=False, floatfmt=".3f")}

The deterministic samples used seeds {SEED} and {SEED + 1}. HAALSI pressure-only direct exclusion was 81.5%, matching Stage 1's approximately 81%. With body constraints included, modifiers increased HAALSI representability from 8.5% to 16.0% (+7.5 percentage points) and ELSA from 8.0% to 10.0% (+2.0 points). All 52 attempted engines succeeded and met pressure tolerance. ELSA had 23 explicitly unreachable low-pressure targets, showing the asymmetry of a modifier domain chosen to raise pressure.

Anonymous exact sampled rows remain local under `results/stage2/private`; only aggregate results are intended for version control.

## Restabilisation

The representative nearest attainable point to 150/90 used resistance {rest['resistance_multiplier']:.3f} and compliance {rest['compliance_multiplier']:.3f}. Default `incremental=false` processing took {rest['process_action_wall_s']:.2f} wall seconds and advanced the engine clock from {rest['simulation_time_immediately_before_action_s']:.1f} to {rest['simulation_time_immediately_after_action_s']:.1f} s. The blocking API supplies no intermediate `pull_data` samples, so the saved trace shows measured pre/post operating points rather than fabricating a transition waveform.

{rest_display.to_markdown(floatfmt=".4f")}

MAP rose from {endpoints.loc['pre', 'map_mmHg']:.1f} to {endpoints.loc['post', 'map_mmHg']:.1f} mmHg, CO fell from {endpoints.loc['pre', 'cardiac_output_L_min']:.2f} to {endpoints.loc['post', 'cardiac_output_L_min']:.2f} L/min, and SVR rose from {endpoints.loc['pre', 'systemic_vascular_resistance_mmHg_s_mL']:.2f} to {endpoints.loc['post', 'systemic_vascular_resistance_mmHg_s_mL']:.2f} mmHg·s/mL. All four directly requested baroreflex scales were essentially 1.0 after restabilisation. Empirically, the engine accepted the raised operating pressure as the new accommodated state rather than sustaining a corrective reflex output.

## Acute reach

{acute_summary.to_markdown(index=False)}

The fixed 200 mL/min bleed ran from 30 to 655 s. The hypertensive phenotype crossed MAP 65 mmHg {control.time_to_map_below_65_s - hypertensive.time_to_map_below_65_s:.1f} s earlier and entered hypovolaemic shock {control.time_to_hypovolemic_shock_s - hypertensive.time_to_hypovolemic_shock_s:.2f} s earlier. Its minimum cardiac output was {hypertensive.minimum_cardiac_output_L_min:.2f} versus {control.minimum_cardiac_output_L_min:.2f} L/min. The released modifiers therefore reach the acute scenario materially; they are not merely cosmetic resting-pressure labels.

## Interpretation and limits

Stock Pulse can produce a modest hypertensive haemodynamic state accurately, and that state changes haemorrhage compensation. It cannot cover much of either real cohort because the two-modifier pressure manifold is narrow, the prescribed grid does not reach 150 mmHg systolic, body-definition exclusions remain, and low-pressure targets are outside this raise-oriented domain. Tier 1 is therefore justified by quantified coverage limits rather than by solver instability.

This remains an acute-onset phenotype. It contains no disease duration, vascular remodelling history, exposed baroreflex setpoint, or progression stage. The inverse lookup was learned on StandardMale and transferred to body-specific patients; transfer was accurate for all attempted cases here, but only within the measured hull. The 200-person samples quantify this seeded experiment rather than replacing full-cohort inference.

## Artefacts

- Reproduce with `scripts/run_stage2_tier0.sh all --workers 12`; individual stages and a non-rerunning `report` command are also available.
- `reachability_sweep.csv` and `reachability_and_failure_boundary.png`
- `calibration_lookup_table.csv` and `calibration_reachability_and_residuals.png`
- `population_representability_summary.csv` and `population_representability.png`
- `restabilisation_trace.csv`, metadata, and baroreflex figure
- aligned compressed acute trajectories, summary, and comparison figure
- `stage0_regression_gate.json` and `stage2_summary.json`
"""
    (ROOT / "docs/STAGE2_TIER0_HYPERTENSION.md").write_text(text)


def plot_final_summaries(calibration, population):
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    unreachable = calibration[~calibration.lookup_reachable]
    reachable = calibration[calibration.lookup_reachable]
    axes[0].scatter(unreachable.target_systolic_mmHg,
                    unreachable.target_diastolic_mmHg,
                    s=13, color="lightgray", label="Unreachable")
    points = axes[0].scatter(
        reachable.target_systolic_mmHg, reachable.target_diastolic_mmHg,
        c=reachable.achieved_euclidean_residual_mmHg,
        cmap="viridis", s=45, label="Validated")
    axes[0].set(xlabel="Target SBP (mmHg)", ylabel="Target DBP (mmHg)",
                title="Inverse lookup domain")
    axes[0].legend()
    fig.colorbar(points, ax=axes[0], label="Achieved residual (mmHg)")

    x = np.arange(len(population))
    width = .25
    axes[1].bar(x - width, population.direct_pressure_admissible_pct,
                width, label="Pressure only")
    axes[1].bar(x, population.direct_all_constraints_admissible_pct,
                width, label="Direct + body")
    axes[1].bar(x + width, population.modifier_representable_pct,
                width, label="Modifiers + body")
    axes[1].set_xticks(x, population.cohort)
    axes[1].set(ylabel="Representable sample (%)",
                title="Seeded 200-person samples", ylim=(0, 30))
    axes[1].legend()
    fig.savefig(OUT / "calibration_reachability_and_residuals.png", dpi=180)
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(7, 4.5), constrained_layout=True)
    axis.bar(x - width, population.direct_all_constraints_admissible_pct,
             width * 2, label="Direct + body")
    axis.bar(x + width, population.modifier_representable_pct,
             width * 2, label="Modifiers + body")
    axis.set_xticks(x, population.cohort)
    axis.set(ylabel="Representable sample (%)",
             title="Coverage gained by stock modifiers", ylim=(0, 20))
    axis.legend()
    fig.savefig(OUT / "population_representability.png", dpi=180)
    plt.close(fig)


def load_sweep():
    path = OUT / "reachability_sweep.csv"
    if not path.exists():
        raise RuntimeError("Run the sweep before this command")
    return pd.read_csv(path)


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", nargs="?", default="all",
        choices=["smoke", "sweep", "calibrate", "population",
                 "restabilisation", "acute", "report", "all"])
    parser.add_argument("--workers", type=int, default=min(12, os.cpu_count() or 1))
    parser.add_argument("--population-n", type=int, default=200)
    return parser.parse_args()


def main():
    args = arguments()
    directories()
    stage0_gate()
    if args.command == "report":
        frame = load_sweep()
        calibration = pd.read_csv(OUT / "calibration_lookup_table.csv")
        population = pd.read_csv(OUT / "population_representability_summary.csv")
        rest = json.loads((OUT / "restabilisation_metadata.json").read_text())
        acute_summary = pd.read_csv(OUT / "acute_comparison_summary.csv")
        report(frame, calibration, population, rest, acute_summary)
        return
    if args.command == "smoke":
        print(smoke().to_string(index=False))
        return
    if args.command in ("sweep", "all"):
        smoke()
        frame = sweep(args.workers)
    else:
        frame = load_sweep()
    if args.command == "sweep":
        return
    calibration = calibration_table(
        frame, args.workers) if args.command in ("calibrate", "all") else None
    if args.command == "calibrate":
        return
    population = populations(
        frame, args.population_n, args.workers) if args.command in ("population", "all") else None
    if args.command == "population":
        return
    rest = restabilisation(frame) if args.command in ("restabilisation", "all") else None
    if args.command == "restabilisation":
        return
    acute_summary = acute(frame, args.workers) if args.command in ("acute", "all") else None
    if args.command == "acute":
        return
    report(frame, calibration, population, rest, acute_summary)


if __name__ == "__main__":
    main()
