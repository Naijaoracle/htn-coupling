#!/usr/bin/env python3
"""Diagnose Stage 5 augmentation pressure and reflection feature identity."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.signal import find_peaks, peak_prominences

from stage5_pipeline import ROOT, OUT as STAGE5, phase_pressure

AMEND = ROOT / "results/stage5_amendment"
OUT = ROOT / "results/stage5_followup"
SITES = ("external_carotid_R", "internal_carotid_R")
CASES = {
    "normotensive": {
        "inlet_only": (STAGE5/"runs/normotensive_arm1_inlet_only", "normotensive_arm1_inlet_only"),
        "uniform_E2p5": (STAGE5/"runs/threshold_E_2p50", "threshold_E_2p50"),
        "central_only_E2p5": (AMEND/"runs/normotensive_central_E_2p5", "normotensive_central_E_2p5"),
    },
    "compliance_dominant": {
        "inlet_only": (STAGE5/"runs/compliance_dominant_arm1_inlet_only", "compliance_dominant_arm1_inlet_only"),
        "uniform_E2p5": (STAGE5/"runs/compliance_dominant_arm2_matched_stiffening", "compliance_dominant_arm2_matched_stiffening"),
        "central_only_E2p5": (AMEND/"runs/compliance_dominant_central_E_2p5", "compliance_dominant_central_E_2p5"),
    },
    "combined": {
        "inlet_only": (STAGE5/"runs/combined_arm1_inlet_only", "combined_arm1_inlet_only"),
        "uniform_E2p5": (STAGE5/"runs/combined_arm2_matched_stiffening", "combined_arm2_matched_stiffening"),
        "central_only_E2p5": (AMEND/"runs/combined_central_E_2p5", "combined_central_E_2p5"),
    },
}


def features(directory: Path, case: str, vessel: str) -> tuple[dict, np.ndarray, np.ndarray]:
    phase, pressure = phase_pressure(directory, vessel)
    unique = pressure[:-1]
    primary = int(np.argmax(unique))
    prominence_threshold = max(0.02*np.ptp(pressure), 0.05)
    minima, _ = find_peaks(-unique, prominence=prominence_threshold/2, distance=15)
    peaks, props = find_peaks(unique, prominence=prominence_threshold, distance=15)
    later_min = minima[minima > primary]
    trough = int(later_min[0]) if len(later_min) else None
    secondary = None
    if trough is not None:
        later_peak = peaks[peaks > trough]
        secondary = int(later_peak[0]) if len(later_peak) else None
    pp = float(np.ptp(pressure))
    ap = (float(pressure[secondary]-pressure[trough])
          if secondary is not None else np.nan)
    prominences = peak_prominences(unique, peaks)[0] if len(peaks) else []
    row = {
        "phenotype": None, "arm": None, "case": case, "vessel": vessel,
        "pulse_pressure_mmHg": pp,
        "primary_peak_phase": float(phase[primary]),
        "primary_peak_pressure_mmHg": float(pressure[primary]),
        "selected_trough_phase": float(phase[trough]) if trough is not None else np.nan,
        "selected_trough_pressure_mmHg": float(pressure[trough]) if trough is not None else np.nan,
        "selected_secondary_phase": float(phase[secondary]) if secondary is not None else np.nan,
        "selected_secondary_pressure_mmHg": float(pressure[secondary]) if secondary is not None else np.nan,
        "augmentation_pressure_mmHg": ap,
        "augmentation_index_pct": 100*ap/pp if np.isfinite(ap) else np.nan,
        "all_peak_phases": ";".join(f"{phase[i]:.4f}" for i in peaks),
        "all_peak_pressures_mmHg": ";".join(f"{pressure[i]:.4f}" for i in peaks),
        "all_peak_prominences_mmHg": ";".join(f"{x:.4f}" for x in prominences),
        "detected_peak_count": int(len(peaks)),
    }
    return row, phase, pressure


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    fig, axes = plt.subplots(3, 2, figsize=(14, 12), sharex=True,
                             constrained_layout=True)
    colors = {"inlet_only": "black", "uniform_E2p5": "tab:red",
              "central_only_E2p5": "tab:blue"}
    for i, (phenotype, arms) in enumerate(CASES.items()):
        for j, vessel in enumerate(SITES):
            axis = axes[i, j]
            for arm, (directory, case) in arms.items():
                row, phase, pressure = features(directory, case, vessel)
                row["phenotype"], row["arm"] = phenotype, arm
                rows.append(row)
                axis.plot(phase, pressure, color=colors[arm], label=arm, linewidth=1.8)
                axis.scatter(row["primary_peak_phase"], row["primary_peak_pressure_mmHg"],
                             color=colors[arm], marker="^", s=55, zorder=4)
                if np.isfinite(row["selected_trough_phase"]):
                    axis.scatter(row["selected_trough_phase"], row["selected_trough_pressure_mmHg"],
                                 color=colors[arm], marker="v", s=45, zorder=4)
                if np.isfinite(row["selected_secondary_phase"]):
                    axis.scatter(row["selected_secondary_phase"], row["selected_secondary_pressure_mmHg"],
                                 facecolors="none", edgecolors=colors[arm], marker="o", s=70, zorder=5)
            axis.set(title=f"{phenotype} — {vessel}", ylabel="Pressure (mmHg)")
            axis.grid(alpha=.2)
            axis.legend(fontsize=8)
    for axis in axes[-1, :]:
        axis.set_xlabel("Cardiac-cycle phase")
    fig.suptitle("Reflection detector audit: ▲ primary, ▼ trough, ○ selected secondary", fontsize=14)
    fig.savefig(OUT/"reflection_detector_annotated_overlays.png", dpi=200)
    plt.close(fig)

    frame = pd.DataFrame(rows)
    frame.to_csv(OUT/"reflection_detector_features.csv", index=False)
    frame[["phenotype", "arm", "vessel", "pulse_pressure_mmHg",
           "augmentation_pressure_mmHg", "augmentation_index_pct"]].to_csv(
               OUT/"augmentation_pressure_diagnosis.csv", index=False)
    summary = {
        "augmentation_pressure_reported_with_index": True,
        "figure": str(OUT/"reflection_detector_annotated_overlays.png"),
        "classification_status": "pending visual inspection",
        "marker_key": {"primary": "filled triangle up", "trough": "filled triangle down",
                       "selected_secondary": "open circle"},
    }
    (OUT/"waveform_diagnostic_summary.json").write_text(json.dumps(summary, indent=2)+"\n")
    print(frame[["phenotype", "arm", "vessel", "pulse_pressure_mmHg",
                 "augmentation_pressure_mmHg", "augmentation_index_pct",
                 "primary_peak_phase", "selected_secondary_phase",
                 "detected_peak_count"]].to_string(index=False))


if __name__ == "__main__":
    main()
