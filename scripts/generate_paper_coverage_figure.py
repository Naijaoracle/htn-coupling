#!/usr/bin/env python3
"""Generate the paper's cohort blood-pressure density figure.

The hexbin minimum is fixed at ten participants per visible cell for
disclosure control. The output contains only the rendered aggregate figure.
Set PULSE_ROOT to the local Pulse checkout that holds authorized cohort files.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_stage2_tier0 import load_elsa, load_haalsi  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    cohorts = {"HAALSI": load_haalsi(), "ELSA": load_elsa()}
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.3), constrained_layout=True)
    for axis, (name, frame) in zip(axes, cohorts.items()):
        pressure = frame.dropna(subset=["systolic_mmHg", "diastolic_mmHg"])
        axis.hexbin(
            pressure.systolic_mmHg,
            pressure.diastolic_mmHg,
            gridsize=35,
            mincnt=10,
            cmap="Greys",
            bins="log",
        )
        axis.add_patch(
            Rectangle((90, 60), 30, 20, fill=False, edgecolor="red", linewidth=2)
        )
        if name == "HAALSI":
            axis.text(
                108, 116, "Pulse default\nadmissibility box",
                color="red", ha="center", va="center", fontsize=10,
            )
        axis.set(
            title=name,
            xlabel="Systolic BP (mmHg)",
            ylabel="Diastolic BP (mmHg)",
            xlim=(75, 225),
            ylim=(30, 140),
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
