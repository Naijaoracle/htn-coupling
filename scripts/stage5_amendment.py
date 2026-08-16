#!/usr/bin/env python3
"""Run and analyse the predeclared Stage 5 amendment."""

from __future__ import annotations

import argparse
import json
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from tqdm import tqdm

from bridge_units import mmhg_s_per_ml_to_pa_s_per_m3
from prepare_stage4_openbf import equivalent_terminal_resistance
from stage5_pipeline import (BASE, OPENBF, OUT as STAGE5, PROTOCOL, ROOT,
                             RUNNER, SITES, aligned_shape_rmse, extract_one,
                             phase_pressure, waveform_metrics)

OUT = ROOT / "results/stage5_amendment"
SPEC = ROOT / "config/stage5_amendment_v1.json"


def taper_audit() -> dict:
    config = yaml.safe_load(BASE.read_text())
    rows = []
    for vessel in config["network"]:
        rp, rd = float(vessel["Rp"]), float(vessel["Rd"])
        # Reproduce openBF src/vessel.jl exactly. Julia isapprox uses the given
        # absolute tolerance here; the radii are far below its default rtol scale.
        solver_tapered = not np.isclose(rd, rp, atol=1e-4, rtol=0.0)
        rows.append({
            "vessel": vessel["label"], "Rp_m": rp, "Rd_m": rd,
            "radius_difference_m": abs(rp-rd),
            "geometrically_tapered": rp != rd,
            "solver_tapered": solver_tapered,
            "taper_pct": 100*(rp-rd)/rp,
        })
    frame = pd.DataFrame(rows)
    frame.to_csv(OUT/"adan56_taper_audit.csv", index=False)
    result = {
        "vessels_n": len(frame),
        "rp_rd_unequal_n": int(frame.geometrically_tapered.sum()),
        "openbf_solver_tapered_n": int(frame.solver_tapered.sum()),
        "solver_constant_radius_n": int((~frame.solver_tapered).sum()),
        "right_eca_solver_tapered": bool(frame.loc[frame.vessel == "external_carotid_R", "solver_tapered"].iloc[0]),
        "right_ica_solver_tapered": bool(frame.loc[frame.vessel == "internal_carotid_R", "solver_tapered"].iloc[0]),
        "paper_scope": (
            "Benemerito et al. 2024 describes constant mean radii in its "
            "Charlton healthy-ageing conversion. The shipped ADAN56 YAML and "
            "current v2 solver used here support and activate tapering."),
        "paper_url": "https://doi.org/10.1088/1361-6579/ad9663",
    }
    (OUT/"taper_audit_summary.json").write_text(json.dumps(result, indent=2)+"\n")
    return result


def extract_matched() -> dict:
    stage5 = pd.read_csv(STAGE5/"pulse_phenotypes.csv").set_index("phenotype")
    sweep = pd.read_csv(ROOT/"results/stage2/reachability_sweep.csv")
    hi = sweep[(sweep.resistance_multiplier == 1.05)&
               (sweep.compliance_multiplier == 1.0)].iloc[0]
    target = json.loads(SPEC.read_text())["map_target_mmHg"]
    lo_map = stage5.loc["normotensive", "map_mmHg"]
    resistance = 1.0 + 0.05*(target-lo_map)/(hi.achieved_map_mmHg-lo_map)
    result = extract_one("resistance_map_matched", {
        "resistance_multiplier": float(resistance),
        "compliance_multiplier": 1.0,
    })
    error = result["map_mmHg"]-target
    result["target_map_mmHg"] = target
    result["map_error_mmHg"] = error
    result["calibration_method"] = "linear interpolation from R=1.00 and R=1.05 endpoints"
    if abs(error) > json.loads(SPEC.read_text())["map_tolerance_mmHg"]:
        raise RuntimeError(f"First MAP-matched run missed by {error:.3f} mmHg; secant correction required")
    (OUT/"map_matched_pulse.json").write_text(json.dumps(result, indent=2)+"\n")
    pd.DataFrame([result]).to_csv(OUT/"map_matched_pulse.csv", index=False)
    return result


def is_central(label: str, patterns: list[str]) -> bool:
    return any(label.startswith(pattern) for pattern in patterns)


