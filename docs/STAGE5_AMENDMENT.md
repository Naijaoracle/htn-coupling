# Stage 5 amendment: taper, stiffness gradient, and matched comparisons

## Decision

The original Stage 5 conclusion is **not overturned** under the predeclared amendment rule. The numerical shape signal remains real; the question here is whether central-only stiffening restores wider pulse pressure, earlier identifiable reflection, and increased augmentation at both carotids.

## Taper audit

The shipped ADAN56 network is not globally constant-radius. Of 77 vessels, 39 have unequal `Rp`/`Rd`, and the current openBF solver actively classifies 33 as tapered. Both terminal right carotid segments are constant-radius. The openBF validation paper's documented underprediction arose in its Charlton healthy-ageing conversion, where taper was replaced by a mean constant radius ([Benemerito et al., 2024](https://doi.org/10.1088/1361-6579/ad9663)); that limitation is not directly the configuration used here. No unsourced taper was added.

## Central-only versus uniform stiffening

Central vessels were the aortic arch, thoracic and abdominal aorta, brachiocephalic trunk, and bilateral common carotids. All other vessel `E` and every WK3 `Cc` remained published.

| phenotype           | arm               | case                                        | vessel             |   pulse_pressure_mmHg |   time_to_peak_phase | reflected_wave_present   |   reflected_wave_phase |   augmentation_index_pct |
|:--------------------|:------------------|:--------------------------------------------|:-------------------|----------------------:|---------------------:|:-------------------------|-----------------------:|-------------------------:|
| normotensive        | inlet_only        | normotensive_arm1_inlet_only                | external_carotid_R |               28.4806 |               0.1620 | True                     |                 0.2940 |                  16.1275 |
| normotensive        | uniform_E2p5      | threshold_E_2p50                            | external_carotid_R |               51.4282 |               0.2620 | False                    |               nan      |                 nan      |
| normotensive        | central_only_E2p5 | normotensive_central_E_2p5                  | external_carotid_R |               51.6509 |               0.1520 | True                     |                 0.3040 |                   3.2683 |
| normotensive        | inlet_only        | normotensive_arm1_inlet_only                | internal_carotid_R |               39.1966 |               0.1400 | True                     |                 0.3140 |                  20.7902 |
| normotensive        | uniform_E2p5      | threshold_E_2p50                            | internal_carotid_R |               52.0516 |               0.2720 | True                     |                 0.4860 |                   2.0012 |
| normotensive        | central_only_E2p5 | normotensive_central_E_2p5                  | internal_carotid_R |               58.3154 |               0.1320 | True                     |                 0.3220 |                   7.4489 |
| compliance_dominant | inlet_only        | compliance_dominant_arm1_inlet_only         | external_carotid_R |               25.0991 |               0.1720 | True                     |                 0.3740 |                  22.8372 |
| compliance_dominant | uniform_E2p5      | compliance_dominant_arm2_matched_stiffening | external_carotid_R |               48.4694 |               0.2920 | False                    |               nan      |                 nan      |
| compliance_dominant | central_only_E2p5 | compliance_dominant_central_E_2p5           | external_carotid_R |               45.5072 |               0.1520 | True                     |                 0.3220 |                   6.3288 |
| compliance_dominant | inlet_only        | compliance_dominant_arm1_inlet_only         | internal_carotid_R |               34.6523 |               0.1420 | True                     |                 0.3220 |                  24.2964 |
| compliance_dominant | uniform_E2p5      | compliance_dominant_arm2_matched_stiffening | internal_carotid_R |               49.2778 |               0.2920 | True                     |                 0.5240 |                   3.2973 |
| compliance_dominant | central_only_E2p5 | compliance_dominant_central_E_2p5           | internal_carotid_R |               51.4365 |               0.1420 | True                     |                 0.3340 |                  12.7339 |
| combined            | inlet_only        | combined_arm1_inlet_only                    | external_carotid_R |               16.9483 |               0.2820 | True                     |                 0.5360 |                   5.6090 |
| combined            | uniform_E2p5      | combined_arm2_matched_stiffening            | external_carotid_R |               34.9774 |               0.2720 | True                     |                 0.4460 |                   3.8588 |
| combined            | central_only_E2p5 | combined_central_E_2p5                      | external_carotid_R |               32.3429 |               0.1320 | True                     |                 0.2820 |                  19.8995 |
| combined            | inlet_only        | combined_arm1_inlet_only                    | internal_carotid_R |               24.6091 |               0.1220 | True                     |                 0.2840 |                  39.7954 |
| combined            | uniform_E2p5      | combined_arm2_matched_stiffening            | internal_carotid_R |               35.8387 |               0.2720 | True                     |                 0.4640 |                   9.0185 |
| combined            | central_only_E2p5 | combined_central_E_2p5                      | internal_carotid_R |               37.7597 |               0.1120 | True                     |                 0.2820 |                  25.9090 |

