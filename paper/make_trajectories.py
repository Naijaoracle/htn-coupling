"""Build median haemorrhage trajectories for the 20-body expanded panel.

Reads the 80 per-run compressed Pulse CSVs under results/stage5/private/acute/
(files named expanded_*).  Produces fig_trajectories.png (MAP, HR, CO, SVR)
and prints checkpoint statistics for the manuscript text.
"""
from __future__ import annotations

import glob
from pathlib import Path

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
ACUTE = _env_dir("HTN_RESULTS") / "stage5" / "private" / "acute"

plt.rcParams.update({
    "font.size": 8.5,
    "axes.titlesize": 9,
    "axes.labelsize": 8.5,
    "legend.fontsize": 8,
    "figure.dpi": 150,
})

COLS = ["time_s", "map_mmHg", "heart_rate_per_min",
        "cardiac_output_L_min", "systemic_vascular_resistance_mmHg_s_mL"]
VAR = {
    "map_mmHg": "MAP (mmHg)",
    "heart_rate_per_min": "Heart rate (/min)",
    "cardiac_output_L_min": "Cardiac output (L/min)",
    "systemic_vascular_resistance_mmHg_s_mL": "SVR (mmHg\u00b7s/mL)",
}
ORDER = ["normotensive", "resistance_dominant", "compliance_dominant", "combined"]
COLOR = {"normotensive": "#999999", "resistance_dominant": "#2166ac",
         "compliance_dominant": "#b2182b", "combined": "#222222"}
LABEL = {"normotensive": "Normotensive", "resistance_dominant": "Resistance-only",
         "compliance_dominant": "Compliance-only", "combined": "Combined"}
BLEED = (30.0, 655.0)
XMAX = 900.0

files = sorted(glob.glob(str(ACUTE / "expanded_*__*.csv.gz")))
assert len(files) == 80, f"expected 80 expanded runs, found {len(files)}"

# per-file per-second medians
per_second = []
for f in files:
    d = pd.read_csv(f, usecols=COLS)
    d["sec"] = np.floor(d["time_s"]).astype(int)
    agg = d.groupby("sec")[list(VAR)].median()
    name = Path(f).name.replace(".csv.gz", "").split("__")
    agg["body_id"] = name[0]
    agg["phenotype"] = name[1]
    per_second.append(agg.reset_index())
panel = pd.concat(per_second, ignore_index=True)

# median across the 20 bodies, per phenotype per second
traj = panel.groupby(["phenotype", "sec"])[list(VAR)].median().reset_index()
traj = traj[traj["sec"] <= XMAX]

fig, axes = plt.subplots(2, 2, figsize=(7.2, 6.0), sharex=True)
for ax, (var, ylab) in zip(axes.flat, VAR.items()):
    for p in ORDER:
        sub = traj[traj["phenotype"] == p]
        ax.plot(sub["sec"], sub[var], color=COLOR[p], lw=1.2, label=LABEL[p])
    ax.axvspan(BLEED[0], BLEED[1], color="#d9d9d9", alpha=0.55, lw=0)
    ax.set_ylabel(ylab)
    ax.set_xlim(0, XMAX)
axes[0, 0].set_title("Median trajectories across 20 bodies (grey band: 200 mL/min bleed)")
axes[1, 0].set_xlabel("Scenario time (s)")
axes[1, 1].set_xlabel("Scenario time (s)")
axes[1, 0].legend(frameon=False, ncol=2, loc="lower left")
fig.tight_layout()
axes[0, 0].text(0.02, -0.32, "Active runs (300/600/900 s): Norm 20/13/0, Res 20/9/0, Comp 20/13/0, Comb 20/13/0", transform=axes[0, 0].transAxes, fontsize=7, ha="left", va="top", clip_on=False)
fig.savefig(PAPER / "fig_trajectories.png", bbox_inches="tight")
plt.close(fig)

# checkpoint statistics for the text
print("checkpoint medians (across 20 bodies per phenotype):")
for p in ORDER:
    sub = traj[traj["phenotype"] == p]
    def at(t):
        row = sub[sub["sec"] == t]
        return row.iloc[0] if len(row) else None
    rows = {t: at(t) for t in (30, 300, 655, 900)}
    hr_peak = sub[sub["sec"].between(30, 655)]["heart_rate_per_min"].max()
    print(
        f"  {p:22s} "
        + " | ".join(
            f"t{t}: MAP {rows[t]['map_mmHg']:.0f}, HR {rows[t]['heart_rate_per_min']:.0f}, "
            f"CO {rows[t]['cardiac_output_L_min']:.2f}, SVR {rows[t]['systemic_vascular_resistance_mmHg_s_mL']:.2f}"
            if rows[t] is not None else f"t{t}: (ended)"
            for t in (30, 655, 900)
        )
    )
    print(f"    HR peak during bleed: {hr_peak:.0f} /min")
print("done")
