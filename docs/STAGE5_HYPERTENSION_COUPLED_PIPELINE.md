# Stage 5: hypertension through the coupled pipeline

## Abstract

The optical-relevant result is positive: normalised carotid waveform shape was not attenuated by Pulse’s low-pulsatility inlet even though pulse-pressure response was attenuated by 40% at ECA and 59% at ICA. A 25% Young’s-modulus increase, rather than a doubling, was the smallest tested change clearing the predeclared shape floor at both sites. A subsequent amendment also retained shape separation after resistance and compliance phenotypes were matched to within 0.382 mmHg MAP (3.56 times the ECA floor and 6.25 times the ICA floor). The remaining negative result is narrower: neither uniform nor central-only stiffening produced the full predeclared reflection-plus-augmentation direction at both carotids, so the detectable model signature is not yet a validated physiological hypertension signature. See `docs/STAGE5_AMENDMENT.md`.

## Outcome

The coupled pipeline resolves carotid waveform changes above the tested inlet-noise floor, but **does not pass the physiological-recognisability gate**. A 25% global Young’s-modulus increase was the smallest tested change clearing the normalised-shape floor at both carotids. The original resistance-only and compliance-only Pulse states differed in MAP by 24.0 mmHg; the amendment removed that gap to 0.382 mmHg and retained shape separation at 3.56 and 6.25 times the ECA and ICA floors. Central-only stiffening improved reflection timing and augmentation for the combined ECA case, but not at both sites or in the compliance-only state. Stage 5 therefore establishes a robust detectable shape perturbation, but not yet a validated optical hypertension signature.

No Pulse or openBF source was changed. Stage 0 remains byte-identical at SHA-256 `462c43248785ce45771b056b53443252414ec066ae50bee0d3b276a42fcfab0a` and all 16 openBF cases converged.

## Predeclared mapping

The mapping and pass criteria were fixed in `docs/STAGE5_PREDECLARATION.md` before the runs. Each phenotype's Pulse flow waveform and SVR were propagated. WK3 terminal resistances were globally scaled to that SVR. Arm 1 retained published wall properties; Arm 2 used `E scale = 1 / Pulse compliance multiplier`, with WK3 compliance unchanged. This is a first-order perturbation rule, not an equivalence between lumped Pulse compliance and distributed openBF compliance.

### Achieved Pulse phenotypes

| phenotype           |   resistance_multiplier |   compliance_multiplier |   systolic_mmHg |   diastolic_mmHg |   map_mmHg |   pulse_pressure_mmHg |   cardiac_output_L_min |
|:--------------------|------------------------:|------------------------:|----------------:|-----------------:|-----------:|----------------------:|-----------------------:|
| normotensive        |                   1.000 |                   1.000 |         114.262 |           73.588 |     95.328 |                40.673 |                  5.787 |
| resistance_dominant |                   2.000 |                   1.000 |         133.983 |          104.761 |    120.102 |                29.222 |                  3.788 |
| compliance_dominant |                   1.000 |                   0.400 |         136.859 |           53.105 |     96.105 |                83.754 |                  5.818 |
| combined            |                   2.000 |                   0.400 |         152.159 |           87.787 |    120.857 |                64.372 |                  3.836 |

The compliance-only state changed pulse-pressure partitioning while leaving MAP near control. The resistance-only state raised MAP by about 25 mmHg. They cannot be mean-matched while remaining one-modifier phenotypes, so direct R-versus-C shape differences remain pressure-confounded.

## Coupled metrics

Augmentation pressure was predeclared as the first post-primary secondary peak minus its intervening minimum; AIx is `100*AP/PP`. It is an explicit rebound metric, not clinical `P2-P1`. Missing secondary extrema remain missing.

