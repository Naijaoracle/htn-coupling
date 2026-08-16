#!/usr/bin/env python3
"""Checkpointed outer-boundary sweep for the stock Pulse modifiers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from run_stage2_tier0 import (
    OUT,
    TOL_DBP,
    TOL_SBP,
    directories,
    modifier_worker,
    parallel,
    stage0_gate,
    standard_state,
)


CSV = OUT / "extended_boundary_sweep.csv"
SUMMARY = OUT / "extended_boundary_summary.json"
FIGURE = OUT / "extended_boundary_sweep.png"
CENSORED = OUT / "extended_boundary_censored.json"


def values(text: str) -> list[float]:
    return [float(item) for item in text.split(",") if item.strip()]


def key(resistance: float, compliance: float) -> tuple[float, float]:
    return round(float(resistance), 6), round(float(compliance), 6)


def load_existing() -> pd.DataFrame:
    return pd.read_csv(CSV) if CSV.exists() else pd.DataFrame()


def save(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.drop_duplicates(
        ["resistance_multiplier", "compliance_multiplier"], keep="last"
    ).sort_values(["resistance_multiplier", "compliance_multiplier"])
    frame.to_csv(CSV, index=False)
    return frame


def analyse(frame: pd.DataFrame) -> dict:
    ok = frame[frame.status.eq("ok")].copy()
    failed = frame[~frame.status.eq("ok")].copy()
    if ok.empty:
        raise RuntimeError("No successful extended-boundary cells")
    distance = np.hypot(
        ok.achieved_systolic_mmHg - 150.0,
        ok.achieved_diastolic_mmHg - 90.0,
    )
    nearest = ok.loc[distance.idxmin()]
    slopes = []
    for compliance, group in ok.groupby("compliance_multiplier"):
        group = group.sort_values("resistance_multiplier")
        if len(group) < 2:
            continue
        tail = group.tail(min(3, len(group)))
        delta_r = tail.resistance_multiplier.iloc[-1] - tail.resistance_multiplier.iloc[0]
        if delta_r <= 0:
            continue
        slopes.append({
            "compliance_multiplier": float(compliance),
            "last_resistance_multiplier": float(tail.resistance_multiplier.iloc[-1]),
            "tail_sbp_gain_mmHg_per_resistance_multiplier": float(
                (tail.achieved_systolic_mmHg.iloc[-1]
                 - tail.achieved_systolic_mmHg.iloc[0]) / delta_r
            ),
            "tail_dbp_gain_mmHg_per_resistance_multiplier": float(
                (tail.achieved_diastolic_mmHg.iloc[-1]
                 - tail.achieved_diastolic_mmHg.iloc[0]) / delta_r
            ),
        })
    censored = json.loads(CENSORED.read_text()) if CENSORED.exists() else []
    summary = {
        "tested_cells": int(len(frame)),
        "successful_cells": int(len(ok)),
        "failed_cells": int(len(failed)),
        "tested_resistance_min_max": [
            float(frame.resistance_multiplier.min()),
            float(frame.resistance_multiplier.max()),
        ],
        "tested_compliance_min_max": [
            float(frame.compliance_multiplier.min()),
            float(frame.compliance_multiplier.max()),
        ],
        "achieved_systolic_min_max_mmHg": [
            float(ok.achieved_systolic_mmHg.min()),
            float(ok.achieved_systolic_mmHg.max()),
        ],
        "achieved_diastolic_min_max_mmHg": [
            float(ok.achieved_diastolic_mmHg.min()),
            float(ok.achieved_diastolic_mmHg.max()),
        ],
        "achieved_map_min_max_mmHg": [
            float(ok.achieved_map_mmHg.min()),
            float(ok.achieved_map_mmHg.max()),
        ],
        "nearest_to_150_90": {
            "resistance_multiplier": float(nearest.resistance_multiplier),
            "compliance_multiplier": float(nearest.compliance_multiplier),
            "achieved_systolic_mmHg": float(nearest.achieved_systolic_mmHg),
            "achieved_diastolic_mmHg": float(nearest.achieved_diastolic_mmHg),
            "euclidean_residual_mmHg": float(distance.loc[nearest.name]),
            "within_stage2_tolerance": bool(
                abs(nearest.achieved_systolic_mmHg - 150) <= TOL_SBP
                and abs(nearest.achieved_diastolic_mmHg - 90) <= TOL_DBP
            ),
        },
        "failure_cells": failed[[
            "resistance_multiplier", "compliance_multiplier", "error"
        ]].to_dict("records") if not failed.empty else [],
        "censored_cells": censored,
        "high_resistance_tail_slopes": slopes,
        "plateau_rule": (
            "A tail is called practically flat only when absolute SBP gain is "
            "below 2 mmHg per +1.0 resistance multiplier across the last three "
            "successful points. Failure is reported separately, never as plateau."
        ),
        "practically_flat_compliance_levels": [
            item["compliance_multiplier"] for item in slopes
            if abs(item["tail_sbp_gain_mmHg_per_resistance_multiplier"]) < 2.0
        ],
    }
    SUMMARY.write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def plot(frame: pd.DataFrame) -> None:
    ok = frame[frame.status.eq("ok")]
    failed = frame[~frame.status.eq("ok")]
    fig, axes = plt.subplots(1, 3, figsize=(17, 5), constrained_layout=True)
    points = axes[0].scatter(
        ok.resistance_multiplier, ok.compliance_multiplier,
        c=ok.achieved_systolic_mmHg, cmap="viridis", s=65,
    )
    if not failed.empty:
        axes[0].scatter(
            failed.resistance_multiplier, failed.compliance_multiplier,
            marker="x", color="red", s=65, label="failed",
        )
        axes[0].legend(frameon=False)
    if CENSORED.exists():
        censored = pd.DataFrame(json.loads(CENSORED.read_text()))
        axes[0].scatter(
            censored.resistance_multiplier, censored.compliance_multiplier,
            marker="X", color="orange", edgecolor="black", s=90,
            label="operator-censored non-convergence",
        )
        axes[0].legend(frameon=False, fontsize=8)
    axes[0].set(
        xlabel="Systemic resistance multiplier",
        ylabel="Arterial compliance multiplier",
        title="Extended boundary and achieved SBP",
    )
    fig.colorbar(points, ax=axes[0], label="SBP (mmHg)")

    for compliance, group in ok.groupby("compliance_multiplier"):
        group = group.sort_values("resistance_multiplier")
        axes[1].plot(
            group.resistance_multiplier, group.achieved_systolic_mmHg,
            marker="o", label=f"C={compliance:g}",
        )
    axes[1].axhline(150, color="black", linestyle="--", linewidth=1)
    axes[1].set(
        xlabel="Systemic resistance multiplier", ylabel="Achieved SBP (mmHg)",
        title="Systolic reach and flattening",
    )
    axes[1].legend(frameon=False, ncol=2, fontsize=8)

    scatter = axes[2].scatter(
        ok.achieved_systolic_mmHg, ok.achieved_diastolic_mmHg,
        c=ok.restabilization_wall_s, cmap="magma", s=65,
    )
    axes[2].scatter([150], [90], marker="*", color="cyan", edgecolor="black",
                    s=180, label="150/90 target")
    axes[2].set(
        xlabel="Achieved SBP (mmHg)", ylabel="Achieved DBP (mmHg)",
        title="Pressure manifold and convergence cost",
    )
    axes[2].legend(frameon=False)
    fig.colorbar(scatter, ax=axes[2], label="Restabilisation wall time (s)")
    fig.savefig(FIGURE, dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resistance-values", required=True)
    parser.add_argument("--compliance-values", required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()

    directories()
    stage0_gate()
    standard_state()
    existing = load_existing()
    completed = {
        key(row.resistance_multiplier, row.compliance_multiplier)
        for row in existing.itertuples()
    } if not existing.empty else set()
    jobs = [
        {
            "grid_id": f"XR{r:.3f}_C{c:.3f}",
            "resistance_multiplier": r,
            "compliance_multiplier": c,
        }
        for r in values(args.resistance_values)
        for c in values(args.compliance_values)
        if key(r, c) not in completed
    ]
    frame = existing
    for start in range(0, len(jobs), args.batch_size):
        batch = jobs[start:start + args.batch_size]
        result = pd.DataFrame(parallel(
            batch, modifier_worker, min(args.workers, len(batch)),
            "Pulse extended boundary",
        ))
        frame = save(pd.concat([frame, result], ignore_index=True))
        summary = analyse(frame)
        plot(frame)
        print(json.dumps(summary, indent=2))
    if not jobs:
        summary = analyse(frame)
        plot(frame)
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
