#!/usr/bin/env python3
"""Create the mechanism, plausibility, acute, and narrative Stage 5 outputs."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from stage5_pipeline import OUT, SITES, aligned_shape_rmse, phase_pressure

ROOT = Path(__file__).resolve().parents[1]


def shape_between(case_a: str, case_b: str, vessel: str) -> float:
    _, a = phase_pressure(OUT/"runs"/case_a, vessel)
    _, b = phase_pressure(OUT/"runs"/case_b, vessel)
    return aligned_shape_rmse(a, b)[0]


def main() -> None:
    metrics = pd.read_csv(OUT/"waveform_metrics.csv")
    noise = pd.read_csv(OUT/"metric_noise_floors.csv")
    pulse = pd.read_csv(OUT/"pulse_phenotypes.csv")
    acute = pd.read_csv(OUT/"acute_body_results.csv")
    thresholds = pd.read_csv(OUT/"stiffness_shape_threshold.csv")
    terminal = pd.read_csv(OUT/"ica_eca_terminal_diagnostic.csv")
    low = pd.read_csv(OUT/"low_pulsatility_check.csv")
    summary = json.loads((OUT/"coupled_summary.json").read_text())

    mechanism = []
    for arm in ("arm1_inlet_only", "arm2_matched_stiffening"):
        rcase = f"resistance_dominant_{arm}"
        ccase = f"compliance_dominant_{arm}"
        for vessel in ("external_carotid_R", "internal_carotid_R"):
            effect = shape_between(rcase, ccase, vessel)
            floor = noise[(noise.vessel == vessel)&
                          (noise.metric == "phase_aligned_normalised_shape_rmse")].noise_floor.iloc[0]
            mechanism.append({"arm": arm, "vessel": vessel,
                              "normalised_shape_rmse_R_vs_C": effect,
                              "shape_noise_floor": floor,
                              "attribution_ratio": effect/floor,
                              "clears_1p25x_floor": effect/floor >= 1.25,
                              "map_mismatch_mmHg": summary["mechanism_arm_map_difference_mmHg"]})
    mechanism = pd.DataFrame(mechanism)
    mechanism.to_csv(OUT/"mechanism_separation.csv", index=False)

    isolated = []
    expected = {
        "pulse_pressure_mmHg": "increase",
        "reflected_wave_phase": "decrease",
        "augmentation_index_pct": "increase",
    }
    for phenotype in ("compliance_dominant", "combined"):
        before = metrics[metrics.case == f"{phenotype}_arm1_inlet_only"].set_index("vessel")
        after = metrics[metrics.case == f"{phenotype}_arm2_matched_stiffening"].set_index("vessel")
        for vessel in SITES:
            for metric, direction in expected.items():
                a, b = before.loc[vessel, metric], after.loc[vessel, metric]
                delta = b-a if np.isfinite(a) and np.isfinite(b) else np.nan
                agrees = ((delta > 0) if direction == "increase" else (delta < 0)) if np.isfinite(delta) else False
                isolated.append({"phenotype": phenotype, "vessel": vessel,
                                 "metric": metric, "arm1": a, "arm2": b,
                                 "delta": delta, "expected_direction": direction,
                                 "direction_agrees": bool(agrees),
                                 "assessable": bool(np.isfinite(delta))})
    plausibility = pd.DataFrame(isolated)
    plausibility.to_csv(OUT/"physiological_direction_check.csv", index=False)

    prethreshold = []
    for _, result in acute.iterrows():
        path = OUT/"private/acute"/f"{result.body_id}__{result.phenotype}.csv.gz"
        trace = pd.read_csv(path)
        cutoff = result.time_to_map_below_65_s
        before = trace[trace.time_s <= cutoff]
        prethreshold.append(float(before.cardiac_output_L_min.min()))
    acute["minimum_co_through_map65_L_min"] = prethreshold
    acute.to_csv(OUT/"acute_body_results.csv", index=False)
    spread_rows = []
    for phenotype, group in acute.groupby("phenotype", sort=False):
        spread_rows.append({
            "phenotype": phenotype, "bodies_n": len(group),
            "map65_median_s": group.time_to_map_below_65_s.median(),
            "map65_min_s": group.time_to_map_below_65_s.min(),
            "map65_max_s": group.time_to_map_below_65_s.max(),
            "shock_events_n": group.time_to_hypovolemic_shock_s.notna().sum(),
            "shock_median_s": group.time_to_hypovolemic_shock_s.median(),
            "shock_min_s": group.time_to_hypovolemic_shock_s.min(),
            "shock_max_s": group.time_to_hypovolemic_shock_s.max(),
            "minimum_co_recorded_median_L_min": group.minimum_cardiac_output_L_min.median(),
            "minimum_co_through_map65_median_L_min": group.minimum_co_through_map65_L_min.median(),
        })
    acute_spread = pd.DataFrame(spread_rows)
    acute_spread.to_csv(OUT/"acute_phenotype_spread_compact.csv", index=False)

    p = pulse.set_index("phenotype")
    primary = metrics[metrics.case.str.contains("_arm[12]_")]
    primary_table = primary[["case", "vessel", "systolic_mmHg", "diastolic_mmHg",
                             "mean_mmHg", "pulse_pressure_mmHg", "time_to_peak_phase",
                             "reflected_wave_phase", "augmentation_index_pct"]]
    carotid_primary = primary_table[primary_table.vessel != "aortic_arch_I"]
    threshold_display = thresholds[["youngs_modulus_scale", "vessel",
                                    "phase_aligned_normalised_shape_rmse",
                                    "shape_noise_floor", "attribution_ratio",
                                    "passes_1p25x_floor"]]
    direction_carotid = plausibility[plausibility.vessel != "aortic_arch_I"]

    shape_pass = bool(mechanism.clears_1p25x_floor.all())
    physiological_pass = bool(
        direction_carotid[direction_carotid.metric == "pulse_pressure_mmHg"].direction_agrees.all()
        and direction_carotid[direction_carotid.metric == "reflected_wave_phase"].assessable.all()
        and direction_carotid[direction_carotid.metric == "reflected_wave_phase"].direction_agrees.all()
        and direction_carotid[direction_carotid.metric == "augmentation_index_pct"].assessable.all()
        and direction_carotid[direction_carotid.metric == "augmentation_index_pct"].direction_agrees.all())
    final = {
        **summary,
        "mechanism_shape_separation_clears_floor_both_arms_and_sites": shape_pass,
        "predeclared_physiological_direction_gate_passed": physiological_pass,
        "acute_runs": len(acute),
        "acute_runs_successful": int((acute.status == "ok").sum()),
        "conclusion": (
            "The coupling resolves modifier-associated carotid shape differences above "
            "the tested inlet noise floor, but the resistance/compliance arms are not "
            "MAP-matched and the stiffening response fails the predeclared reflected-wave/"
            "augmentation direction test. No physiologically recognisable hypertension "
            "signature is claimed from Stage 5."),
    }
    (OUT/"stage5_summary.json").write_text(json.dumps(final, indent=2)+"\n")

    doc = f"""# Stage 5: hypertension through the coupled pipeline