| case                                        | vessel             |   systolic_mmHg |   diastolic_mmHg |   mean_mmHg |   pulse_pressure_mmHg |   time_to_peak_phase |   reflected_wave_phase |   augmentation_index_pct |
|:--------------------------------------------|:-------------------|----------------:|-----------------:|------------:|----------------------:|---------------------:|-----------------------:|-------------------------:|
| normotensive_arm1_inlet_only                | external_carotid_R |         104.209 |           75.728 |      91.136 |                28.481 |                0.162 |                  0.294 |                   16.127 |
| normotensive_arm1_inlet_only                | internal_carotid_R |         114.131 |           74.934 |      90.963 |                39.197 |                0.140 |                  0.314 |                   20.790 |
| normotensive_arm2_matched_stiffening        | external_carotid_R |         104.209 |           75.728 |      91.136 |                28.481 |                0.162 |                  0.294 |                   16.127 |
| normotensive_arm2_matched_stiffening        | internal_carotid_R |         114.131 |           74.934 |      90.963 |                39.197 |                0.140 |                  0.314 |                   20.790 |
| resistance_dominant_arm1_inlet_only         | external_carotid_R |         121.859 |          103.178 |     113.503 |                18.681 |                0.162 |                  0.292 |                   32.032 |
| resistance_dominant_arm1_inlet_only         | internal_carotid_R |         128.826 |          102.547 |     113.410 |                26.278 |                0.132 |                  0.302 |                   37.754 |
| resistance_dominant_arm2_matched_stiffening | external_carotid_R |         121.859 |          103.178 |     113.503 |                18.681 |                0.162 |                  0.292 |                   32.032 |
| resistance_dominant_arm2_matched_stiffening | internal_carotid_R |         128.826 |          102.547 |     113.410 |                26.278 |                0.132 |                  0.302 |                   37.754 |
| compliance_dominant_arm1_inlet_only         | external_carotid_R |         102.624 |           77.525 |      92.339 |                25.099 |                0.172 |                  0.374 |                   22.837 |
| compliance_dominant_arm1_inlet_only         | internal_carotid_R |         111.455 |           76.802 |      92.159 |                34.652 |                0.142 |                  0.322 |                   24.296 |
| compliance_dominant_arm2_matched_stiffening | external_carotid_R |         112.682 |           64.212 |      93.603 |                48.469 |                0.292 |                nan     |                  nan     |
| compliance_dominant_arm2_matched_stiffening | internal_carotid_R |         112.840 |           63.563 |      93.379 |                49.278 |                0.292 |                  0.524 |                    3.297 |
| combined_arm1_inlet_only                    | external_carotid_R |         121.113 |          104.165 |     114.203 |                16.948 |                0.282 |                  0.536 |                    5.609 |
| combined_arm1_inlet_only                    | internal_carotid_R |         128.209 |          103.599 |     114.108 |                24.609 |                0.122 |                  0.284 |                   39.795 |
| combined_arm2_matched_stiffening            | external_carotid_R |         132.258 |           97.281 |     117.248 |                34.977 |                0.272 |                  0.446 |                    3.859 |
| combined_arm2_matched_stiffening            | internal_carotid_R |         132.599 |           96.760 |     117.113 |                35.839 |                0.272 |                  0.464 |                    9.018 |

Amplitude and shape attribution are available without filtering in `attribution_table.csv`. A pass required at least 1.25 times the largest Stage 4.6 change from flow +/-5% or period +/-5%.

### Smallest resolvable stiffness change

|   youngs_modulus_scale | vessel             |   phase_aligned_normalised_shape_rmse |   shape_noise_floor |   attribution_ratio | passes_1p25x_floor   |
|-----------------------:|:-------------------|--------------------------------------:|--------------------:|--------------------:|:---------------------|
|                 1.1000 | external_carotid_R |                                0.0258 |              0.0382 |              0.6754 | False                |
|                 1.1000 | internal_carotid_R |                                0.0355 |              0.0411 |              0.8644 | False                |
|                 1.2500 | external_carotid_R |                                0.0499 |              0.0382 |              1.3072 | True                 |
|                 1.2500 | internal_carotid_R |                                0.0819 |              0.0411 |              1.9926 | True                 |
|                 1.5000 | external_carotid_R |                                0.0833 |              0.0382 |              2.1807 | True                 |
|                 1.5000 | internal_carotid_R |                                0.1378 |              0.0411 |              3.3509 | True                 |
|                 1.7500 | external_carotid_R |                                0.1115 |              0.0382 |              2.9214 | True                 |
|                 1.7500 | internal_carotid_R |                                0.1859 |              0.0411 |              4.5213 | True                 |
|                 2.0000 | external_carotid_R |                                0.1164 |              0.0382 |              3.0484 | True                 |
|                 2.0000 | internal_carotid_R |                                0.2282 |              0.0411 |              5.5500 | True                 |
|                 2.5000 | external_carotid_R |                                0.1189 |              0.0382 |              3.1151 | True                 |
|                 2.5000 | internal_carotid_R |                                0.2390 |              0.0411 |              5.8129 | True                 |

`E x1.10` failed at both carotids. `E x1.25` was the first tested level to pass: 1.31 times the ECA shape floor and 1.99 times the ICA floor. This is grid-censored between 10% and 25%; it is not a fitted detection threshold and it applies to simulated carotid pressure, not skin or rPPG.

