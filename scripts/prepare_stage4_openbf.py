#!/usr/bin/env python3
"""Generate ADAN56 bridge configurations without modifying openBF."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

import numpy as np
import yaml

from bridge_units import mmhg_s_per_ml_to_pa_s_per_m3

ROOT = Path(__file__).resolve().parents[1]
OPENBF = Path(os.environ.get("OPENBF_ROOT", ROOT.parent / "openBF"))
BASE = OPENBF / "models/boileau2015/adan56/adan56.yaml"
OUT = ROOT / "results/stage4"
CONFIGS = OUT / "configs"


def equivalent_terminal_resistance(config):
    totals = [v["R1"] + v["R2"] for v in config["network"]
              if v.get("outlet") == "wk3"]
    if not totals:
        raise RuntimeError("No ADAN56 WK3 outlets found")
    return 1.0 / sum(1.0 / value for value in totals), len(totals)


def write_case(name, inlet, resistance_scale=1.0,
               flow_scale=1.0, period_scale=1.0):
    case_dir = CONFIGS / name
    case_dir.mkdir(parents=True, exist_ok=True)
    data = np.loadtxt(inlet)
    data[:, 0] *= period_scale
    data[:, 1] *= flow_scale
    inlet_name = f"{name}_inlet.dat"
    np.savetxt(case_dir / inlet_name, data, fmt="%.12g")
    config = yaml.safe_load(BASE.read_text())
    config["project_name"] = name
    config["inlet_file"] = inlet_name
    config["solver"]["cycles"] = 15
    for vessel in config["network"]:
        if vessel.get("outlet") == "wk3":
            vessel["R1"] *= resistance_scale
            vessel["R2"] *= resistance_scale
            # Deliberate: Cc stays published to isolate resistance matching.
    path = case_dir / f"{name}.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False))
    return {
        "case": name, "yaml": str(path), "inlet": str(case_dir / inlet_name),
        "terminal_resistance_scale": resistance_scale,
        "terminal_compliance_scale": 1.0,
        "inlet_flow_scale": flow_scale, "cardiac_period_scale": period_scale,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["base", "sensitivity"])
    args = parser.parse_args()
    metadata = json.loads((OUT / "pulse_inlet_metadata.json").read_text())
    inlet = Path(metadata["inlet_file"])
    config = yaml.safe_load(BASE.read_text())
    published_r, outlets = equivalent_terminal_resistance(config)
    pulse_r = mmhg_s_per_ml_to_pa_s_per_m3(
        metadata["systemic_vascular_resistance_mmHg_s_mL"])
    factor = pulse_r / published_r
    if args.mode == "base":
        cases = [write_case("stage4_unscaled", inlet),
                 write_case("stage4_scaled", inlet, resistance_scale=factor)]
    else:
        gate = json.loads((OUT / "aortic_gate.json").read_text())
        if not gate["passed"]:
            raise RuntimeError("Aortic gate failed; sensitivity runs are blocked")
        preferred = ("stage4_scaled" if gate["arms"]["scaled"]["passed"]
                     else "stage4_unscaled")
        rscale = factor if preferred == "stage4_scaled" else 1.0
        cases = [
            write_case("sensitivity_flow_low", inlet, rscale, flow_scale=0.95),
            write_case("sensitivity_flow_high", inlet, rscale, flow_scale=1.05),
            write_case("sensitivity_period_low", inlet, rscale, period_scale=0.95),
            write_case("sensitivity_period_high", inlet, rscale, period_scale=1.05),
        ]
    manifest = {
        "mode": args.mode,
        "openbf_revision": subprocess.check_output(
            ["git", "-C", str(OPENBF), "rev-parse", "HEAD"], text=True).strip(),
        "base_yaml": str(BASE), "wk3_outlets": outlets,
        "published_parallel_terminal_resistance_pa_s_m3": published_r,
        "pulse_systemic_resistance_pa_s_m3": pulse_r,
        "global_resistance_scale": factor,
        "compliance_decision": "published Cc unchanged in both arms",
        "cases": cases,
    }
    (OUT / f"{args.mode}_config_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