def write_case(name: str, inlet: Path, resistance_scale: float,
               central_scale: float = 1.0) -> dict:
    spec = json.loads(SPEC.read_text())
    case_dir = OUT/"configs"/name
    case_dir.mkdir(parents=True, exist_ok=True)
    inlet_out = case_dir/f"{name}_inlet.dat"
    inlet_out.write_bytes(inlet.read_bytes())
    config = yaml.safe_load(BASE.read_text())
    config["project_name"] = name
    config["inlet_file"] = inlet_out.name
    config["solver"]["cycles"] = 15
    central = []
    for vessel in config["network"]:
        if is_central(vessel["label"], spec["central_vessel_patterns"]):
            vessel["E"] *= central_scale
            central.append(vessel["label"])
        if vessel.get("outlet") == "wk3":
            vessel["R1"] *= resistance_scale
            vessel["R2"] *= resistance_scale
    path = case_dir/f"{name}.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False))
    return {"case": name, "yaml": str(path), "inlet": str(inlet_out),
            "terminal_resistance_scale": resistance_scale,
            "central_youngs_modulus_scale": central_scale,
            "central_vessels": central}


def prepare() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    audit = taper_audit()
    matched = extract_matched()
    config = yaml.safe_load(BASE.read_text())
    published_r, _ = equivalent_terminal_resistance(config)
    phenotypes = json.loads((STAGE5/"pulse_phenotypes.json").read_text())["phenotypes"]
    by_name = {x["phenotype"]: x for x in phenotypes}
    by_name["resistance_map_matched"] = matched
    cases = []
    scale = json.loads(SPEC.read_text())["youngs_modulus_scale"]
    for name in ("normotensive", "compliance_dominant", "combined"):
        meta = by_name[name]
        rscale = mmhg_s_per_ml_to_pa_s_per_m3(
            meta["systemic_vascular_resistance_mmHg_s_mL"])/published_r
        cases.append(write_case(f"{name}_central_E_2p5", Path(meta["inlet_file"]),
                                rscale, central_scale=scale))
    meta = matched
    rscale = mmhg_s_per_ml_to_pa_s_per_m3(
        meta["systemic_vascular_resistance_mmHg_s_mL"])/published_r
    cases.append(write_case("resistance_map_matched_published_walls",
                            Path(meta["inlet_file"]), rscale))
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "openbf_revision": subprocess.check_output(
            ["git", "-C", str(OPENBF), "rev-parse", "HEAD"], text=True).strip(),
        "taper_audit": audit, "matched_pulse": matched, "cases": cases,
    }
    (OUT/"run_manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    print(f"Prepared {len(cases)} amendment cases; matched R={matched['resistance_multiplier']:.6f}, MAP={matched['map_mmHg']:.3f}")


def run_one(item: dict) -> dict:
    result = OUT/"runs"/item["case"]
    result.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(["julia", f"--project={ROOT}", str(RUNNER),
                           item["yaml"], str(result)], text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (result/"runner.log").write_text(proc.stdout)
    return {"case": item["case"], "status": "ok" if proc.returncode == 0 else "failed",
            "returncode": proc.returncode}


def run(workers: int) -> None:
    jobs = json.loads((OUT/"run_manifest.json").read_text())["cases"]
    rows = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_one, job) for job in jobs]
        with tqdm(total=len(futures), desc="Stage 5 amendment openBF", unit="case") as bar:
            for future in as_completed(futures):
                row = future.result(); rows.append(row)
                bar.set_postfix(case=row["case"], status=row["status"]); bar.update()
    frame = pd.DataFrame(rows).sort_values("case")
    frame.to_csv(OUT/"run_status.csv", index=False)
    if not frame.status.eq("ok").all():
        raise RuntimeError("An amendment openBF case failed")


def first_fractional_fall(frame: pd.DataFrame, fraction: float) -> float:
    baseline = float(frame.loc[frame.time_s.between(0, 29), "map_mmHg"].median())
    values = frame.loc[frame.map_mmHg <= baseline*(1-fraction), "time_s"]
    return float(values.iloc[0]) if len(values) else np.nan


