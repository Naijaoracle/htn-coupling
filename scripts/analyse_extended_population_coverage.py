#!/usr/bin/env python3
"""Rebuild pressure-pair lookup coverage from the extended Pulse sweep."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.interpolate import LinearNDInterpolator
from scipy.spatial import ConvexHull, Delaunay

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_stage2_tier0 import load_elsa, load_haalsi

OUT = ROOT / "results/stage2"


class Domain:
    def __init__(self, name, frame, definition):
        self.name, self.definition = name, definition
        self.frame = frame.drop_duplicates(
            ["resistance_multiplier", "compliance_multiplier"], keep="last")
        pressure = self.frame[["achieved_systolic_mmHg",
                               "achieved_diastolic_mmHg"]].to_numpy()
        modifiers = self.frame[["resistance_multiplier",
                                "compliance_multiplier"]].to_numpy()
        self.hull = Delaunay(pressure, qhull_options="QJ")
        self.convex = ConvexHull(pressure)
        self.r = LinearNDInterpolator(self.hull, modifiers[:, 0], fill_value=np.nan)
        self.c = LinearNDInterpolator(self.hull, modifiers[:, 1], fill_value=np.nan)

    def reachable(self, frame):
        points = frame[["systolic_mmHg", "diastolic_mmHg"]].to_numpy()
        return self.hull.find_simplex(points) >= 0

    def table(self):
        rows = []
        for systolic in range(80, 221, 5):
            for diastolic in range(40, 141, 5):
                point = np.array([[systolic, diastolic]])
                reachable = self.hull.find_simplex(point)[0] >= 0
                rows.append({
                    "domain": self.name, "target_systolic_mmHg": systolic,
                    "target_diastolic_mmHg": diastolic,
                    "lookup_reachable": bool(reachable),
                    "resistance_multiplier": (float(self.r(point)[0])
                                                if reachable else np.nan),
                    "compliance_multiplier": (float(self.c(point)[0])
                                                if reachable else np.nan),
                })
        return pd.DataFrame(rows)


def phenotypes(frame):
    sbp, dbp = frame.systolic_mmHg, frame.diastolic_mmHg
    return {
        "all_valid_pressure": np.ones(len(frame), dtype=bool),
        "hypertension_140_or_90": (sbp >= 140) | (dbp >= 90),
        "isolated_systolic_hypertension": (sbp >= 140) & (dbp < 90),
        "combined_systolic_diastolic_hypertension": (sbp >= 140) & (dbp >= 90),
        "isolated_diastolic_hypertension": (sbp < 140) & (dbp >= 90),
        "hypertension_with_pulse_pressure_ge_60": (((sbp >= 140) | (dbp >= 90))
                                                    & ((sbp-dbp) >= 60)),
    }


def summarize(cohort, frame, domain):
    frame = frame.dropna(subset=["systolic_mmHg", "diastolic_mmHg"]).copy()
    frame["pulse_pressure_mmHg"] = frame.systolic_mmHg - frame.diastolic_mmHg
    reachable = domain.reachable(frame)
    rows = []
    for phenotype, mask in phenotypes(frame).items():
        mask = np.asarray(mask, dtype=bool)
        n = int(mask.sum())
        selected_reachable = reachable[mask]
        pp = frame.loc[mask, "pulse_pressure_mmHg"].to_numpy()
        rows.append({
            "cohort": cohort, "domain": domain.name,
            "domain_definition": domain.definition, "phenotype": phenotype,
            "n": n, "reachable_n": int(selected_reachable.sum()),
            "reachable_pct": 100 * float(selected_reachable.mean()) if n else np.nan,
            "unreachable_n": int((~selected_reachable).sum()),
            "unreachable_with_pp_ge_60_n": int(
                ((~selected_reachable) & (pp >= 60)).sum()),
            "median_pp_reachable_mmHg": (float(np.median(pp[selected_reachable]))
                                         if selected_reachable.any() else np.nan),
            "median_pp_unreachable_mmHg": (float(np.median(pp[~selected_reachable]))
                                           if (~selected_reachable).any() else np.nan),
        })
    return rows


def plot(domains, cohorts):
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), constrained_layout=True)
    for axis, (name, frame) in zip(axes, cohorts.items()):
        pressure = frame.dropna(subset=["systolic_mmHg", "diastolic_mmHg"])
        axis.hexbin(pressure.systolic_mmHg, pressure.diastolic_mmHg,
                    gridsize=35, mincnt=1, cmap="Greys", bins="log")
        for domain, color in zip(domains, ("tab:blue", "tab:orange", "tab:red")):
            points = domain.frame[["achieved_systolic_mmHg",
                                   "achieved_diastolic_mmHg"]].to_numpy()
            polygon = points[domain.convex.vertices]
            polygon = np.vstack([polygon, polygon[0]])
            axis.plot(polygon[:, 0], polygon[:, 1], color=color,
                      label=domain.name.replace("_", " "))
        axis.axvline(140, color="black", linestyle="--", linewidth=.8)
        axis.axhline(90, color="black", linestyle="--", linewidth=.8)
        axis.set(xlabel="Systolic pressure (mmHg)", ylabel="Diastolic pressure (mmHg)",
                 title=name.upper(), xlim=(75, 225), ylim=(35, 140))
        axis.legend(frameon=False, fontsize=8)
    fig.savefig(OUT / "extended_population_pressure_hulls.png", dpi=180)
    plt.close(fig)


def main():
    original = pd.read_csv(OUT / "reachability_sweep.csv").query("status == 'ok'")
    extended = pd.read_csv(OUT / "extended_boundary_sweep.csv").query("status == 'ok'")
    combined = pd.concat([original, extended], ignore_index=True)
    calibrated = combined[(combined.resistance_multiplier <= 2.0)
                          & (combined.compliance_multiplier >= 0.4)]
    domains = [
        Domain("prescribed", original,
               "R 1.0-1.6 and C 1.0-0.5, original dense grid"),
        Domain("calibration_extended", calibrated,
               "empirically sampled R <=2.0 and C >=0.4; includes 150/90-class point"),
        Domain("engineering_explored", combined,
               "all successful explored cells through R 6.0 and C 0.1; not asserted physiologic"),
    ]
    cohorts = {"haalsi": load_haalsi(), "elsa_wave8": load_elsa()}
    rows = [row for name, frame in cohorts.items() for domain in domains
            for row in summarize(name, frame, domain)]
    summary = pd.DataFrame(rows)
    summary.to_csv(OUT / "extended_population_coverage.csv", index=False)
    lookup = pd.concat([domain.table() for domain in domains], ignore_index=True)
    lookup.to_csv(OUT / "extended_calibration_lookup_table.csv", index=False)
    payload = {
        "hypertension_definition": "SBP >=140 mmHg or DBP >=90 mmHg",
        "isolated_systolic_definition": "SBP >=140 mmHg and DBP <90 mmHg",
        "domains": [{"name": d.name, "definition": d.definition,
                     "successful_sweep_cells": len(d.frame)} for d in domains],
        "coverage": summary.to_dict("records"),
        "guardrail": ("Pressure-pair convex-hull membership is an empirical lookup screen, "
                      "not proof that interpolated modifiers are physiologically plausible "
                      "or transferable to every body-defined patient."),
    }
    (OUT / "extended_population_coverage.json").write_text(
        json.dumps(payload, indent=2) + "\n")
    plot(domains, cohorts)
    print(summary[summary.phenotype != "all_valid_pressure"].to_string(index=False))


if __name__ == "__main__":
    main()
