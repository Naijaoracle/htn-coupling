"""Generate paper figures and mechanism statistics for the hypertension paper.

Inputs (read-only):
  HAALSI Wave 1 tab file (published derived pressures)
  ELSA Wave 8/9 nurse tab file (wave 8 subset, validity rule from stage 1)
  stage5_followup expanded acute CSVs (fractional endpoints, run results)

Outputs:
  paper/coverage_scatter.csv         per-participant SBP/DBP, no identifiers
  paper/fig_coverage.png             two-panel scatter with Pulse box
  paper/fig_sensitivity.png          paired-difference medians at 20/30/40%
  paper/fig_p3.png                   baroreflex gain trace-audit values
  stdout summary for the manuscript text
"""
from __future__ import annotations

import csv
from pathlib import Path
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import os


def _env_dir(name):
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Set {name}; see README (Data access).")
    return Path(value)


PAPER = Path(__file__).resolve().parent
HAALSI_TAB = _env_dir("HTN_HAALSI_TAB")
ELSA_TAB_DIR = _env_dir("HTN_ELSA_TAB_DIR")
FOLLOWUP = _env_dir("HTN_RESULTS") / "stage5_followup"

plt.rcParams.update({
    "font.size": 9,
    "axes.titlesize": 9,
    "axes.labelsize": 9,
    "legend.fontsize": 8,
    "figure.dpi": 150,
})

# ---------------------------------------------------------------- cohorts
haalsi = pd.read_csv(
    HAALSI_TAB,
    sep="\t",
    usecols=["c_bs_mean_sys", "c_bs_mean_dia"],
    low_memory=False,
)
haalsi = haalsi.dropna()
assert len(haalsi) == 4895, len(haalsi)

elsa = pd.read_csv(
    ELSA_TAB_DIR / "wave_8_elsa_nurse_data_eul_v1.tab",
    sep="\t",
    usecols=["idauniq", "bprespc", "sysval", "diaval"],
    low_memory=False,
)
valid = (elsa["bprespc"] == 1) & (elsa["sysval"] > 0) & (elsa["diaval"] > 0)
elsa = elsa.loc[valid, ["sysval", "diaval"]].dropna()
assert len(elsa) == 3317, len(elsa)
print(f"cohorts: haalsi n={len(haalsi)}, elsa w8 n={len(elsa)}")

rows = []
for cohort, frame in (("HAALSI", haalsi), ("ELSA", elsa)):
    for sbp, dbp in zip(frame.iloc[:, 0], frame.iloc[:, 1]):
        rows.append((cohort, float(sbp), float(dbp)))
with open(PAPER / "coverage_scatter.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["cohort", "systolic_mmHg", "diastolic_mmHg"])
    w.writerows(rows)

# ---------------------------------------------------------------- coverage figure
fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.1), sharex=True, sharey=True)
box_x = (90, 120)
box_y = (60, 80)
for ax, cohort in zip(axes, ("HAALSI", "ELSA")):
    frame = haalsi if cohort == "HAALSI" else elsa
    ax.hexbin(
        frame.iloc[:, 0], frame.iloc[:, 1],
        gridsize=48, cmap="Greys", bins="log", mincnt=1,
    )
    ax.plot(box_x, [box_y[0], box_y[0]], color="#c1272d", lw=1.4)
    ax.plot(box_x, [box_y[1], box_y[1]], color="#c1272d", lw=1.4)
    ax.plot([box_x[0], box_x[0]], box_y, color="#c1272d", lw=1.4)
    ax.plot([box_x[1], box_x[1]], box_y, color="#c1272d", lw=1.4)
    ax.set_title(cohort)
    ax.set_xlabel("Systolic BP (mmHg)")
    ax.set_xlim(60, 230)
    ax.set_ylim(30, 140)
axes[0].set_ylabel("Diastolic BP (mmHg)")
axes[0].annotate(
    "Pulse default\nadmissibility box", xy=(105, 118), ha="center",
    fontsize=7.5, color="#c1272d",
)
fig.tight_layout()
fig.savefig(PAPER / "fig_coverage.png")
plt.close(fig)

# ---------------------------------------------------------------- threshold sensitivity
endpoints = pd.read_csv(FOLLOWUP / "expanded_acute_fractional_endpoints.csv")
phenotypes = ["resistance_dominant", "compliance_dominant", "combined"]
thresholds = ["20", "30", "40"]
medians = {}
paired = {}
for p in phenotypes + ["normotensive"]:
    sub = endpoints[endpoints["phenotype"] == p]
    medians[p] = {
        t: float(sub[f"time_to_{t}pct_map_fall_s"].median())
        for t in thresholds
    }