### Mechanism separation

| arm                     | vessel             |   normalised_shape_rmse_R_vs_C |   shape_noise_floor |   attribution_ratio | clears_1p25x_floor   |   map_mismatch_mmHg |
|:------------------------|:-------------------|-------------------------------:|--------------------:|--------------------:|:---------------------|--------------------:|
| arm1_inlet_only         | external_carotid_R |                         0.0723 |              0.0382 |              1.8938 | True                 |             23.9970 |
| arm1_inlet_only         | internal_carotid_R |                         0.0678 |              0.0411 |              1.6476 | True                 |             23.9970 |
| arm2_matched_stiffening | external_carotid_R |                         0.1380 |              0.0382 |              3.6145 | True                 |             23.9970 |
| arm2_matched_stiffening | internal_carotid_R |                         0.2629 |              0.0411 |              6.3938 | True                 |             23.9970 |

The R-versus-C normalised shapes clear the numerical floor, including in inlet-only Arm 1. Because the Pulse states differ in MAP by 24.0 mmHg, this demonstrates model-state separability, not mechanism-specific identifiability at matched pressure.

## Low-pulsatility obligation

| source                          | vessel             |   baseline_pp_mmHg |   stiff_pp_mmHg |   delta_pp_mmHg |   baseline_augmentation_index_pct |   stiff_augmentation_index_pct |   phase_aligned_normalised_shape_rmse |   optimal_phase_shift |
|:--------------------------------|:-------------------|-------------------:|----------------:|----------------:|----------------------------------:|-------------------------------:|--------------------------------------:|----------------------:|
| Pulse low-pulsatility           | aortic_arch_I      |            20.4341 |         47.6805 |         27.2465 |                            2.0504 |                       nan      |                                0.0742 |                0.0040 |
| Pulse low-pulsatility           | external_carotid_R |            28.4806 |         51.4282 |         22.9476 |                           16.1275 |                       nan      |                                0.1189 |                0.0160 |
| Pulse low-pulsatility           | internal_carotid_R |            39.1966 |         52.0516 |         12.8551 |                           20.7902 |                         2.0012 |                                0.2390 |                0.0220 |
| ADAN56 default high-pulsatility | aortic_arch_I      |            34.4020 |         72.1599 |         37.7580 |                            5.0730 |                         5.6764 |                                0.0818 |                0.0080 |
| ADAN56 default high-pulsatility | external_carotid_R |            37.7223 |         75.7832 |         38.0609 |                           15.1813 |                        19.7148 |                                0.0968 |                0.0120 |
| ADAN56 default high-pulsatility | internal_carotid_R |            45.5161 |         76.9612 |         31.4450 |                           21.0680 |                        24.0009 |                                0.1368 |                0.0160 |

Relative to ADAN56's default inlet, the Pulse-driven baseline attenuated the `E x2.5` pulse-pressure change by 39.7% at ECA and 59.1% at ICA. Normalised-shape effects were not attenuated: their Pulse/default ratios were 1.23 and 1.75. The depressed inlet therefore compresses amplitude but not this shape statistic.

## Physiological direction check

