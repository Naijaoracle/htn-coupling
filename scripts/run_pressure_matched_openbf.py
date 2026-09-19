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
import stage5_pipeline as stage5

SITES = stage5.SITES

OPENBF = Path(os.environ.get("OPENBF_ROOT", ROOT.parent / "openBF"))
BASE = OPENBF / "models/boileau2015/adan56/adan56.yaml"
RUNNER = ROOT / "scripts/run_stage4_openbf.jl"
V2 = ROOT / "results/pressure_matched_routes_v2"
SOURCE = V2 / "private/cases"
OUT = V2 / "coupled_openbf"
DIRECT = SOURCE / "direct_higher/stable_trace.csv.gz"


def selected_higher_modifier_trace() -> tuple[Path, dict]:
    primary = pd.read_csv(V2 / "primary_solutions.csv")
    higher = primary[primary.target.eq("higher")]
    if len(higher) != 1:
        raise RuntimeError("expected exactly one confirmed higher-target primary solution")
    row = higher.iloc[0]
    if not bool(row.rerun_pass) or not bool(row.stationarity_pass):
        raise RuntimeError("higher-target primary failed stationarity or independent confirmation")
    case_id = str(row.case_id)
    trace = SOURCE / f"rerun_{case_id}/stable_trace.csv.gz"
    if not trace.is_file():
        raise RuntimeError(f"missing independent confirmation trace for {case_id}")
    return trace, row.to_dict()


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
    return {"name": name,
            "source_trace": "{HTN_COUPLING_ROOT}/" + str(source.relative_to(ROOT)),
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


def attribution_tables(metric_frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compare the matched diagonal and factorial shapes to the saved inlet-perturbation benchmark."""
    noise = pd.read_csv(ROOT / "results/pressure_matched_routes/coupled_openbf/primary_noise_attribution.csv")
    floors = {(row.site, row.metric): float(row.stage4_6_perturbation_floor)
              for row in noise.itertuples(index=False)}
    direct_case = "direct_inlet_direct_resistance"
    modifier_case = "modifier_inlet_modifier_resistance"
    metrics = ("systolic_mmHg", "diastolic_mmHg", "mean_mmHg",
               "pulse_pressure_mmHg", "time_to_peak_phase")
    primary_rows = []
    for site in SITES:
        rows = metric_frame[metric_frame.vessel.eq(site)].set_index("case")
        direct, modifier = rows.loc[direct_case], rows.loc[modifier_case]
        for metric in metrics:
            difference = float(direct[metric] - modifier[metric])
            floor = floors[(site, metric)]
            primary_rows.append({
                "site": site, "metric": metric,
                "direct_route_value": float(direct[metric]),
                "modifier_route_value": float(modifier[metric]),
                "direct_minus_modifier": difference,
                "absolute_effect": abs(difference),
                "stage4_6_perturbation_floor": floor,
                "effect_to_floor_ratio": abs(difference) / floor,
                "attribution_threshold_ratio": 1.25,
                "clears_1p25x_floor": abs(difference) >= 1.25 * floor,
                "phase_shift_direct_vs_modifier": np.nan,
                "comparison": "direct inlet + direct WK3 resistance vs confirmed modifier inlet + modifier WK3 resistance",
            })
        direct_dir = OUT / "runs" / direct_case
        modifier_dir = OUT / "runs" / modifier_case
        _, direct_pressure = stage5.phase_pressure(direct_dir, site)
        _, modifier_pressure = stage5.phase_pressure(modifier_dir, site)
        shape, shift = stage5.aligned_shape_rmse(direct_pressure, modifier_pressure)
        floor = floors[(site, "phase_aligned_normalised_shape_rmse")]
        primary_rows.append({
            "site": site, "metric": "phase_aligned_normalised_shape_rmse",
            "direct_route_value": np.nan, "modifier_route_value": np.nan,
            "direct_minus_modifier": np.nan, "absolute_effect": shape,
            "stage4_6_perturbation_floor": floor,
            "effect_to_floor_ratio": shape / floor,
            "attribution_threshold_ratio": 1.25,
            "clears_1p25x_floor": shape >= 1.25 * floor,
            "phase_shift_direct_vs_modifier": shift,
            "comparison": "direct inlet + direct WK3 resistance vs confirmed modifier inlet + modifier WK3 resistance",
        })

    factorial_rows = []
    comparisons = [
        ("inlet", "direct", "direct_inlet_direct_resistance", "modifier_inlet_direct_resistance"),
        ("inlet", "modifier", "direct_inlet_modifier_resistance", "modifier_inlet_modifier_resistance"),
        ("resistance", "direct", "direct_inlet_direct_resistance", "direct_inlet_modifier_resistance"),
        ("resistance", "modifier", "modifier_inlet_direct_resistance", "modifier_inlet_modifier_resistance"),
    ]
    for site in SITES:
        floor = floors[(site, "phase_aligned_normalised_shape_rmse")]
        for factor, held, case_a, case_b in comparisons:
            _, pressure_a = stage5.phase_pressure(OUT / "runs" / case_a, site)
            _, pressure_b = stage5.phase_pressure(OUT / "runs" / case_b, site)
            shape, shift = stage5.aligned_shape_rmse(pressure_a, pressure_b)
            factorial_rows.append({
                "site": site, "changed_factor": factor, "held_factor_level": held,
                "case_a": case_a, "case_b": case_b,
                "phase_aligned_normalised_shape_rmse": shape,
                "optimal_phase_shift": shift,
                "stage4_6_perturbation_floor": floor,
                "effect_to_floor_ratio": shape / floor,
                "clears_1p25x_floor": shape >= 1.25 * floor,
            })
    primary = pd.DataFrame(primary_rows)
    factorial = pd.DataFrame(factorial_rows)
    primary.to_csv(OUT / "primary_noise_attribution.csv", index=False)
    factorial.to_csv(OUT / "factorial_shape_attribution.csv", index=False)
    return primary, factorial


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    direct = extract_inlet("direct_higher", DIRECT)
    modifier_trace, primary_solution = selected_higher_modifier_trace()
    modifier_name = f"modifier_higher_R{float(primary_solution['R']):.3f}_C{float(primary_solution['C']):.3f}"
    modifier = extract_inlet(modifier_name, modifier_trace)
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
    source_manifest = json.loads((V2 / "run_manifest.json").read_text())
    inlet_records = []
    for record in (direct, modifier):
        sanitized = dict(record)
        sanitized["inlet"] = "{HTN_COUPLING_ROOT}/" + str(Path(record["inlet"]).relative_to(ROOT))
        inlet_records.append(sanitized)
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "protocol": "{HTN_COUPLING_ROOT}/config/pressure_matched_route_v1.json",
        "protocol_amendment": "{HTN_COUPLING_ROOT}/docs/STAGE_MATCHED_ROUTE_AMENDMENT_4.md",
        "primary_solution": {key: primary_solution[key] for key in
                              ("target", "R", "C", "systolic_mmHg", "diastolic_mmHg",
                               "rerun_systolic_residual_mmHg", "rerun_diastolic_residual_mmHg")},
        "pulse_revision": source_manifest["pulse_revision"],
        "pulse_runtime_path": source_manifest.get("pulse_path"),
        "openbf_revision": subprocess.check_output(
            ["git", "-C", str(OPENBF), "rev-parse", "HEAD"], text=True).strip(),
        "coupling_revision": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
        "openbf_base_yaml": "{OPENBF_ROOT}/models/boileau2015/adan56/adan56.yaml",
        "wk3_outlets": outlets,
        "published_parallel_terminal_resistance_pa_s_m3": published_r,
        "svr_mmHg_s_mL": {"direct": direct["median_pulse_svr_mmHg_s_mL"],
                           "modifier": modifier["median_pulse_svr_mmHg_s_mL"]},
        "global_wk3_resistance_scales": scales,
        "inlets": inlet_records, "cases": cases,
        "design": "2x2 cross: direct/modifier flow inlet by direct/modifier global WK3 R scale; E and Cc held at published values; 15 cycles",
    }
    manifest["cases"] = []
    for item in cases:
        sanitized = dict(item)
        sanitized["yaml"] = "{HTN_COUPLING_ROOT}/" + str(Path(item["yaml"]).relative_to(ROOT))
        sanitized["inlet"] = "{HTN_COUPLING_ROOT}/" + str(Path(item["inlet"]).relative_to(ROOT))
        manifest["cases"].append(sanitized)
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
            # The protocol withdrew the reflected-wave detector endpoint.
            for key in ("reflected_wave_present", "reflected_wave_phase",
                        "augmentation_pressure_mmHg", "augmentation_index_pct"):
                m.pop(key, None)
            metrics.append({**m, "inlet_source": item["case"].split("_inlet_")[0],
                            "resistance_source": item["case"].split("_inlet_")[1].removesuffix("_resistance"),
                            "global_wk3_resistance_scale": item["global_wk3_resistance_scale"]})
    metric_frame = pd.DataFrame(metrics)
    metric_frame.to_csv(OUT / "waveform_metrics.csv", index=False)
    # Pairwise factorial contrasts: mean differences across the other factor.
    contrasts = []
    numeric = ["systolic_mmHg", "diastolic_mmHg", "mean_mmHg", "pulse_pressure_mmHg",
               "time_to_peak_phase"]
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
    primary_attribution, shape_attribution = attribution_tables(metric_frame)
    print(metric_frame.to_string(index=False))
    print("\nPrimary comparison vs Stage 4.6 inlet-perturbation benchmark:")
    print(primary_attribution[["site", "metric", "absolute_effect",
                               "stage4_6_perturbation_floor", "effect_to_floor_ratio",
                               "clears_1p25x_floor"]].to_string(index=False))
    print("\nFactorial shape contrasts:")
    print(shape_attribution.to_string(index=False))


if __name__ == "__main__":
    main()
