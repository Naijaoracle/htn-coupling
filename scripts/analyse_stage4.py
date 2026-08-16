#!/usr/bin/env python3
"""Apply the aortic gate and, only after it passes, analyse Stage 4."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from bridge_units import pa_to_mmhg

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/stage4"
SPEC = json.loads((ROOT / "config/stage4_interface_v1.json").read_text())
SITES = ["aortic_arch_I", "external_carotid_R", "internal_carotid_R"]


def waveform(case, vessel, field):
    path = OUT / "runs" / case / f"{vessel}_{field}.last"
    data = np.loadtxt(path)
    return data[:, 0], data[:, 1], path


def pressure_metrics(case, vessel):
    time_s, pressure_pa, path = waveform(case, vessel, "P")
    pressure = pa_to_mmhg(pressure_pa)
    duration = time_s[-1] - time_s[0]
    return {
        "case": case, "vessel": vessel, "file": str(path),
        "systolic_mmHg": float(np.max(pressure)),
        "diastolic_mmHg": float(np.min(pressure)),
        "mean_mmHg": float(np.trapz(pressure, time_s) / duration),
        "pulse_pressure_mmHg": float(np.ptp(pressure)),
    }


def plot_base():
    representative = pd.read_csv(OUT / "pulse_representative_cycle.csv")
    fig, axes = plt.subplots(2, 1, figsize=(10, 8), constrained_layout=True)
    axes[0].plot(representative.time_s / representative.time_s.max(),
                 representative.aorta_pressure_mmHg, label="Pulse aorta")
    for case, label in (("stage4_unscaled", "openBF unscaled"),
                        ("stage4_scaled", "openBF resistance-scaled")):
        time_s, pressure_pa, _ = waveform(case, "aortic_arch_I", "P")
        axes[0].plot((time_s-time_s[0])/(time_s[-1]-time_s[0]),
                     pa_to_mmhg(pressure_pa), label=label)
    axes[0].set(xlabel="Cycle phase", ylabel="Pressure (mmHg)",
                title="Aortic acceptance comparison")
    axes[0].legend()
    for case, label in (("stage4_unscaled", "unscaled"),
                        ("stage4_scaled", "scaled")):
        time_s, flow, _ = waveform(case, "aortic_arch_I", "Q")
        axes[1].plot((time_s-time_s[0])/(time_s[-1]-time_s[0]),
                     flow*1e6, label=label)
    axes[1].plot(representative.time_s / representative.time_s.max(),
                 representative.aorta_inflow_mL_s, linestyle="--", label="Pulse inlet")
    axes[1].set(xlabel="Cycle phase", ylabel="Flow (mL/s)")
    axes[1].legend()
    fig.savefig(OUT / "aortic_agreement.png", dpi=180)
    plt.close(fig)


def base_gate():
    pulse = json.loads((OUT / "pulse_inlet_metadata.json").read_text())
    tolerance = SPEC["aortic_acceptance"]
    arms, rows = {}, []
    for arm, case in (("unscaled", "stage4_unscaled"),
                      ("scaled", "stage4_scaled")):
        metric = pressure_metrics(case, "aortic_arch_I")
        metric["pulse_mean_mmHg"] = pulse["aortic_cycle_mean_pressure_mmHg"]
        metric["pulse_pulse_pressure_mmHg"] = (
            pulse["aortic_cycle_systolic_pressure_mmHg"]
            - pulse["aortic_cycle_diastolic_pressure_mmHg"])
        metric["mean_error_mmHg"] = metric["mean_mmHg"] - metric["pulse_mean_mmHg"]
        metric["pulse_pressure_error_mmHg"] = (
            metric["pulse_pressure_mmHg"] - metric["pulse_pulse_pressure_mmHg"])
        metric["passed"] = (
            abs(metric["mean_error_mmHg"]) <= tolerance["mean_pressure_tolerance_mmHg"]
            and abs(metric["pulse_pressure_error_mmHg"])
            <= tolerance["pulse_pressure_tolerance_mmHg"])
        conv = (OUT / "runs" / case / f"{case}.conv").read_text().splitlines()
        metric["openbf_converged"] = conv[0].strip().lower() == "true"
        metric["openbf_cycles"] = int(conv[1])
        metric["openbf_solver_elapsed_s"] = float(conv[2])
        arms[arm] = metric
        rows.append(metric)
    costs = {}
    for arm, case in (("unscaled", "stage4_unscaled"),
                      ("scaled", "stage4_scaled")):
        costs[arm] = float((OUT / "runs" / case /
                            "bridge_wall_time_s.txt").read_text())
    result = {"passed": any(item["passed"] for item in arms.values()),
              "tolerances": tolerance, "arms": arms,
              "wall_time_s": costs,
              "downstream_status": "blocked"}
    (OUT / "aortic_gate.json").write_text(json.dumps(result, indent=2) + "\n")
    pd.DataFrame(rows).to_csv(OUT / "aortic_agreement.csv", index=False)
    plot_base()
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit("Aortic acceptance gate failed for both arms")


def final_analysis():
    gate = json.loads((OUT / "aortic_gate.json").read_text())
    if not gate["passed"]:
        raise RuntimeError("Aortic gate failed")
    selected = ("stage4_scaled" if gate["arms"]["scaled"]["passed"]
                else "stage4_unscaled")
    rows = [pressure_metrics(selected, vessel) for vessel in SITES]
    for row in rows:
        time_s, flow, _ = waveform(selected, row["vessel"], "Q")
        row["mean_flow_mL_s"] = float(
            np.trapz(flow, time_s)/(time_s[-1]-time_s[0])*1e6)
    sites = pd.DataFrame(rows)
    sites.to_csv(OUT / "reference_site_metrics.csv", index=False)
    sensitivity = []
    baseline = {v: pressure_metrics(selected, v) for v in SITES[1:]}
    for case in ("sensitivity_flow_low", "sensitivity_flow_high",
                 "sensitivity_period_low", "sensitivity_period_high"):
        for vessel in SITES[1:]:
            metric = pressure_metrics(case, vessel)
            for name in ("systolic_mmHg", "diastolic_mmHg", "mean_mmHg",
                         "pulse_pressure_mmHg"):
                metric[f"delta_{name}"] = metric[name] - baseline[vessel][name]
            sensitivity.append(metric)
    sensitivity = pd.DataFrame(sensitivity)
    sensitivity.to_csv(OUT / "inlet_sensitivity.csv", index=False)
    times = []
    for directory in sorted((OUT / "runs").iterdir()):
        path = directory / "bridge_wall_time_s.txt"
        if path.exists():
            times.append({"case": directory.name,
                          "wall_time_s": float(path.read_text())})
    pd.DataFrame(times).to_csv(OUT / "run_costs.csv", index=False)
    by_site = sites.set_index("vessel")
    summary = {
        "selected_arm": selected, "aortic_gate": gate,
        "reference_sites": rows,
        "eca_mean_flow_less_than_ica": bool(
            by_site.loc["external_carotid_R", "mean_flow_mL_s"]
            < by_site.loc["internal_carotid_R", "mean_flow_mL_s"]),
        "maximum_absolute_sensitivity_delta_mmHg": float(
            sensitivity.filter(like="delta_").abs().max().max()),
        "run_costs": times,
    }
    (OUT / "stage4_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["gate", "final"])
    args = parser.parse_args()
    base_gate() if args.mode == "gate" else final_analysis()


if __name__ == "__main__":
    main()