Clinical carotid tonometry has found earlier waveform reflection in both early and chronic essential hypertension ([Roman et al., 1996](https://pubmed.ncbi.nlm.nih.gov/8800034/)). The Charlton healthy-ageing database models age-dependent arterial stiffening and validates pressure-wave plausibility across 4,374 virtual subjects ([Charlton et al., 2019](https://doi.org/10.1152/ajpheart.00218.2019)). The relationship is not reducible to reflection alone: a clinical pressure/flow decomposition found similar backward-to-forward morphology across central pulse-pressure tertiles ([Westerhof et al., 2017](https://pubmed.ncbi.nlm.nih.gov/27920128/)).

| phenotype           | vessel             | metric                 |    arm1 |     arm2 |    delta | expected_direction   | direction_agrees   | assessable   |
|:--------------------|:-------------------|:-----------------------|--------:|---------:|---------:|:---------------------|:-------------------|:-------------|
| compliance_dominant | external_carotid_R | pulse_pressure_mmHg    | 25.0991 |  48.4694 |  23.3703 | increase             | True               | True         |
| compliance_dominant | external_carotid_R | reflected_wave_phase   |  0.3740 | nan      | nan      | decrease             | False              | False        |
| compliance_dominant | external_carotid_R | augmentation_index_pct | 22.8372 | nan      | nan      | increase             | False              | False        |
| compliance_dominant | internal_carotid_R | pulse_pressure_mmHg    | 34.6523 |  49.2778 |  14.6255 | increase             | True               | True         |
| compliance_dominant | internal_carotid_R | reflected_wave_phase   |  0.3220 |   0.5240 |   0.2020 | decrease             | False              | True         |
| compliance_dominant | internal_carotid_R | augmentation_index_pct | 24.2964 |   3.2973 | -20.9991 | increase             | False              | True         |
| combined            | external_carotid_R | pulse_pressure_mmHg    | 16.9483 |  34.9774 |  18.0291 | increase             | True               | True         |
| combined            | external_carotid_R | reflected_wave_phase   |  0.5360 |   0.4460 |  -0.0900 | decrease             | True               | True         |
| combined            | external_carotid_R | augmentation_index_pct |  5.6090 |   3.8588 |  -1.7502 | increase             | False              | True         |
| combined            | internal_carotid_R | pulse_pressure_mmHg    | 24.6091 |  35.8387 |  11.2296 | increase             | True               | True         |
| combined            | internal_carotid_R | reflected_wave_phase   |  0.2840 |   0.4640 |   0.1800 | decrease             | False              | True         |
| combined            | internal_carotid_R | augmentation_index_pct | 39.7954 |   9.0185 | -30.7769 | increase             | False              | True         |

Pulse pressure widened under distributed stiffening, as expected. The reflected-wave and augmentation tests did not pass: the ECA secondary maximum disappeared for compliance-only Arm 2, ICA reflection moved later and AIx fell, and both combined carotid AIx values fell. A merged peak could represent an early reflection that this extrema-based definition cannot separate, but that is an untested alternative interpretation. Under the predeclared metric, criterion 8 fails.

## ICA/ECA diagnosis

| vessel             |   length_m |   radius_m |   R1_pa_s_m3 |   R2_pa_s_m3 |   Cc_m3_pa |   baseline_pp_mmHg |   delta_pp_E_2p5_mmHg |   delta_pp_Cc_0p4_mmHg |
|:-------------------|-----------:|-----------:|-------------:|-------------:|-----------:|-------------------:|----------------------:|-----------------------:|
| external_carotid_R |     0.0609 |   0.002265 |    9.391e+08 |    3.756e+09 |  6.032e-11 |              28.48 |                 22.95 |                 0.8537 |
| internal_carotid_R |     0.1321 |   0.002765 |    5.76e+08  |    2.304e+09 |  9.833e-11 |              39.2  |                 12.86 |                 3.345  |

Both candidate sites terminate directly in WK3 loads. The ICA load has lower R1/R2 and 1.63 times the ECA terminal compliance. Reducing terminal `Cc` to 0.4 changed PP by only 0.85 mmHg at ECA and 3.35 mmHg at ICA, whereas distributed `E x2.5` changed it by 22.95 and 12.86 mmHg. The odd site ordering is therefore not explained by terminal compliance alone. It is a network-plus-load property, and it cannot support a forehead-versus-cheek anatomical claim.

## Acute reach across bodies

The panel used the lowest- and highest-BMI admissible HAALSI bodies within each sex from the fixed anonymous Stage 2 sample (ages restricted to 40–65); BP was not used to select bodies. Bleeding was fixed at 200 mL/min from 30 to 655 s.

| phenotype           |   bodies_n |   map65_median_s |   map65_min_s |   map65_max_s |   shock_events_n |   shock_median_s |   shock_min_s |   shock_max_s |   minimum_co_recorded_median_L_min |   minimum_co_through_map65_median_L_min |
|:--------------------|-----------:|-----------------:|--------------:|--------------:|-----------------:|-----------------:|--------------:|--------------:|-----------------------------------:|----------------------------------------:|
| combined            |          4 |          452.500 |       335.000 |       525.000 |                4 |          516.850 |       324.460 |       623.120 |                              0.365 |                                   1.436 |
| compliance_dominant |          4 |          483.500 |       328.000 |       561.000 |                4 |          535.720 |       334.200 |       646.960 |                              0.835 |                                   3.045 |
| normotensive        |          4 |          467.500 |       316.000 |       553.000 |                4 |          525.700 |       326.680 |       638.640 |                              0.826 |                                   3.057 |
| resistance_dominant |          4 |          446.500 |       328.000 |       518.000 |                3 |          449.400 |       326.580 |       625.360 |                              0.000 |                                   1.414 |

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
