#!/usr/bin/env python3
"""Prepare and analyse Stage 4 carotid plausibility and sensitivity runs."""

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

ROOT = Path(__file__).resolve().parents[1]
OPENBF = Path(os.environ.get("OPENBF_ROOT", "{OPENBF_ROOT}"))
BASE = OPENBF / "models/boileau2015/adan56/adan56.yaml"
STAGE0 = ROOT / "results/stage0/openbf_adan56"
STAGE4 = ROOT / "results/stage4"
OUT = ROOT / "results/stage4_completion"
SITES = ("external_carotid_R", "internal_carotid_R")
PA_PER_MMHG = 133.322387415


def write_case(name: str, inlet: Path, resistance_scale: float,
               flow_scale: float = 1.0, period_scale: float = 1.0,
               youngs_modulus_scale: float = 1.0) -> dict:
    case_dir = OUT / "configs" / name
    case_dir.mkdir(parents=True, exist_ok=True)
    inlet_data = np.loadtxt(inlet)
    inlet_data[:, 0] *= period_scale
    inlet_data[:, 1] *= flow_scale
    inlet_out = case_dir / f"{name}_inlet.dat"
    np.savetxt(inlet_out, inlet_data, fmt="%.12g")
    config = yaml.safe_load(BASE.read_text())
    config["project_name"] = name
    config["inlet_file"] = inlet_out.name
    config["solver"]["cycles"] = 15
    for vessel in config["network"]:
        vessel["E"] *= youngs_modulus_scale
        if vessel.get("outlet") == "wk3":
            vessel["R1"] *= resistance_scale
            vessel["R2"] *= resistance_scale
    yaml_out = case_dir / f"{name}.yaml"
    yaml_out.write_text(yaml.safe_dump(config, sort_keys=False))
    return {
        "case": name, "yaml": str(yaml_out), "inlet": str(inlet_out),
        "terminal_resistance_scale": resistance_scale,
        "terminal_compliance_scale": 1.0,
        "inlet_flow_scale": flow_scale, "cardiac_period_scale": period_scale,
        "wall_youngs_modulus_scale": youngs_modulus_scale,
    }


