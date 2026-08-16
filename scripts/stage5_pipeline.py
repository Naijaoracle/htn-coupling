#!/usr/bin/env python3
"""Prepare, run, and analyse Stage 5 Pulse-to-openBF experiments."""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import os
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml
from scipy.signal import find_peaks
from tqdm import tqdm

from bridge_units import mmhg_s_per_ml_to_pa_s_per_m3, pa_to_mmhg
from extract_stage4_pulse_inlet import average_cycles
from prepare_stage4_openbf import equivalent_terminal_resistance

ROOT = Path(__file__).resolve().parents[1]
PULSE = Path(os.environ.get("PULSE_ROOT", "{PULSE_ROOT}"))
OPENBF = Path(os.environ.get("OPENBF_ROOT", "{OPENBF_ROOT}"))
BIN = PULSE / "build/install/bin"
BASE = OPENBF / "models/boileau2015/adan56/adan56.yaml"
OUT = ROOT / "results/stage5"
PROTOCOL = ROOT / "config/stage5_protocol_v1.json"
STATE = ROOT / "results/stage2/private/cache/StandardMale_stage2_baseline.json"
STAGE4 = ROOT / "results/stage4"
STAGE4C = ROOT / "results/stage4_completion"
STAGE0_OPENBF = ROOT / "results/stage0/openbf_adan56"
RUNNER = ROOT / "scripts/run_stage4_openbf.jl"
PA_PER_MMHG = 133.322387415
SITES = ("aortic_arch_I", "external_carotid_R", "internal_carotid_R")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_stage0() -> dict:
    gate = json.loads((ROOT / "results/stage2/stage0_regression_gate.json").read_text())
    if not gate.get("passed"):
        raise RuntimeError("Stage 0 byte-identity gate is not passing")
    current = [sha256(Path(item["path"])) for item in gate["files"]]
    if len(set(current + [gate["expected_sha256"]])) != 1:
        raise RuntimeError("Stage 0 files changed after their recorded gate")
    return gate


def pulse_requests():
    from pulse.cdm.engine import SEDataRequest, SEDataRequestManager
    from pulse.cdm.scalars import (FrequencyUnit, PressureTimePerVolumeUnit,
                                   PressureUnit, VolumePerTimeUnit)
    r = SEDataRequest
    return SEDataRequestManager([
        r.create_liquid_compartment_request("Aorta", "InFlow", VolumePerTimeUnit.mL_Per_s),
        r.create_liquid_compartment_request("Aorta", "Pressure", PressureUnit.mmHg),
        r.create_physiology_request("HeartRate", FrequencyUnit.Per_min),
        r.create_physiology_request("CardiacOutput", VolumePerTimeUnit.L_Per_min),
        r.create_physiology_request("MeanArterialPressure", PressureUnit.mmHg),
        r.create_physiology_request("SystolicArterialPressure", PressureUnit.mmHg),
        r.create_physiology_request("DiastolicArterialPressure", PressureUnit.mmHg),
        r.create_physiology_request("SystemicVascularResistance",
                                    PressureTimePerVolumeUnit.mmHg_s_Per_mL),
    ])


PULSE_COLUMNS = [
    "time_s", "aorta_inflow_mL_s", "aorta_pressure_mmHg",
    "heart_rate_per_min", "cardiac_output_L_min", "map_mmHg",
    "systolic_mmHg", "diastolic_mmHg", "svr_mmHg_s_mL",
]