def analyse() -> None:
    spec = json.loads(SPEC.read_text())
    manifest = json.loads((OUT/"run_manifest.json").read_text())
    new_metrics = []
    for item in manifest["cases"]:
        for vessel in SITES:
            new_metrics.append(waveform_metrics(
                OUT/"runs"/item["case"], item["case"], vessel))
    new_metrics = pd.DataFrame(new_metrics)
    new_metrics.to_csv(OUT/"waveform_metrics.csv", index=False)
    old = pd.read_csv(STAGE5/"waveform_metrics.csv")

    comparison = []
    cases = {
        "normotensive": ("normotensive_arm1_inlet_only", "threshold_E_2p50", "normotensive_central_E_2p5"),
        "compliance_dominant": ("compliance_dominant_arm1_inlet_only", "compliance_dominant_arm2_matched_stiffening", "compliance_dominant_central_E_2p5"),
        "combined": ("combined_arm1_inlet_only", "combined_arm2_matched_stiffening", "combined_central_E_2p5"),
    }
    all_metrics = pd.concat([old, new_metrics], ignore_index=True)
    for phenotype, (base_case, uniform_case, central_case) in cases.items():
        for vessel in ("external_carotid_R", "internal_carotid_R"):
            indexed = all_metrics[all_metrics.vessel == vessel].set_index("case")
            for arm, case in (("inlet_only", base_case), ("uniform_E2p5", uniform_case),
                              ("central_only_E2p5", central_case)):
                row = indexed.loc[case]
                comparison.append({"phenotype": phenotype, "arm": arm, "case": case,
                                   "vessel": vessel,
                                   "pulse_pressure_mmHg": row.pulse_pressure_mmHg,
                                   "time_to_peak_phase": row.time_to_peak_phase,
                                   "reflected_wave_present": row.reflected_wave_present,
                                   "reflected_wave_phase": row.reflected_wave_phase,
                                   "augmentation_index_pct": row.augmentation_index_pct})
    comparison = pd.DataFrame(comparison)
    comparison.to_csv(OUT/"central_vs_uniform_stiffening.csv", index=False)

    direction = []
    for phenotype in cases:
        group = comparison[comparison.phenotype == phenotype]
        for vessel in ("external_carotid_R", "internal_carotid_R"):
            g = group[group.vessel == vessel].set_index("arm")
            for arm in ("uniform_E2p5", "central_only_E2p5"):
                pp = g.loc[arm, "pulse_pressure_mmHg"]-g.loc["inlet_only", "pulse_pressure_mmHg"]
                ref = g.loc[arm, "reflected_wave_phase"]-g.loc["inlet_only", "reflected_wave_phase"]
                aix = g.loc[arm, "augmentation_index_pct"]-g.loc["inlet_only", "augmentation_index_pct"]
                direction.append({"phenotype": phenotype, "vessel": vessel, "arm": arm,
                                  "delta_pp_mmHg": pp, "delta_reflected_wave_phase": ref,
                                  "delta_augmentation_index_pct": aix,
                                  "pp_widens": bool(pp > 0),
                                  "reflection_earlier": bool(np.isfinite(ref) and ref < 0),
                                  "augmentation_increases": bool(np.isfinite(aix) and aix > 0),
                                  "all_directions_pass": bool(pp > 0 and np.isfinite(ref) and ref < 0 and np.isfinite(aix) and aix > 0)})
    direction = pd.DataFrame(direction)
    direction.to_csv(OUT/"recognisability_direction_check.csv", index=False)

    noise = pd.read_csv(STAGE5/"metric_noise_floors.csv")
    matched_rows = []
    mcase = "resistance_map_matched_published_walls"
    ccase = "compliance_dominant_arm2_matched_stiffening"
    for vessel in ("external_carotid_R", "internal_carotid_R"):
        _, m = phase_pressure(OUT/"runs"/mcase, vessel)
        _, c = phase_pressure(STAGE5/"runs"/ccase, vessel)
        rmse, shift = aligned_shape_rmse(m, c)
        floor = noise[(noise.vessel == vessel)&
                      (noise.metric == "phase_aligned_normalised_shape_rmse")].noise_floor.iloc[0]
        matched_rows.append({"vessel": vessel, "shape_rmse": rmse,
                             "optimal_phase_shift": shift, "shape_noise_floor": floor,
                             "attribution_ratio": rmse/floor,
                             "clears_1p25x_floor": rmse/floor >= 1.25})
    matched_shape = pd.DataFrame(matched_rows)
    matched_shape.to_csv(OUT/"map_matched_mechanism_separation.csv", index=False)

    acute = pd.read_csv(STAGE5/"acute_body_results.csv")
    fractions = []
    for _, result in acute.iterrows():
        trace = pd.read_csv(STAGE5/"private/acute"/f"{result.body_id}__{result.phenotype}.csv.gz")
        baseline = float(trace.loc[trace.time_s.between(0, 29), "map_mmHg"].median())
        row = {"body_id": result.body_id, "phenotype": result.phenotype,
               "baseline_map_mmHg": baseline}
        for fraction in spec["fractional_map_falls"]:
            row[f"time_to_{int(fraction*100)}pct_map_fall_s"] = first_fractional_fall(trace, fraction)
        fractions.append(row)
    fractions = pd.DataFrame(fractions)
    fractions.to_csv(OUT/"acute_fractional_map_falls.csv", index=False)
    aggregate = fractions.groupby("phenotype").agg(
        bodies_n=("body_id", "size"),
        baseline_map_median_mmHg=("baseline_map_mmHg", "median"),
        time_to_20pct_fall_median_s=("time_to_20pct_map_fall_s", "median"),
        time_to_30pct_fall_median_s=("time_to_30pct_map_fall_s", "median"),
        time_to_40pct_fall_median_s=("time_to_40pct_map_fall_s", "median"),
    ).reset_index()
    aggregate.to_csv(OUT/"acute_fractional_map_fall_summary.csv", index=False)

    central_direction = direction[direction.arm == "central_only_E2p5"]
    gate = bool(central_direction.all_directions_pass.all())
    matched = json.loads((OUT/"map_matched_pulse.json").read_text())
    audit = json.loads((OUT/"taper_audit_summary.json").read_text())
    result = {
        "taper_audit": audit,
        "map_matched_resistance_multiplier": matched["resistance_multiplier"],
        "map_matched_pulse_map_mmHg": matched["map_mmHg"],
        "map_target_error_mmHg": matched["map_error_mmHg"],
        "map_matched_shape_clears_floor_both_sites": bool(matched_shape.clears_1p25x_floor.all()),
        "central_only_recognisability_gate_passed": gate,
        "original_no_recognisable_signature_conclusion_overturned": gate,
    }
    (OUT/"stage5_amendment_summary.json").write_text(json.dumps(result, indent=2)+"\n")
    write_report(result, comparison, direction, matched_shape, aggregate)
    print(json.dumps(result, indent=2))