## Outcome

The coupled pipeline resolves carotid waveform changes above the tested inlet-noise floor, but **does not pass the physiological-recognisability gate**. A 25% global Young's-modulus increase was the smallest tested change clearing the normalised-shape floor at both carotids. However, resistance-only and compliance-only Pulse states differed in MAP by {summary['mechanism_arm_map_difference_mmHg']:.1f} mmHg, and the mapped stiffening did not consistently produce the predeclared earlier reflected wave and increased augmentation. Stage 5 therefore does not support an optical hypertension signature; it supplies a quantified detectable model perturbation with an unresolved physiological mapping.

No Pulse or openBF source was changed. Stage 0 remains byte-identical at SHA-256 `{summary['stage0_sha256']}` and all 16 openBF cases converged.

## Predeclared mapping

The mapping and pass criteria were fixed in `docs/STAGE5_PREDECLARATION.md` before the runs. Each phenotype's Pulse flow waveform and SVR were propagated. WK3 terminal resistances were globally scaled to that SVR. Arm 1 retained published wall properties; Arm 2 used `E scale = 1 / Pulse compliance multiplier`, with WK3 compliance unchanged. This is a first-order perturbation rule, not an equivalence between lumped Pulse compliance and distributed openBF compliance.

### Achieved Pulse phenotypes

{p[['resistance_multiplier','compliance_multiplier','systolic_mmHg','diastolic_mmHg','map_mmHg','pulse_pressure_mmHg','cardiac_output_L_min']].to_markdown(floatfmt='.3f')}

The compliance-only state changed pulse-pressure partitioning while leaving MAP near control. The resistance-only state raised MAP by about 25 mmHg. They cannot be mean-matched while remaining one-modifier phenotypes, so direct R-versus-C shape differences remain pressure-confounded.

## Coupled metrics

Augmentation pressure was predeclared as the first post-primary secondary peak minus its intervening minimum; AIx is `100*AP/PP`. It is an explicit rebound metric, not clinical `P2-P1`. Missing secondary extrema remain missing.

{carotid_primary.to_markdown(index=False, floatfmt='.3f')}

Amplitude and shape attribution are available without filtering in `attribution_table.csv`. A pass required at least 1.25 times the largest Stage 4.6 change from flow +/-5% or period +/-5%.

### Smallest resolvable stiffness change

{threshold_display.to_markdown(index=False, floatfmt='.4f')}

`E x1.10` failed at both carotids. `E x1.25` was the first tested level to pass: 1.31 times the ECA shape floor and 1.99 times the ICA floor. This is grid-censored between 10% and 25%; it is not a fitted detection threshold and it applies to simulated carotid pressure, not skin or rPPG.

### Mechanism separation

{mechanism.to_markdown(index=False, floatfmt='.4f')}