def extract_one(name: str, spec: dict) -> dict:
    from pulse.cdm.patient_actions import SECardiovascularMechanicsModification
    from pulse.engine.PulseEngine import PulseEngine

    case_dir = OUT / "pulse" / name
    case_dir.mkdir(parents=True, exist_ok=True)
    engine = PulseEngine(data_root_dir=str(BIN))
    engine.log_to_console(False)
    engine.set_log_filename(str(case_dir / "pulse.log"))
    if not engine.serialize_from_file(str(STATE), pulse_requests()):
        raise RuntimeError(f"Could not load Stage 2 state for {name}")
    r, c = spec["resistance_multiplier"], spec["compliance_multiplier"]
    restabilisation_s = 0.0
    if r != 1.0 or c != 1.0:
        action = SECardiovascularMechanicsModification()
        action.get_modifiers().get_systemic_resistance_multiplier().set_value(r)
        action.get_modifiers().get_arterial_compliance_multiplier().set_value(c)
        started = time.monotonic()
        engine.process_action(action)
        restabilisation_s = time.monotonic() - started
        if not engine.advance_time_s(0.02):
            raise RuntimeError(f"Pulse stopped after modifying {name}")
    rows = []
    for _ in range(1000):
        if not engine.advance_time_s(0.02):
            raise RuntimeError(f"Pulse stopped while sampling {name}")
        rows.append(dict(zip(PULSE_COLUMNS, engine.pull_data().copy())))
    raw = pd.DataFrame(rows)
    raw.to_csv(case_dir / "stable_raw.csv.gz", index=False, compression="gzip")
    time_s, flow, pressure, periods, rmses = average_cycles(raw, 8, 201)
    flow_m3_s = flow * 1e-6
    flow_m3_s[np.abs(flow_m3_s) < 1e-10] = 1e-10
    inlet = case_dir / "aortic_inlet.dat"
    np.savetxt(inlet, np.column_stack([time_s, flow_m3_s]), fmt="%.12g")
    pd.DataFrame({"time_s": time_s, "aorta_inflow_mL_s": flow,
                  "aorta_pressure_mmHg": pressure}).to_csv(
                      case_dir / "representative_cycle.csv", index=False)
    cycle_co = float(np.trapz(flow, time_s) / time_s[-1] * 0.06)
    reported_co = float(raw.cardiac_output_L_min.median())
    result = {
        "phenotype": name, **spec, "status": "ok",
        "restabilisation_wall_s": restabilisation_s,
        "inlet_file": str(inlet), "inlet_sha256": sha256(inlet),
        "cardiac_cycle_length_s": float(time_s[-1]),
        "heart_rate_per_min": float(raw.heart_rate_per_min.median()),
        "systolic_mmHg": float(raw.systolic_mmHg.median()),
        "diastolic_mmHg": float(raw.diastolic_mmHg.median()),
        "map_mmHg": float(raw.map_mmHg.median()),
        "pulse_pressure_mmHg": float(raw.systolic_mmHg.median()-raw.diastolic_mmHg.median()),
        "cardiac_output_L_min": reported_co,
        "cardiac_output_from_inlet_L_min": cycle_co,
        "flow_integral_relative_error": abs(cycle_co-reported_co)/reported_co,
        "systemic_vascular_resistance_mmHg_s_mL": float(raw.svr_mmHg_s_mL.median()),
        "maximum_cycle_flow_rmse_fraction_of_peak": float(np.max(rmses)/np.max(flow)),
        "periodic_endpoint_error_m3_s": float(abs(flow_m3_s[-1]-flow_m3_s[0])),
    }
    if result["flow_integral_relative_error"] > 0.01:
        raise RuntimeError(f"{name} inlet integral differs from CO by >1%")
    (case_dir / "metadata.json").write_text(json.dumps(result, indent=2)+"\n")
    return result


def extract() -> None:
    gate = require_stage0()
    if not STATE.exists():
        raise RuntimeError(f"Missing Stage 2 baseline state: {STATE}")
    protocol = json.loads(PROTOCOL.read_text())
    rows = []
    with tqdm(protocol["phenotypes"].items(), total=4,
              desc="Pulse Stage 5 phenotypes", unit="phenotype") as progress:
        for name, spec in progress:
            progress.set_postfix_str(name)
            rows.append(extract_one(name, spec))
    frame = pd.DataFrame(rows)
    frame.to_csv(OUT / "pulse_phenotypes.csv", index=False)
    maps = frame.set_index("phenotype").map_mmHg
    result = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "stage0_sha256": gate["expected_sha256"],
        "pulse_revision": subprocess.check_output(
            ["git", "-C", str(PULSE), "rev-parse", "HEAD"], text=True).strip(),
        "phenotypes": rows,
        "mechanism_arm_map_difference_mmHg": float(
            abs(maps["resistance_dominant"]-maps["compliance_dominant"])),
        "mean_match_tolerance_mmHg": protocol["mean_match_tolerance_mmHg"],
        "mechanism_arms_mean_matched": bool(
            abs(maps["resistance_dominant"]-maps["compliance_dominant"])
            <= protocol["mean_match_tolerance_mmHg"]),
    }
    (OUT / "pulse_phenotypes.json").write_text(json.dumps(result, indent=2)+"\n")
    print(frame.to_string(index=False))