for p in phenotypes:
    sub = endpoints[endpoints["phenotype"] == p]
    norm = endpoints[endpoints["phenotype"] == "normotensive"]
    by_body = norm.set_index("body_id")
    diffs = {}
    for t in thresholds:
        d = [
            float(r[f"time_to_{t}pct_map_fall_s"])
            - float(by_body.loc[r["body_id"], f"time_to_{t}pct_map_fall_s"])
            for _, r in sub.iterrows()
        ]
        diffs[t] = d
    paired[p] = diffs

print("\nmedian endpoint (s) by threshold:")
for p in phenotypes + ["normotensive"]:
    print(f"  {p:22s} " + "  ".join(f"{t}%: {medians[p][t]:.1f}" for t in thresholds))
print("\npaired median difference vs control (s) and direction:")
for p in phenotypes:
    for t in thresholds:
        d = paired[p][t]
        direction = "earlier" if np.median(d) < 0 else "later"
        n = int(np.sum(np.sign(d) == np.sign(np.median(d))))
        print(f"  {p:22s} {t}%: median {np.median(d):+.1f}  {direction} {n}/20")

fig, ax = plt.subplots(figsize=(5.0, 3.0))
width = 0.26
colors = {"resistance_dominant": "#2166ac", "compliance_dominant": "#b2182b",
          "combined": "#4d4d4d"}
labels = {"resistance_dominant": "Resistance-only",
          "compliance_dominant": "Compliance-only", "combined": "Combined"}
x = np.arange(len(thresholds))
for i, p in enumerate(phenotypes):
    vals = [np.median(paired[p][t]) for t in thresholds]
    ax.bar(x + (i - 1) * width, vals, width, color=colors[p],
           label=labels[p], edgecolor="white")
ax.axhline(0, color="black", lw=0.8)
ax.set_xticks(x)
ax.set_xticklabels(["20%", "30%", "40%"])
ax.set_xlabel("Endpoint threshold (fall from own baseline MAP)")
ax.set_ylabel("Paired median difference\nfrom control (s)")
ax.set_ylim(-70, 15)
ax.legend(frameon=False, ncol=3, loc="lower right", bbox_to_anchor=(1.0, -0.32))
fig.tight_layout()
fig.savefig(PAPER / "fig_sensitivity.png", bbox_inches="tight")
plt.close(fig)

# ---------------------------------------------------------------- P3 audit figure
fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.7))
pre_gains = ["0.40", "1.0"]
pre_hr = [1.435, 1.386]
pre_r = [1.238, 1.227]
post_gains = ["0.40", "1.0", "2.0"]
post_hr = [0.839, 1.048, 1.614]
post_r = [0.895, 1.022, 1.628]
x_pre = np.arange(len(pre_gains))
x_post = np.arange(len(post_gains))
w = 0.35
axes[0].bar(x_pre - w / 2, pre_hr, w, label="HR scale", color="#2166ac")
axes[0].bar(x_pre + w / 2, pre_r, w, label="Resistance scale", color="#b2182b")
axes[0].set_title("Before correction (300 s)")
axes[0].set_xticks(x_pre, pre_gains)
axes[0].set_xlabel("Gain")
axes[0].set_ylabel("Effector scale")
axes[0].set_ylim(0, 1.7)
axes[0].legend(frameon=False, ncol=2)
axes[1].bar(x_post - w / 2, post_hr, w, label="HR scale", color="#2166ac")
axes[1].bar(x_post + w / 2, post_r, w, label="Resistance scale", color="#b2182b")
axes[1].set_title("After drive-only correction (60 s)")
axes[1].set_xticks(x_post, post_gains)
axes[1].set_xlabel("Gain")
axes[1].set_ylim(0, 1.7)
axes[1].legend(frameon=False, ncol=2)
fig.tight_layout()
fig.savefig(PAPER / "fig_p3.png")
plt.close(fig)

# ---------------------------------------------------------------- mechanism checkpoints
runs = pd.read_csv(FOLLOWUP / "expanded_acute_run_results.csv")
print("\nmedian checkpoint values by phenotype:")
for p in ["normotensive", "resistance_dominant", "compliance_dominant", "combined"]:
    sub = runs[runs["phenotype"] == p]
    sub_e = endpoints[endpoints["phenotype"] == p]
    print(
        f"  {p:22s} baseline MAP {sub_e['baseline_map_mmHg'].median():.1f} mmHg | "
        f"min CO {sub['minimum_cardiac_output_L_min'].median():.2f} L/min | "
        f"max HR {sub['maximum_heart_rate_per_min'].median():.0f} /min | "
        f"shock time {sub['time_to_hypovolemic_shock_s'].median():.0f} s (n={sub['time_to_hypovolemic_shock_s'].notna().sum()})"
    )
print("\ndone")