The R-versus-C normalised shapes clear the numerical floor, including in inlet-only Arm 1. Because the Pulse states differ in MAP by 24.0 mmHg, this demonstrates model-state separability, not mechanism-specific identifiability at matched pressure.

## Low-pulsatility obligation

{low.to_markdown(index=False, floatfmt='.4f')}

Relative to ADAN56's default inlet, the Pulse-driven baseline attenuated the `E x2.5` pulse-pressure change by {summary['low_pulsatility_attenuation']['external_carotid_R']['attenuation_pct']:.1f}% at ECA and {summary['low_pulsatility_attenuation']['internal_carotid_R']['attenuation_pct']:.1f}% at ICA. Normalised-shape effects were not attenuated: their Pulse/default ratios were {summary['low_pulsatility_attenuation']['external_carotid_R']['pulse_to_default_shape_effect_ratio']:.2f} and {summary['low_pulsatility_attenuation']['internal_carotid_R']['pulse_to_default_shape_effect_ratio']:.2f}. The depressed inlet therefore compresses amplitude but not this shape statistic.

## Physiological direction check

Clinical carotid tonometry has found earlier waveform reflection in both early and chronic essential hypertension ([Roman et al., 1996](https://pubmed.ncbi.nlm.nih.gov/8800034/)). The Charlton healthy-ageing database models age-dependent arterial stiffening and validates pressure-wave plausibility across 4,374 virtual subjects ([Charlton et al., 2019](https://doi.org/10.1152/ajpheart.00218.2019)). The relationship is not reducible to reflection alone: a clinical pressure/flow decomposition found similar backward-to-forward morphology across central pulse-pressure tertiles ([Westerhof et al., 2017](https://pubmed.ncbi.nlm.nih.gov/27920128/)).

{direction_carotid.to_markdown(index=False, floatfmt='.4f')}

Pulse pressure widened under distributed stiffening, as expected. The reflected-wave and augmentation tests did not pass: the ECA secondary maximum disappeared for compliance-only Arm 2, ICA reflection moved later and AIx fell, and both combined carotid AIx values fell. A merged peak could represent an early reflection that this extrema-based definition cannot separate, but that is an untested alternative interpretation. Under the predeclared metric, criterion 8 fails.

## ICA/ECA diagnosis

{terminal.to_markdown(index=False, floatfmt='.4g')}

Both candidate sites terminate directly in WK3 loads. The ICA load has lower R1/R2 and 1.63 times the ECA terminal compliance. Reducing terminal `Cc` to 0.4 changed PP by only 0.85 mmHg at ECA and 3.35 mmHg at ICA, whereas distributed `E x2.5` changed it by 22.95 and 12.86 mmHg. The odd site ordering is therefore not explained by terminal compliance alone. It is a network-plus-load property, and it cannot support a forehead-versus-cheek anatomical claim.

## Acute reach across bodies

The panel used the lowest- and highest-BMI admissible HAALSI bodies within each sex from the fixed anonymous Stage 2 sample (ages restricted to 40–65); BP was not used to select bodies. Bleeding was fixed at 200 mL/min from 30 to 655 s.

{acute_spread.to_markdown(index=False, floatfmt='.3f')}

The single-body Stage 2 direction did not generalise monotonically. Relative to the 467.5 s control median MAP-65 time, resistance-only was 21 s earlier, compliance-only 16 s later, and combined 15 s earlier. Across-body ranges were 237–233 s wide, much larger than phenotype median differences. Recorded minimum CO becomes zero when Pulse terminates at irreversible state, so the table also reports a termination-aware minimum through the MAP-65 crossing. One resistance-dominant body entered irreversible state without emitting a hypovolaemic-shock event; that shock time is missing rather than imputed.

## Acceptance decision

1. Stage 0 byte identity: **pass**.
2. Four phenotypes and mean-match assessment: **pass**, not mean-matched.
3. Mapping predeclared: **pass**.
4. Arms 1 and 2 for all phenotypes: **pass**.
5. Full metrics at all three sites: **pass**.
6. Per-metric amplitude/shape attribution including failures: **pass**.
7. Low-pulsatility attenuation: **pass**, amplitude attenuated, shape not.
8. Published-morphology direction: **fail under the predeclared reflection metric**.
9. Acute comparison across phenotypes and bodies: **pass**, with strong body dependence.

## Reproducibility and scope

Run configuration, code, full pass/fail tables, raw openBF last-cycle outputs, and private compressed Pulse trajectories are retained under `results/stage5`. Runtime was 10 min 41 s for 16 openBF cases with two workers and 36 min 30 s for 16 acute Pulse cases with two workers. This stage makes no claim about skin perfusion, rPPG, facial-site equivalence, chronic hypertension, or baroreflex disease state.
"""
    (ROOT/"docs/STAGE5_HYPERTENSION_COUPLED_PIPELINE.md").write_text(doc)
    print(json.dumps(final, indent=2))


if __name__ == "__main__":
    main()