def write_case(name: str, inlet: Path, resistance_scale: float,
               youngs_scale: float = 1.0, cc_scale: float = 1.0,
               source: str = "pulse") -> dict:
    case_dir = OUT / "configs" / name
    case_dir.mkdir(parents=True, exist_ok=True)
    inlet_out = case_dir / f"{name}_inlet.dat"
    inlet_out.write_bytes(inlet.read_bytes())
    config = yaml.safe_load(BASE.read_text())
    config["project_name"] = name
    config["inlet_file"] = inlet_out.name
    config["solver"]["cycles"] = 15
    for vessel in config["network"]:
        vessel["E"] *= youngs_scale
        if vessel.get("outlet") == "wk3":
            vessel["R1"] *= resistance_scale
            vessel["R2"] *= resistance_scale
            vessel["Cc"] *= cc_scale
    yaml_out = case_dir / f"{name}.yaml"
    yaml_out.write_text(yaml.safe_dump(config, sort_keys=False))
    return {"case": name, "yaml": str(yaml_out), "inlet": str(inlet_out),
            "source": source, "terminal_resistance_scale": resistance_scale,
            "terminal_compliance_scale": cc_scale,
            "wall_youngs_modulus_scale": youngs_scale}


def prepare() -> None:
    require_stage0()
    protocol = json.loads(PROTOCOL.read_text())
    metadata = json.loads((OUT / "pulse_phenotypes.json").read_text())
    by_name = {x["phenotype"]: x for x in metadata["phenotypes"]}
    base_config = yaml.safe_load(BASE.read_text())
    published_r, outlets = equivalent_terminal_resistance(base_config)
    cases = []
    for name, spec in protocol["phenotypes"].items():
        pulse = by_name[name]
        pulse_r = mmhg_s_per_ml_to_pa_s_per_m3(
            pulse["systemic_vascular_resistance_mmHg_s_mL"])
        rscale = pulse_r / published_r
        inlet = Path(pulse["inlet_file"])
        cases.append(write_case(f"{name}_arm1_inlet_only", inlet, rscale,
                                youngs_scale=1.0))
        cases.append(write_case(f"{name}_arm2_matched_stiffening", inlet, rscale,
                                youngs_scale=1.0/spec["compliance_multiplier"]))
    norm = by_name["normotensive"]
    norm_rscale = mmhg_s_per_ml_to_pa_s_per_m3(
        norm["systemic_vascular_resistance_mmHg_s_mL"])/published_r
    norm_inlet = Path(norm["inlet_file"])
    for scale in protocol["attribution"]["stiffness_scales"]:
        cases.append(write_case(f"threshold_E_{scale:.2f}".replace(".", "p"),
                                norm_inlet, norm_rscale, youngs_scale=scale,
                                source="Pulse low-pulsatility threshold"))
    default_inlet = BASE.parent / base_config["inlet_file"]
    cases.append(write_case("default_inlet_E_2p50", default_inlet, 1.0,
                            youngs_scale=2.5,
                            source="ADAN56 default high-pulsatility reference"))
    cases.append(write_case("terminal_only_Cc_0p40", norm_inlet, norm_rscale,
                            cc_scale=0.4, source="ICA terminal diagnostic"))
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "openbf_revision": subprocess.check_output(
            ["git", "-C", str(OPENBF), "rev-parse", "HEAD"], text=True).strip(),
        "base_yaml": str(BASE), "wk3_outlets": outlets,
        "published_parallel_terminal_resistance_pa_s_m3": published_r,
        "mapping": "R1/R2 globally matched to each Pulse SVR; Cc published; Arm 2 E=1/C",
        "cases": cases,
    }
    (OUT / "run_manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    print(f"Prepared {len(cases)} Stage 5 openBF cases")


def run_case(item: dict) -> dict:
    result = OUT / "runs" / item["case"]
    result.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    proc = subprocess.run(
        ["julia", f"--project={ROOT}", str(RUNNER), item["yaml"], str(result)],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (result / "runner.log").write_text(proc.stdout)
    return {"case": item["case"], "returncode": proc.returncode,
            "wall_s": time.monotonic()-started,
            "status": "ok" if proc.returncode == 0 else "failed"}


def run(workers: int) -> None:
    manifest = json.loads((OUT / "run_manifest.json").read_text())
    jobs = manifest["cases"]
    rows = []
    with ProcessPoolExecutor(max_workers=workers,
                             mp_context=mp.get_context("spawn")) as pool:
        futures = {pool.submit(run_case, item): item for item in jobs}
        with tqdm(total=len(futures), desc="openBF Stage 5", unit="case") as progress:
            for future in as_completed(futures):
                row = future.result()
                rows.append(row)
                progress.set_postfix(case=row["case"], status=row["status"])
                progress.update()
    frame = pd.DataFrame(rows).sort_values("case")
    frame.to_csv(OUT / "run_status.csv", index=False)
    if not frame.status.eq("ok").all():
        raise RuntimeError("One or more Stage 5 openBF cases failed")


def trace(directory: Path, vessel: str, field: str) -> tuple[np.ndarray, np.ndarray]:
    data = np.loadtxt(directory / f"{vessel}_{field}.last")
    # The declared overlap site is the proximal aortic root. Carotid reference
    # sites are distal outlets. openBF stores time in column 0 and spatial
    # samples thereafter, so these sites require opposite column selections.
    values = data[:, 1] if vessel == "aortic_arch_I" else data[:, -1]
    return data[:, 0], values


def phase_pressure(directory: Path, vessel: str, points: int = 501) -> tuple[np.ndarray, np.ndarray]:
    t, p = trace(directory, vessel, "P")
    phase = (t-t[0])/(t[-1]-t[0])
    target = np.linspace(0, 1, points)
    return target, np.interp(target, phase, pa_to_mmhg(p))


def aligned_shape_rmse(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    an = (a-a.min())/np.ptp(a)
    bn = (b-b.min())/np.ptp(b)
    au, bu = an[:-1], bn[:-1]
    choices = []
    for shift in range(-25, 26):
        choices.append((float(np.sqrt(np.mean((au-np.roll(bu, shift))**2))), shift))
    value, shift = min(choices)
    return value, shift/len(au)


def waveform_metrics(directory: Path, case: str, vessel: str) -> dict:
    phase, pressure = phase_pressure(directory, vessel)
    t, _ = trace(directory, vessel, "P")
    primary = int(np.argmax(pressure[:-1]))
    prominence = max(0.02*np.ptp(pressure), 0.05)
    minima, _ = find_peaks(-pressure[:-1], prominence=prominence/2, distance=15)
    peaks, _ = find_peaks(pressure[:-1], prominence=prominence, distance=15)
    later_min = minima[minima > primary]
    secondary_index = None
    minimum_index = None
    if len(later_min):
        minimum_index = int(later_min[0])
        later_peak = peaks[peaks > minimum_index]
        if len(later_peak):
            secondary_index = int(later_peak[0])
    pp = float(np.ptp(pressure))
    ap = (float(pressure[secondary_index]-pressure[minimum_index])
          if secondary_index is not None else np.nan)
    conv = (directory / f"{case}.conv").read_text().splitlines()
    return {
        "case": case, "vessel": vessel,
        "systolic_mmHg": float(pressure.max()),
        "diastolic_mmHg": float(pressure.min()),
        "mean_mmHg": float(np.trapz(pressure, phase)),
        "pulse_pressure_mmHg": pp,
        "time_to_peak_phase": float(phase[primary]),
        "reflected_wave_present": secondary_index is not None,
        "reflected_wave_phase": (float(phase[secondary_index])
                                 if secondary_index is not None else np.nan),
        "augmentation_pressure_mmHg": ap,
        "augmentation_index_pct": 100*ap/pp if np.isfinite(ap) else np.nan,
        "openbf_converged": conv[0].strip().lower() == "true",
        "openbf_cycles": int(conv[1]),
        "openbf_solver_elapsed_s": float(conv[2]),
    }


def scalar_and_shape_effect(case_dir: Path, base_dir: Path, vessel: str) -> dict:
    _, case = phase_pressure(case_dir, vessel)
    _, base = phase_pressure(base_dir, vessel)
    rmse, shift = aligned_shape_rmse(base, case)
    return {"phase_aligned_normalised_shape_rmse": rmse,
            "optimal_phase_shift": shift}


def stage4_noise() -> pd.DataFrame:
    baseline = STAGE4 / "runs/stage4_scaled"
    cases = ["sensitivity_flow_low", "sensitivity_flow_high",
             "sensitivity_period_low", "sensitivity_period_high"]
    rows = []
    for vessel in SITES:
        base_m = waveform_metrics(baseline, "stage4_scaled", vessel)
        values = []
        for case in cases:
            directory = STAGE4C / "runs" / case
            m = waveform_metrics(directory, case, vessel)
            shape = scalar_and_shape_effect(directory, baseline, vessel)
            values.append({**m, **shape})
        for metric in ("systolic_mmHg", "diastolic_mmHg", "mean_mmHg",
                       "pulse_pressure_mmHg", "time_to_peak_phase",
                       "reflected_wave_phase", "augmentation_pressure_mmHg",
                       "augmentation_index_pct"):
            deltas = [abs(x[metric]-base_m[metric]) for x in values
                      if np.isfinite(x[metric]) and np.isfinite(base_m[metric])]
            rows.append({"vessel": vessel, "metric": metric,
                         "noise_floor": max(deltas) if deltas else np.nan,
                         "metric_class": "amplitude" if metric in
                         ("systolic_mmHg", "diastolic_mmHg", "mean_mmHg",
                          "pulse_pressure_mmHg", "augmentation_pressure_mmHg")
                         else "shape"})
        rows.append({"vessel": vessel,
                     "metric": "phase_aligned_normalised_shape_rmse",
                     "noise_floor": max(x["phase_aligned_normalised_shape_rmse"]
                                        for x in values),
                     "metric_class": "shape"})
    return pd.DataFrame(rows)


def analyse() -> None:
    protocol = json.loads(PROTOCOL.read_text())
    manifest = json.loads((OUT / "run_manifest.json").read_text())
    by_case = {x["case"]: x for x in manifest["cases"]}
    metrics_rows = []
    for item in manifest["cases"]:
        directory = OUT / "runs" / item["case"]
        for vessel in SITES:
            metrics_rows.append({**waveform_metrics(directory, item["case"], vessel),
                                 **{k: item[k] for k in
                                    ("source", "terminal_resistance_scale",
                                     "terminal_compliance_scale",
                                     "wall_youngs_modulus_scale")}})
    metrics = pd.DataFrame(metrics_rows)
    metrics.to_csv(OUT / "waveform_metrics.csv", index=False)

    noise = stage4_noise()
    noise.to_csv(OUT / "metric_noise_floors.csv", index=False)
    baseline_case = "normotensive_arm1_inlet_only"
    baseline_dir = OUT / "runs" / baseline_case
    baseline = metrics[metrics.case == baseline_case].set_index("vessel")
    pass_ratio = protocol["attribution"]["pass_ratio"]
    rows = []
    measured = ["systolic_mmHg", "diastolic_mmHg", "mean_mmHg",
                "pulse_pressure_mmHg", "time_to_peak_phase",
                "reflected_wave_phase", "augmentation_pressure_mmHg",
                "augmentation_index_pct"]
    primary_cases = [x["case"] for x in manifest["cases"]
                     if "_arm" in x["case"]]
    for case in primary_cases:
        directory = OUT / "runs" / case
        case_metrics = metrics[metrics.case == case].set_index("vessel")
        for vessel in SITES:
            for metric in measured:
                effect = abs(case_metrics.loc[vessel, metric]-baseline.loc[vessel, metric])
                floor_row = noise[(noise.vessel == vessel)&(noise.metric == metric)].iloc[0]
                floor = floor_row.noise_floor
                ratio = effect/floor if np.isfinite(floor) and floor > 0 else np.nan
                rows.append({"case": case, "vessel": vessel, "metric": metric,
                             "metric_class": floor_row.metric_class,
                             "effect_vs_normotensive": effect,
                             "noise_floor": floor, "attribution_ratio": ratio,
                             "passes_1p25x_floor": bool(np.isfinite(ratio) and ratio >= pass_ratio)})
            shape = scalar_and_shape_effect(directory, baseline_dir, vessel)
            floor = noise[(noise.vessel == vessel)&
                          (noise.metric == "phase_aligned_normalised_shape_rmse")].noise_floor.iloc[0]
            ratio = shape["phase_aligned_normalised_shape_rmse"]/floor
            rows.append({"case": case, "vessel": vessel,
                         "metric": "phase_aligned_normalised_shape_rmse",
                         "metric_class": "shape",
                         "effect_vs_normotensive": shape["phase_aligned_normalised_shape_rmse"],
                         "noise_floor": floor, "attribution_ratio": ratio,
                         "passes_1p25x_floor": bool(ratio >= pass_ratio)})
    attribution = pd.DataFrame(rows)
    attribution.to_csv(OUT / "attribution_table.csv", index=False)

    threshold_rows = []
    for scale in protocol["attribution"]["stiffness_scales"]:
        case = f"threshold_E_{scale:.2f}".replace(".", "p")
        directory = OUT / "runs" / case
        for vessel in ("external_carotid_R", "internal_carotid_R"):
            shape = scalar_and_shape_effect(directory, baseline_dir, vessel)
            floor = noise[(noise.vessel == vessel)&
                          (noise.metric == "phase_aligned_normalised_shape_rmse")].noise_floor.iloc[0]
            ratio = shape["phase_aligned_normalised_shape_rmse"]/floor
            threshold_rows.append({"youngs_modulus_scale": scale, "vessel": vessel,
                                   **shape, "shape_noise_floor": floor,
                                   "attribution_ratio": ratio,
                                   "passes_1p25x_floor": ratio >= pass_ratio})
    thresholds = pd.DataFrame(threshold_rows)
    thresholds.to_csv(OUT / "stiffness_shape_threshold.csv", index=False)

    low_rows = []
    comparisons = [
        ("Pulse low-pulsatility", baseline_dir, OUT/"runs/threshold_E_2p50"),
        ("ADAN56 default high-pulsatility", STAGE0_OPENBF,
         OUT/"runs/default_inlet_E_2p50"),
    ]
    for source, base_dir, stiff_dir in comparisons:
        base_case = baseline_case if source.startswith("Pulse") else "adan56"
        stiff_case = "threshold_E_2p50" if source.startswith("Pulse") else "default_inlet_E_2p50"
        for vessel in SITES:
            bm = waveform_metrics(base_dir, base_case, vessel)
            sm = waveform_metrics(stiff_dir, stiff_case, vessel)
            shape = scalar_and_shape_effect(stiff_dir, base_dir, vessel)
            low_rows.append({"source": source, "vessel": vessel,
                             "baseline_pp_mmHg": bm["pulse_pressure_mmHg"],
                             "stiff_pp_mmHg": sm["pulse_pressure_mmHg"],
                             "delta_pp_mmHg": sm["pulse_pressure_mmHg"]-bm["pulse_pressure_mmHg"],
                             "baseline_augmentation_index_pct": bm["augmentation_index_pct"],
                             "stiff_augmentation_index_pct": sm["augmentation_index_pct"],
                             **shape})
    low = pd.DataFrame(low_rows)
    low.to_csv(OUT / "low_pulsatility_check.csv", index=False)

    config = yaml.safe_load(BASE.read_text())
    outlets = {v["label"]: v for v in config["network"]
               if v["label"] in ("external_carotid_R", "internal_carotid_R")}
    terminal_case = metrics[metrics.case == "terminal_only_Cc_0p40"].set_index("vessel")
    stiff_case = metrics[metrics.case == "threshold_E_2p50"].set_index("vessel")
    diagnostic = []
    for vessel in ("external_carotid_R", "internal_carotid_R"):
        v = outlets[vessel]
        diagnostic.append({"vessel": vessel, "length_m": v["L"],
                           "radius_m": v["Rd"], "R1_pa_s_m3": v["R1"],
                           "R2_pa_s_m3": v["R2"], "Cc_m3_pa": v["Cc"],
                           "baseline_pp_mmHg": baseline.loc[vessel, "pulse_pressure_mmHg"],
                           "delta_pp_E_2p5_mmHg": stiff_case.loc[vessel, "pulse_pressure_mmHg"]-baseline.loc[vessel, "pulse_pressure_mmHg"],
                           "delta_pp_Cc_0p4_mmHg": terminal_case.loc[vessel, "pulse_pressure_mmHg"]-baseline.loc[vessel, "pulse_pressure_mmHg"]})
    pd.DataFrame(diagnostic).to_csv(OUT / "ica_eca_terminal_diagnostic.csv", index=False)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
    for axis, vessel in zip(axes, ("external_carotid_R", "internal_carotid_R")):
        for case, label in ((baseline_case, "Normotensive"),
                            ("resistance_dominant_arm2_matched_stiffening", "Resistance only"),
                            ("compliance_dominant_arm2_matched_stiffening", "Compliance only"),
                            ("combined_arm2_matched_stiffening", "Combined")):
            phase, pressure = phase_pressure(OUT/"runs"/case, vessel)
            axis.plot(phase, (pressure-pressure.min())/np.ptp(pressure), label=label)
        axis.set(title=vessel, xlabel="Cycle phase", ylabel="Normalised pressure")
        axis.legend(fontsize=8)
    fig.savefig(OUT / "carotid_normalised_mechanism_comparison.png", dpi=180)
    plt.close(fig)

    smallest = {}
    for vessel, group in thresholds.groupby("vessel"):
        passing = group[group.passes_1p25x_floor]
        smallest[vessel] = (float(passing.youngs_modulus_scale.min())
                            if len(passing) else None)
    pulse_low = low[low.source.str.startswith("Pulse")].set_index("vessel")
    default_high = low[low.source.str.startswith("ADAN")].set_index("vessel")
    attenuation = {}
    for vessel in SITES:
        high = abs(default_high.loc[vessel, "delta_pp_mmHg"])
        depressed = abs(pulse_low.loc[vessel, "delta_pp_mmHg"])
        attenuation[vessel] = {
            "pulse_to_default_delta_pp_ratio": depressed/high if high else None,
            "attenuation_pct": 100*(1-depressed/high) if high else None,
            "pulse_to_default_shape_effect_ratio":
                pulse_low.loc[vessel, "phase_aligned_normalised_shape_rmse"]/
                default_high.loc[vessel, "phase_aligned_normalised_shape_rmse"],
        }
    pulse_meta = json.loads((OUT/"pulse_phenotypes.json").read_text())
    summary = {
        "stage0_sha256": pulse_meta["stage0_sha256"],
        "all_openbf_runs_converged": bool(metrics.openbf_converged.all()),
        "mechanism_arms_mean_matched": pulse_meta["mechanism_arms_mean_matched"],
        "mechanism_arm_map_difference_mmHg": pulse_meta["mechanism_arm_map_difference_mmHg"],
        "smallest_tested_E_scale_clearing_shape_floor": smallest,
        "low_pulsatility_attenuation": attenuation,
        "attribution_pass_ratio": pass_ratio,
        "augmentation_definition": "secondary post-primary peak minus intervening minimum; AIx=100*AP/PP",
    }
    (OUT/"coupled_summary.json").write_text(json.dumps(summary, indent=2)+"\n")
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("extract", "prepare", "run", "analyse"))
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    {"extract": extract, "prepare": prepare, "analyse": analyse}.get(
        args.mode, lambda: run(args.workers))()


if __name__ == "__main__":
    main()