| phenotype           | vessel             | arm               |   delta_pp_mmHg |   delta_reflected_wave_phase |   delta_augmentation_index_pct | pp_widens   | reflection_earlier   | augmentation_increases   | all_directions_pass   |
|:--------------------|:-------------------|:------------------|----------------:|-----------------------------:|-------------------------------:|:------------|:---------------------|:-------------------------|:----------------------|
| normotensive        | external_carotid_R | uniform_E2p5      |         22.9476 |                     nan      |                       nan      | True        | False                | False                    | False                 |
| normotensive        | external_carotid_R | central_only_E2p5 |         23.1703 |                       0.0100 |                       -12.8592 | True        | False                | False                    | False                 |
| normotensive        | internal_carotid_R | uniform_E2p5      |         12.8551 |                       0.1720 |                       -18.7890 | True        | False                | False                    | False                 |
| normotensive        | internal_carotid_R | central_only_E2p5 |         19.1189 |                       0.0080 |                       -13.3413 | True        | False                | False                    | False                 |
| compliance_dominant | external_carotid_R | uniform_E2p5      |         23.3703 |                     nan      |                       nan      | True        | False                | False                    | False                 |
| compliance_dominant | external_carotid_R | central_only_E2p5 |         20.4081 |                      -0.0520 |                       -16.5084 | True        | True                 | False                    | False                 |
| compliance_dominant | internal_carotid_R | uniform_E2p5      |         14.6255 |                       0.2020 |                       -20.9991 | True        | False                | False                    | False                 |
| compliance_dominant | internal_carotid_R | central_only_E2p5 |         16.7842 |                       0.0120 |                       -11.5624 | True        | False                | False                    | False                 |
| combined            | external_carotid_R | uniform_E2p5      |         18.0291 |                      -0.0900 |                        -1.7502 | True        | True                 | False                    | False                 |
| combined            | external_carotid_R | central_only_E2p5 |         15.3946 |                      -0.2540 |                        14.2904 | True        | True                 | True                     | True                  |
| combined            | internal_carotid_R | uniform_E2p5      |         11.2296 |                       0.1800 |                       -30.7769 | True        | False                | False                    | False                 |
| combined            | internal_carotid_R | central_only_E2p5 |         13.1507 |                      -0.0020 |                       -13.8864 | True        | True                 | False                    | False                 |

The amendment gate requires all three directions at both sites; an absent secondary extremum is unassessable, not a pass.

## MAP-matched mechanism comparison

Linear interpolation selected Pulse resistance multiplier 1.016468. It achieved MAP 96.487 mmHg, +0.381 mmHg from the compliance-dominant target.

| vessel             |   shape_rmse |   optimal_phase_shift |   shape_noise_floor |   attribution_ratio | clears_1p25x_floor   |
|:-------------------|-------------:|----------------------:|--------------------:|--------------------:|:---------------------|
| external_carotid_R |       0.1359 |                0.0020 |              0.0382 |              3.5600 | True                 |
| internal_carotid_R |       0.2569 |                0.0100 |              0.0411 |              6.2476 | True                 |

This removes the 24 mmHg Pulse MAP gap. It matches mean pressure, not systolic/diastolic severity.

## Fractional acute endpoints

Baseline is each run's median MAP over scenario seconds 0–29. Crossings are relative to that run and missing values are not imputed.

| phenotype           |   bodies_n |   baseline_map_median_mmHg |   time_to_20pct_fall_median_s |   time_to_30pct_fall_median_s |   time_to_40pct_fall_median_s |
|:--------------------|-----------:|---------------------------:|------------------------------:|------------------------------:|------------------------------:|
| combined            |          4 |                    121.126 |                       379.500 |                       417.000 |                       440.500 |
| compliance_dominant |          4 |                     96.544 |                       436.500 |                       475.500 |                       502.500 |
| normotensive        |          4 |                     95.213 |                       425.500 |                       462.500 |                       487.500 |
| resistance_dominant |          4 |                    119.995 |                       374.500 |                       412.500 |                       435.500 |

These fractional endpoints should accompany, and take interpretive precedence over, the absolute MAP-65 ordering when baseline pressures differ.
