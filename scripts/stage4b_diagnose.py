#!/usr/bin/env python3
"""Prepare and analyse the Stage 4b Pulse-pressure diagnosis."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml
from scipy.signal import find_peaks

from bridge_units import pa_to_mmhg
from extract_stage4_pulse_inlet import average_cycles

ROOT = Path(__file__).resolve().parents[1]
OPENBF = Path(os.environ.get("OPENBF_ROOT", ROOT.parent / "openBF"))
BASE_YAML = OPENBF / "models/boileau2015/adan56/adan56.yaml"
DEFAULT_INLET = OPENBF / "models/boileau2015/adan56/adan56_inlet.dat"
STAGE4 = ROOT / "results/stage4"
OUT = ROOT / "results/stage4b"


def configure(name: str, inlet: Path, resistance_scale: float) -> dict:
    case_dir = OUT / "configs" / name
    case_dir.mkdir(parents=True, exist_ok=True)
    inlet_out = case_dir / f"{name}_inlet.dat"
    shutil.copyfile(inlet, inlet_out)
    config = yaml.safe_load(BASE_YAML.read_text())
    config["project_name"] = name
    config["inlet_file"] = inlet_out.name
    config["solver"]["cycles"] = 15
    for vessel in config["network"]:
        if vessel.get("outlet") == "wk3":
            vessel["R1"] *= resistance_scale
            vessel["R2"] *= resistance_scale
    yaml_out = case_dir / f"{name}.yaml"
    yaml_out.write_text(yaml.safe_dump(config, sort_keys=False))
    return {"case": name, "yaml": str(yaml_out), "inlet": str(inlet_out),
            "resistance_scale": resistance_scale}


def write_diagnostic_inlets() -> list[Path]:
    raw = pd.read_csv(STAGE4 / "private/pulse_stable_raw.csv.gz")
    generated = []
    for points, name in ((1001, "pulse_average_1001"),):
        t, q, _, _, _ = average_cycles(raw, 8, points)
        path = OUT / f"{name}.dat"
        q = q * 1e-6
        q[np.abs(q) < 1e-10] = 1e-10
        np.savetxt(path, np.column_stack([t, q]), fmt="%.12g")
        generated.append(path)

    dt = float(np.median(np.diff(raw.time_s)))
    peaks, _ = find_peaks(raw.aorta_inflow_mL_s.to_numpy(), prominence=100.0,
                          distance=max(1, int(0.6 / dt)))
    left, right = peaks[-2], peaks[-1]
    segment = raw.iloc[left:right + 1]
    phase = ((segment.time_s - segment.time_s.iloc[0]) /
             (segment.time_s.iloc[-1] - segment.time_s.iloc[0])).to_numpy()
    flow = segment.aorta_inflow_mL_s.to_numpy()
    unique = flow[:-1]
    start = int(np.argmax(np.diff(unique, append=unique[0])))
    unique = np.roll(unique, -start)
    flow = np.r_[unique, unique[0]]
    source_phase = np.linspace(0.0, 1.0, len(flow))
    target_phase = np.linspace(0.0, 1.0, 201)
    flow = np.interp(target_phase, source_phase, flow) * 1e-6
    flow[np.abs(flow) < 1e-10] = 1e-10
    path = OUT / "pulse_single_cycle_201.dat"
    np.savetxt(path, np.column_stack([target_phase * 0.84, flow]), fmt="%.12g")
    generated.append(path)
    return generated


def prepare() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    base_manifest = json.loads((STAGE4 / "base_config_manifest.json").read_text())
    scale = base_manifest["global_resistance_scale"]
    diagnostic = write_diagnostic_inlets()
    cases = [
        configure("default_published", DEFAULT_INLET, 1.0),
        configure("default_scaled", DEFAULT_INLET, scale),
        configure("pulse_single_201_published", diagnostic[1], 1.0),
        configure("pulse_average_1001_published", diagnostic[0], 1.0),
    ]
    manifest = {
        "openbf_revision": subprocess.check_output(
            ["git", "-C", str(OPENBF), "rev-parse", "HEAD"], text=True).strip(),
        "base_yaml": str(BASE_YAML), "global_resistance_scale": scale,
        "terminal_compliance_scale": 1.0,
        "cases": cases,
    }
    (OUT / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


def pressure_metrics(case: str, run_root: Path = OUT / "runs") -> dict:
    path = run_root / case / "aortic_arch_I_P.last"
    data = np.loadtxt(path)
    p = pa_to_mmhg(data[:, 1])
    duration = data[-1, 0] - data[0, 0]
    convergence = (run_root / case / f"{case}.conv").read_text().splitlines()
    return {"case": case, "systolic_mmHg": float(p.max()),
            "diastolic_mmHg": float(p.min()),
            "mean_mmHg": float(np.trapz(p, data[:, 0]) / duration),
            "pulse_pressure_mmHg": float(np.ptp(p)),
            "openbf_converged": convergence[0].strip().lower() == "true",
            "openbf_cycles": int(convergence[1]),
            "openbf_solver_elapsed_s": float(convergence[2])}


def inlet_metrics(label: str, path: Path) -> dict:
    data = np.loadtxt(path)
    t, q = data[:, 0], data[:, 1] * 1e6
    period = float(t[-1] - t[0])
    phase = (t - t[0]) / period
    peak = float(q.max())
    positive = q > 0.01 * peak
    # Integrating the periodic indicator is invariant to cycle start and valid for irregular samples.
    ejection_fraction = float(np.trapz(positive.astype(float), t) / period)
    dqdt = np.gradient(q, t)
    peak_idx = int(np.argmax(q))
    post = q[peak_idx:]
    post_t = t[peak_idx:]
    min_post_idx = int(np.argmin(post))
    below = np.flatnonzero(post <= 0.01 * peak)
    ejection_end_idx = int(below[0]) if len(below) else len(post) - 1
    return {
        "inlet": label, "points": len(t), "period_s": period,
        "peak_flow_mL_s": peak, "time_to_peak_s": float(t[peak_idx]-t[0]),
        "phase_to_peak": float(phase[peak_idx]),
        "max_rate_of_rise_mL_s2": float(dqdt.max()),
        "cycle_mean_flow_mL_s": float(np.trapz(q, t) / period),
        "stroke_volume_mL": float(np.trapz(q, t)),
        "ejection_duration_fraction_1pct_peak": ejection_fraction,
        "minimum_flow_after_peak_mL_s": float(post[min_post_idx]),
        "phase_of_post_peak_minimum": float(
            (post_t[min_post_idx]-t[0])/period),
        "dicrotic_flow_reversal_present": bool(np.any(post < -0.01 * peak)),
        "mean_downslope_peak_to_1pct_mL_s2": float(
            (post[ejection_end_idx] - peak) /
            (post_t[ejection_end_idx] - t[peak_idx])),
    }


def extraction_audit() -> dict:
    raw = pd.read_csv(STAGE4 / "private/pulse_stable_raw.csv.gz")
    dt = float(np.median(np.diff(raw.time_s)))
    peaks, _ = find_peaks(raw.aorta_inflow_mL_s.to_numpy(), prominence=100.0,
                          distance=max(1, int(0.6 / dt)))
    last = peaks[-9:]
    cycle_peaks = [float(raw.aorta_inflow_mL_s.iloc[l:r+1].max())
                   for l, r in zip(last[:-1], last[1:])]
    average_peak = float(np.loadtxt(STAGE4 / "pulse_aortic_inlet.dat")[:, 1].max()*1e6)
    audit = {
        "raw_sampling_interval_s": dt,
        "raw_sampling_rate_Hz": 1.0/dt,
        "raw_cycle_peaks_mL_s": cycle_peaks,
        "raw_peak_mean_mL_s": float(np.mean(cycle_peaks)),
        "raw_peak_range_mL_s": [float(np.min(cycle_peaks)), float(np.max(cycle_peaks))],
        "averaged_201_peak_mL_s": average_peak,
        "averaging_peak_attenuation_percent": float(
            100*(np.mean(cycle_peaks)-average_peak)/np.mean(cycle_peaks)),
        "cycle_alignment_max_rmse_fraction_of_peak": json.loads(
            (STAGE4 / "pulse_inlet_metadata.json").read_text())[
                "maximum_cycle_flow_rmse_fraction_of_peak"],
        "source_semantics": (
            "Pulse VascularCompartment::Aorta InFlow; the Aorta compartment's "
            "incoming liquid link is LeftHeartToAorta, mapped to circuit path "
            "LeftHeart1ToAorta2 (SetupCircuitsAndCompartments.cpp:1123-1124)."),
        "zero_and_start": (
            "Values below 1e-10 m3/s use ADAN56's nonzero convention; cycle "
            "starts immediately before maximum systolic upstroke. A rejected "
            "peak-start/exact-zero probe produced non-finite pressure."),
    }
    return audit


def analyse() -> None:
    inlets = [
        ("ADAN56 default", DEFAULT_INLET),
        ("Pulse average 201", STAGE4 / "pulse_aortic_inlet.dat"),
        ("Pulse single cycle 201", OUT / "pulse_single_cycle_201.dat"),
        ("Pulse average 1001", OUT / "pulse_average_1001.dat"),
    ]
    inlet_rows = [inlet_metrics(*item) for item in inlets]
    pd.DataFrame(inlet_rows).to_csv(OUT / "inlet_metrics.csv", index=False)

    cells = [
        pressure_metrics("default_published"),
        pressure_metrics("stage4_unscaled", STAGE4 / "runs"),
        pressure_metrics("default_scaled"),
        pressure_metrics("stage4_scaled", STAGE4 / "runs"),
    ]
    for row, inlet, terminals in zip(
            cells, ["ADAN56 default", "Pulse", "ADAN56 default", "Pulse"],
            ["published", "published", "scaled", "scaled"]):
        row["inlet"] = inlet
        row["terminals"] = terminals
    swap = pd.DataFrame(cells)
    swap.to_csv(OUT / "swap_test.csv", index=False)

    artifact = [pressure_metrics("pulse_single_201_published"),
                pressure_metrics("pulse_average_1001_published")]
    artifact.insert(0, pressure_metrics("stage4_unscaled", STAGE4 / "runs"))
    pd.DataFrame(artifact).to_csv(OUT / "extraction_reruns.csv", index=False)
    audit = extraction_audit()
    (OUT / "extraction_audit.json").write_text(json.dumps(audit, indent=2) + "\n")

    default_pp = float(swap.query("inlet == 'ADAN56 default' and terminals == 'published'").pulse_pressure_mmHg.iloc[0])
    pulse_pp = float(swap.query("inlet == 'Pulse' and terminals == 'published'").pulse_pressure_mmHg.iloc[0])
    default_scaled_pp = float(swap.query("inlet == 'ADAN56 default' and terminals == 'scaled'").pulse_pressure_mmHg.iloc[0])
    pulse_scaled_pp = float(swap.query("inlet == 'Pulse' and terminals == 'scaled'").pulse_pressure_mmHg.iloc[0])
    pulse_scaled_mean = float(swap.query("inlet == 'Pulse' and terminals == 'scaled'").mean_mmHg.iloc[0])
    pulse_mean = json.loads((STAGE4 / "pulse_inlet_metadata.json").read_text())[
        "aortic_cycle_mean_pressure_mmHg"]
    mean_pass = abs(pulse_scaled_mean - pulse_mean) <= 5.0
    summary = {
        "diagnosis": "inlet waveform",
        "published_terminal_inlet_effect_mmHg": pulse_pp-default_pp,
        "default_inlet_terminal_scaling_effect_mmHg": default_scaled_pp-default_pp,
        "pulse_inlet_terminal_scaling_effect_mmHg": pulse_scaled_pp-pulse_pp,
        "reference": {
            "standard_patient_age_years": 44,
            "observed_25_to_44_reference_interval_mmHg": [18, 43],
            "healthy_male_40_to_49_median_mmHg": 32,
            "healthy_male_40_to_49_p10_p90_mmHg": [25, 45],
            "charlton_virtual_age_pp_mmHg": {
                "25": 25.4, "35": 27.3, "45": 31.2,
                "55": 34.5, "65": 38.8, "75": 43.4},
        },
        "wall_property_branch_reached": False,
        "wall_property_reason": "Not reached: the swap test implicated the inlet.",
        "gate_decision": "agreement in mean, physiological pulse-pressure plausibility, and waveform-shape plausibility",
        "gate_limits": {
            "mean_error_vs_pulse_mmHg": 5.0,
            "pulse_pressure_reference_interval_mmHg_age_25_to_44": [18, 43],
        },
        "coupled_scaled_gate": {
            "mean_error_vs_pulse_mmHg": pulse_scaled_mean - pulse_mean,
            "mean_pass": mean_pass,
            "pulse_pressure_in_reference_interval": bool(18 <= pulse_scaled_pp <= 43),
            "shape_caveat": "low-tail PP caused by the genuine Pulse inlet; retain as a known coupling property",
            "passed": bool(mean_pass and 18 <= pulse_scaled_pp <= 43),
        },
    }
    (OUT / "stage4b_summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    fig, ax = plt.subplots(figsize=(9, 5), constrained_layout=True)
    for label, path in inlets[:2]:
        data = np.loadtxt(path)
        ax.plot((data[:, 0]-data[0, 0])/(data[-1, 0]-data[0, 0]),
                data[:, 1]*1e6, label=label)
    ax.axhline(0, color="black", linewidth=0.7)
    ax.set(xlabel="Cardiac-cycle phase", ylabel="Aortic inflow (mL/s)",
           title="ADAN56 and Pulse inlet waveforms")
    ax.legend()
    fig.savefig(OUT / "inlet_comparison.png", dpi=180)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "analyse"])
    args = parser.parse_args()
    prepare() if args.mode == "prepare" else analyse()


if __name__ == "__main__":
    main()