def write_report(result, comparison, direction, matched_shape, acute_summary):
    audit = result["taper_audit"]
    central = direction[direction.arm == "central_only_E2p5"]
    text = f"""# Stage 5 amendment: taper, stiffness gradient, and matched comparisons

## Decision

The original Stage 5 conclusion is **{'overturned' if result['original_no_recognisable_signature_conclusion_overturned'] else 'not overturned'}** under the predeclared amendment rule. The numerical shape signal remains real; the question here is whether central-only stiffening restores wider pulse pressure, earlier identifiable reflection, and increased augmentation at both carotids.

## Taper audit

The shipped ADAN56 network is not globally constant-radius. Of {audit['vessels_n']} vessels, {audit['rp_rd_unequal_n']} have unequal `Rp`/`Rd`, and the current openBF solver actively classifies {audit['openbf_solver_tapered_n']} as tapered. Both terminal right carotid segments are constant-radius. The openBF validation paper's documented underprediction arose in its Charlton healthy-ageing conversion, where taper was replaced by a mean constant radius ([Benemerito et al., 2024](https://doi.org/10.1088/1361-6579/ad9663)); that limitation is not directly the configuration used here. No unsourced taper was added.

## Central-only versus uniform stiffening

Central vessels were the aortic arch, thoracic and abdominal aorta, brachiocephalic trunk, and bilateral common carotids. All other vessel `E` and every WK3 `Cc` remained published.

{comparison.to_markdown(index=False, floatfmt='.4f')}

{direction.to_markdown(index=False, floatfmt='.4f')}

The amendment gate requires all three directions at both sites; an absent secondary extremum is unassessable, not a pass.

## MAP-matched mechanism comparison

Linear interpolation selected Pulse resistance multiplier {result['map_matched_resistance_multiplier']:.6f}. It achieved MAP {result['map_matched_pulse_map_mmHg']:.3f} mmHg, {result['map_target_error_mmHg']:+.3f} mmHg from the compliance-dominant target.

{matched_shape.to_markdown(index=False, floatfmt='.4f')}

This removes the 24 mmHg Pulse MAP gap. It matches mean pressure, not systolic/diastolic severity.

## Fractional acute endpoints

Baseline is each run's median MAP over scenario seconds 0–29. Crossings are relative to that run and missing values are not imputed.

{acute_summary.to_markdown(index=False, floatfmt='.3f')}

These fractional endpoints should accompany, and take interpretive precedence over, the absolute MAP-65 ordering when baseline pressures differ.
"""
    (ROOT/"docs/STAGE5_AMENDMENT.md").write_text(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "run", "analyse"))
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.mode == "prepare": prepare()
    elif args.mode == "run": run(args.workers)
    else: analyse()


if __name__ == "__main__":
    main()
