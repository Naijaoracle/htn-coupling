#!/usr/bin/env python3
"""Run the planned 2x2 Pulse-inlet by WK3-resistance OpenBF comparison."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from bridge_units import mmhg_s_per_ml_to_pa_s_per_m3
from extract_stage4_pulse_inlet import average_cycles
from prepare_stage4_openbf import equivalent_terminal_resistance
from stage5_pipeline import SITES, waveform_metrics

OPENBF = Path(os.environ.get("OPENBF_ROOT", ROOT.parent / "openBF"))
BASE = OPENBF / "models/boileau2015/adan56/adan56.yaml"
RUNNER = ROOT / "scripts/run_stage4_openbf.jl"
SOURCE = ROOT / "results/pressure_matched_routes/private/cases"
OUT = ROOT / "results/pressure_matched_routes/coupled_openbf"
DIRECT = SOURCE / "direct_higher/stable_trace.csv.gz"
MODIFIER = SOURCE / "confirm_higher_3_R1.995_C0.465/stable_trace.csv.gz"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def extract_inlet(name: str, source: Path) -> dict:
    frame = pd.read_csv(source)
    # Archived coupling traces omit aortic pressure. OpenBF uses a flow-only inlet;
    # this unused placeholder only satisfies the shared cycle helper.
    frame["aorta_pressure_mmHg"] = 0.0
    t, flow_ml_s, pressure, periods, rmses = average_cycles(frame, 8, 201)
    flow_m3_s = flow_ml_s * 1e-6
    flow_m3_s[np.abs(flow_m3_s) < 1e-10] = 1e-10
    path = OUT / "inlets" / f"{name}.dat"
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savetxt(path, np.column_stack((t, flow_m3_s)), fmt="%.12g")
    (OUT / "inlets" / f"{name}_representative_cycle.csv").write_text(
        pd.DataFrame({"time_s": t, "flow_mL_s": flow_ml_s,
                      "pressure_mmHg": pressure}).to_csv(index=False))
    integral_co = float(np.trapz(flow_ml_s, t) / t[-1] * 0.06)
    reported_co = float(frame.cardiac_output_L_min.median())
    rel_error = abs(integral_co - reported_co) / reported_co
    max_rmse = float(np.max(rmses) / np.max(flow_ml_s))
    if rel_error > 0.01:
        raise RuntimeError(f"{name} flow integral differs from Pulse CO by {rel_error:.3%}")
    return {"name": name, "source_trace": str(source),
            "source_trace_sha256": sha256(source), "inlet": str(path),
            "inlet_sha256": sha256(path), "cycles_averaged": len(periods),
            "cycle_period_s": float(t[-1]), "pulse_reported_co_L_min": reported_co,
            "aortic_pressure_in_source_trace": False,
            "median_pulse_svr_mmHg_s_mL": float(frame.svr_mmHg_s_mL.median()),
            "inlet_integral_co_L_min": integral_co,
            "flow_integral_relative_error": rel_error,
            "max_cycle_flow_rmse_fraction_of_peak": max_rmse}


def write_config(case: str, inlet: Path, scale: float) -> dict:
    case_dir = OUT / "configs" / case
    case_dir.mkdir(parents=True, exist_ok=True)
    inlet_copy = case_dir / f"{case}_inlet.dat"
    inlet_copy.write_bytes(inlet.read_bytes())
    config = yaml.safe_load(BASE.read_text())
    config["project_name"] = case
    config["inlet_file"] = inlet_copy.name
    config["solver"]["cycles"] = 15
    for vessel in config["network"]:
        if vessel.get("outlet") == "wk3":
            vessel["R1"] *= scale
            vessel["R2"] *= scale
    yaml_path = case_dir / f"{case}.yaml"
    yaml_path.write_text(yaml.safe_dump(config, sort_keys=False))
    return {"case": case, "yaml": str(yaml_path), "inlet": str(inlet_copy),
            "inlet_sha256": sha256(inlet_copy), "global_wk3_resistance_scale": scale,
            "wall_youngs_modulus_scale": 1.0, "terminal_compliance_scale": 1.0}


def run_case(item: dict) -> dict:
    result = OUT / "runs" / item["case"]
    result.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    proc = subprocess.run(["julia", f"--project={ROOT}", str(RUNNER),
                           item["yaml"], str(result)], text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (result / "runner.log").write_text(proc.stdout)
    elapsed = time.monotonic() - started
    if proc.returncode:
        return {"case": item["case"], "status": "failed", "returncode": proc.returncode,
                "wall_s": elapsed}
    return {"case": item["case"], "status": "ok", "returncode": 0,
            "wall_s": elapsed}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    direct = extract_inlet("direct_higher", DIRECT)
    modifier = extract_inlet("modifier_higher_R1.995_C0.465", MODIFIER)
    base = yaml.safe_load(BASE.read_text())
    published_r, outlets = equivalent_terminal_resistance(base)
    scales = {
        "direct": mmhg_s_per_ml_to_pa_s_per_m3(
            direct["median_pulse_svr_mmHg_s_mL"]) / published_r,
        "modifier": mmhg_s_per_ml_to_pa_s_per_m3(
            modifier["median_pulse_svr_mmHg_s_mL"]) / published_r,
    }
    inlets = {"direct": Path(direct["inlet"]),
              "modifier": Path(modifier["inlet"])}
    cases = []
    for inlet_label, inlet in inlets.items():
        for resistance_label, scale in scales.items():
            cases.append(write_config(f"{inlet_label}_inlet_{resistance_label}_resistance",
                                      inlet, scale))
    source_manifest = json.loads((ROOT / "results/pressure_matched_routes/run_manifest.json").read_text())
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "protocol": str(ROOT / "config/pressure_matched_route_v1.json"),
        "pulse_revision": source_manifest["pulse_revision"],
        "pulse_runtime_path": source_manifest.get("pulse_path"),
        "openbf_revision": subprocess.check_output(
            ["git", "-C", str(OPENBF), "rev-parse", "HEAD"], text=True).strip(),
        "coupling_revision": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
        "openbf_base_yaml": str(BASE), "wk3_outlets": outlets,
        "published_parallel_terminal_resistance_pa_s_m3": published_r,
        "svr_mmHg_s_mL": {"direct": direct["median_pulse_svr_mmHg_s_mL"],
                           "modifier": modifier["median_pulse_svr_mmHg_s_mL"]},
        "global_wk3_resistance_scales": scales,
        "inlets": [direct, modifier], "cases": cases,
        "design": "2x2 cross: direct/modifier flow inlet by direct/modifier global WK3 R scale; E and Cc held at published values; 15 cycles",
    }
    (OUT / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    run_rows = [run_case(item) for item in cases]
    pd.DataFrame(run_rows).to_csv(OUT / "run_status.csv", index=False)
    if any(row["status"] != "ok" for row in run_rows):
        raise RuntimeError("OpenBF run failure; see run_status.csv and per-case runner.log")
    metrics = []
    for item in cases:
        run_dir = OUT / "runs" / item["case"]
        for site in SITES:
            m = waveform_metrics(run_dir, item["case"], site)
            metrics.append({**m, "inlet_source": item["case"].split("_inlet_")[0],
                            "resistance_source": item["case"].split("_inlet_")[1].removesuffix("_resistance"),
                            "global_wk3_resistance_scale": item["global_wk3_resistance_scale"]})
    metric_frame = pd.DataFrame(metrics)
    metric_frame.to_csv(OUT / "waveform_metrics.csv", index=False)
    # Pairwise factorial contrasts: mean differences across the other factor.
    contrasts = []
    numeric = ["systolic_mmHg", "diastolic_mmHg", "mean_mmHg", "pulse_pressure_mmHg",
               "time_to_peak_phase", "augmentation_pressure_mmHg", "augmentation_index_pct"]
    for site in SITES:
        site_frame = metric_frame[metric_frame.vessel == site]
        for metric in numeric:
            pivot = site_frame.pivot(index="inlet_source", columns="resistance_source", values=metric)
            contrasts.append({"vessel": site, "metric": metric,
                              "inlet_effect_direct_minus_modifier_mean_over_R": float(
                                  ((pivot.loc["direct"] - pivot.loc["modifier"]).mean())),
                              "resistance_effect_direct_minus_modifier_mean_over_inlet": float(
                                  ((pivot["direct"] - pivot["modifier"]).mean())),
                              "interaction_difference_in_differences": float(
                                  (pivot.loc["direct", "direct"] - pivot.loc["modifier", "direct"])
                                  - (pivot.loc["direct", "modifier"] - pivot.loc["modifier", "modifier"]))})
    pd.DataFrame(contrasts).to_csv(OUT / "factorial_contrasts.csv", index=False)
    print(metric_frame.to_string(index=False))


if __name__ == "__main__":
    main()