def prepare() -> None:
    gate = json.loads((ROOT / "config/stage4b_aortic_gate_v1.json").read_text())
    result = json.loads((OUT.parent / "stage4b/stage4b_summary.json").read_text())
    if not gate["selected_arm_passed"] or not result["coupled_scaled_gate"]["passed"]:
        raise RuntimeError("The amended Stage 4b aortic gate is not passing")
    manifest = json.loads((STAGE4 / "base_config_manifest.json").read_text())
    resistance = manifest["global_resistance_scale"]
    inlet = STAGE4 / "pulse_aortic_inlet.dat"
    cases = [
        write_case("sensitivity_flow_low", inlet, resistance, flow_scale=0.95),
        write_case("sensitivity_flow_high", inlet, resistance, flow_scale=1.05),
        write_case("sensitivity_period_low", inlet, resistance, period_scale=0.95),
        write_case("sensitivity_period_high", inlet, resistance, period_scale=1.05),
        write_case("sensitivity_wall_stiffness_2x", inlet, resistance,
                   youngs_modulus_scale=2.0),
    ]
    output = {
        "openbf_revision": subprocess.check_output(
            ["git", "-C", str(OPENBF), "rev-parse", "HEAD"], text=True).strip(),
        "base_yaml": str(BASE), "selected_baseline": "stage4_scaled",
        "global_resistance_scale": resistance,
        "stiffness_decision": (
            "All vessel E doubled as an approximate conduit-wall compliance "
            "halving; terminal Cc unchanged to isolate distributed stiffness."),
        "cases": cases,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "run_manifest.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))


def trace(directory: Path, vessel: str, field: str) -> tuple[np.ndarray, np.ndarray]:
    data = np.loadtxt(directory / f"{vessel}_{field}.last")
    return data[:, 0], data[:, -1]


def phase_trace(directory: Path, vessel: str, field: str,
                points: int = 501) -> tuple[np.ndarray, np.ndarray]:
    time_s, values = trace(directory, vessel, field)
    phase = (time_s - time_s[0]) / (time_s[-1] - time_s[0])
    target = np.linspace(0.0, 1.0, points)
    return target, np.interp(target, phase, values)


def metrics(directory: Path, case: str, vessel: str) -> dict:
    time_s, pressure_pa = trace(directory, vessel, "P")
    pressure = pa_to_mmhg(pressure_pa)
    _, flow = trace(directory, vessel, "Q")
    duration = time_s[-1] - time_s[0]
    conv = (directory / f"{case}.conv").read_text().splitlines()
    wall_time = directory / "bridge_wall_time_s.txt"
    return {
        "case": case, "vessel": vessel,
        "systolic_mmHg": float(pressure.max()),
        "diastolic_mmHg": float(pressure.min()),
        "mean_mmHg": float(np.trapz(pressure, time_s) / duration),
        "pulse_pressure_mmHg": float(np.ptp(pressure)),
        "mean_flow_mL_min": float(np.trapz(flow, time_s) / duration * 6e7),
        "openbf_converged": conv[0].strip().lower() == "true",
        "openbf_cycles": int(conv[1]),
        "openbf_solver_elapsed_s": float(conv[2]),
        "end_to_end_wall_s": float(wall_time.read_text()) if wall_time.exists() else None,
    }


def morphology(reference_dir: Path, pulse_dir: Path, vessel: str) -> dict:
    phase, reference_pa = phase_trace(reference_dir, vessel, "P")
    _, pulse_pa = phase_trace(pulse_dir, vessel, "P")
    reference = pa_to_mmhg(reference_pa)
    pulse = pa_to_mmhg(pulse_pa)
    ref_norm = (reference-reference.min()) / np.ptp(reference)
    pulse_norm = (pulse-pulse.min()) / np.ptp(pulse)
    # Separate morphology from a small timing displacement. Search is bounded
    # to +/-5% of a cycle and the selected shift remains an explicit result.
    ref_unique, pulse_unique = ref_norm[:-1], pulse_norm[:-1]
    candidates = []
    for shift in range(-25, 26):
        aligned = np.roll(pulse_unique, shift)
        rmse = float(np.sqrt(np.mean((ref_unique-aligned)**2)))
        candidates.append((rmse, shift, aligned))
    aligned_rmse, aligned_shift, aligned_pulse = min(candidates, key=lambda x: x[0])
    aligned_correlation = float(np.corrcoef(ref_unique, aligned_pulse)[0, 1])
    peaks, properties = find_peaks(pulse_norm, prominence=0.02, distance=15)
    return {
        "vessel": vessel,
        "shape_correlation": float(np.corrcoef(ref_norm, pulse_norm)[0, 1]),
        "normalised_shape_rmse": float(np.sqrt(np.mean((ref_norm-pulse_norm)**2))),
        "phase_aligned_shape_correlation": aligned_correlation,
        "phase_aligned_normalised_shape_rmse": aligned_rmse,
        "optimal_bounded_phase_shift": aligned_shift / len(ref_unique),
        "stage3_primary_peak_phase": float(phase[np.argmax(reference)]),
        "pulse_primary_peak_phase": float(phase[np.argmax(pulse)]),
        "pulse_identifiable_peak_count": int(len(peaks)),
        "pulse_peak_phases": ";".join(f"{phase[i]:.4f}" for i in peaks),
        "shape_plausible": bool(
            aligned_correlation >= 0.90
            and aligned_rmse <= 0.20
            and len(peaks) >= 1),
    }


def analyse() -> None:
    baseline_dir = STAGE4 / "runs/stage4_scaled"
    baseline = {v: metrics(baseline_dir, "stage4_scaled", v) for v in SITES}
    stage3 = {v: metrics(STAGE0, "adan56", v) for v in SITES}
    comparison = []
    for vessel in SITES:
        row = morphology(STAGE0, baseline_dir, vessel)
        for prefix, source in (("stage3", stage3[vessel]),
                               ("pulse", baseline[vessel])):
            for key in ("systolic_mmHg", "diastolic_mmHg", "mean_mmHg",
                        "pulse_pressure_mmHg", "mean_flow_mL_min"):
                row[f"{prefix}_{key}"] = source[key]
        comparison.append(row)
    comparison_frame = pd.DataFrame(comparison)
    comparison_frame.to_csv(OUT / "carotid_plausibility.csv", index=False)

    manifest = json.loads((OUT / "run_manifest.json").read_text())
    sensitivity = []
    for item in manifest["cases"]:
        case = item["case"]
        directory = OUT / "runs" / case
        for vessel in SITES:
            row = metrics(directory, case, vessel)
            _, case_pressure = phase_trace(directory, vessel, "P")
            _, base_pressure = phase_trace(baseline_dir, vessel, "P")
            row["waveform_rmse_vs_baseline_mmHg"] = float(
                np.sqrt(np.mean(((case_pressure-base_pressure)/PA_PER_MMHG)**2)))
            for key in ("systolic_mmHg", "diastolic_mmHg", "mean_mmHg",
                        "pulse_pressure_mmHg", "mean_flow_mL_min"):
                row[f"delta_{key}"] = row[key] - baseline[vessel][key]
            row.update({
                "inlet_flow_scale": item["inlet_flow_scale"],
                "cardiac_period_scale": item["cardiac_period_scale"],
                "wall_youngs_modulus_scale": item["wall_youngs_modulus_scale"],
            })
            sensitivity.append(row)
    sensitivity_frame = pd.DataFrame(sensitivity)
    sensitivity_frame.to_csv(OUT / "carotid_sensitivity.csv", index=False)

    inlet = sensitivity_frame[sensitivity_frame.wall_youngs_modulus_scale == 1.0]
    stiffness = sensitivity_frame[
        sensitivity_frame.wall_youngs_modulus_scale == 2.0].set_index("vessel")
    floors = []
    for vessel in SITES:
        site_inlet = inlet[inlet.vessel == vessel]
        noise_rmse = float(site_inlet.waveform_rmse_vs_baseline_mmHg.max())
        noise_pp = float(site_inlet.delta_pulse_pressure_mmHg.abs().max())
        stiff_rmse = float(stiffness.loc[vessel, "waveform_rmse_vs_baseline_mmHg"])
        stiff_pp = float(abs(stiffness.loc[vessel, "delta_pulse_pressure_mmHg"]))
        floors.append({
            "vessel": vessel,
            "maximum_inlet_waveform_rmse_mmHg": noise_rmse,
            "stiffness_waveform_rmse_mmHg": stiff_rmse,
            "stiffness_to_inlet_rmse_ratio": stiff_rmse/noise_rmse,
            "maximum_inlet_absolute_delta_pp_mmHg": noise_pp,
            "stiffness_absolute_delta_pp_mmHg": stiff_pp,
            "stiffness_to_inlet_delta_pp_ratio": stiff_pp/noise_pp,
            "stiffness_exceeds_tested_inlet_noise": bool(stiff_rmse > noise_rmse),
        })
    floor_frame = pd.DataFrame(floors)
    floor_frame.to_csv(OUT / "stage5_noise_floor.csv", index=False)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
    for axis, vessel in zip(axes, SITES):
        for directory, label in ((STAGE0, "Stage 3 default inlet"),
                                 (baseline_dir, "Pulse inlet")):
            phase, p = phase_trace(directory, vessel, "P")
            p = pa_to_mmhg(p)
            axis.plot(phase, (p-p.min())/np.ptp(p), label=label)
        axis.set(title=vessel, xlabel="Cycle phase",
                 ylabel="Normalised distal pressure")
        axis.legend()
    fig.savefig(OUT / "carotid_shape_plausibility.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
    for axis, vessel in zip(axes, SITES):
        phase, base = phase_trace(baseline_dir, vessel, "P")
        axis.plot(phase, pa_to_mmhg(base), label="baseline", linewidth=2)
        for case, label in (("sensitivity_flow_low", "flow -5%"),
                            ("sensitivity_flow_high", "flow +5%"),
                            ("sensitivity_period_low", "period -5%"),
                            ("sensitivity_period_high", "period +5%"),
                            ("sensitivity_wall_stiffness_2x", "E x2")):
            _, p = phase_trace(OUT / "runs" / case, vessel, "P")
            axis.plot(phase, pa_to_mmhg(p), label=label, alpha=0.8)
        axis.set(title=vessel, xlabel="Cycle phase", ylabel="Distal pressure (mmHg)")
        axis.legend(fontsize=8)
    fig.savefig(OUT / "carotid_sensitivity.png", dpi=180)
    plt.close(fig)

    costs = sensitivity_frame.groupby("case").first()[
        ["openbf_converged", "openbf_cycles", "openbf_solver_elapsed_s",
         "end_to_end_wall_s"]].reset_index().to_dict("records")
    summary = {
        "selected_baseline": "stage4_scaled",
        "distal_column_used": True,
        "carotid_shape_gate_passed": bool(comparison_frame.shape_plausible.all()),
        "ica_mean_flow_exceeds_eca": bool(
            baseline["internal_carotid_R"]["mean_flow_mL_min"]
            > baseline["external_carotid_R"]["mean_flow_mL_min"]),
        "all_runs_converged": bool(sensitivity_frame.openbf_converged.all()),
        "stiffness_exceeds_tested_inlet_noise_both_sites": bool(
            floor_frame.stiffness_exceeds_tested_inlet_noise.all()),
        "stage5_baseline_scaling_question": (
            "Open: repeat the same E x2 perturbation from an age-45-matched "
            "approximately 31 mmHg aortic-PP baseline; this Stage 4 result "
            "only establishes response above the depressed coupled baseline."),
        "runtime": costs,
        "stage4_complete": bool(
            comparison_frame.shape_plausible.all()
            and sensitivity_frame.openbf_converged.all()),
    }
    (OUT / "stage4_completion_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "analyse"))
    args = parser.parse_args()
    prepare() if args.mode == "prepare" else analyse()


if __name__ == "__main__":
    main()
