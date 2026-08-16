# Stage 2: stock-Pulse Tier 0 hypertension phenotype

## Scope

Every phenotype here is an admissible normotensive patient to whom cardiovascular modifiers were applied at time zero. Disease stage and duration are therefore erased by construction. No Pulse source, baseline-pressure envelope, ventricular property, stroke-volume multiplier, or baroreflex parameter was changed.

## Stage 0 gate

The fresh Stage 0 haemorrhage output was byte-identical to the archived control: 46,098,446 bytes and SHA-256 `462c43248785ce45771b056b53443252414ec066ae50bee0d3b276a42fcfab0a`. Hypovolaemic shock again occurred at 615.16 s.

## Reachability and calibration

The 13 × 11 sweep covered systemic resistance 1.00–1.60 and arterial compliance 1.00–0.50 in 0.05 increments. All 143 cells restabilised; there was no hard failure boundary in this domain. Restabilisation wall time nevertheless rose from 117.9 to 270.0 s, making convergence cost the practical boundary signal.

The achieved envelope was SBP 114.9–142.3, DBP 59.5–96.3, MAP 95.9–113.7, and pulse pressure 32.4–71.3 mmHg. A 150/90 phenotype was not reachable in the prescribed grid; the nearest high-pressure point was approximately 142/83 mmHg.

Only 23 of 459 five-mmHg target pairs lay inside the achieved pressure-pair hull. Every one was rerun through Pulse: all 23 met the predeclared ±5/±5 mmHg criterion. Median achieved Euclidean residual was 0.043 mmHg and the maximum was 0.568 mmHg. Targets outside the hull are recorded as unreachable, never silently replaced by a nearest point.

## Population test

| cohort     |   sample_n |   direct_pressure_admissible_pct |   direct_all_constraints_admissible_pct |   modifier_representable_pct |   direct_all_to_modifier_gain_pp |   unreachable_low_pressure_n |   median_euclidean_residual_attempted_mmHg |
|:-----------|-----------:|---------------------------------:|----------------------------------------:|-----------------------------:|---------------------------------:|-----------------------------:|-------------------------------------------:|
| haalsi     |        200 |                           18.500 |                                   8.500 |                       16.000 |                            7.500 |                            5 |                                      0.424 |
| elsa_wave8 |        200 |                           24.000 |                                   8.000 |                       10.000 |                            2.000 |                           23 |                                      0.366 |

The deterministic samples used seeds 20260816 and 20260817. HAALSI pressure-only direct exclusion was 81.5%, matching Stage 1's approximately 81%. With body constraints included, modifiers increased HAALSI representability from 8.5% to 16.0% (+7.5 percentage points) and ELSA from 8.0% to 10.0% (+2.0 points). All 52 attempted engines succeeded and met pressure tolerance. ELSA had 23 explicitly unreachable low-pressure targets, showing the asymmetry of a modifier domain chosen to raise pressure.

Anonymous exact sampled rows remain local under `results/stage2/private`; only aggregate results are intended for version control.

## Restabilisation

The representative nearest attainable point to 150/90 used resistance 1.600 and compliance 0.500. Default `incremental=false` processing took 132.99 wall seconds and advanced the engine clock from 30.0 to 882.7 s. The blocking API supplies no intermediate `pull_data` samples, so the saved trace shows measured pre/post operating points rather than fabricating a transition waveform.

|                                        |      pre |     post |
|:---------------------------------------|---------:|---------:|
| systolic_mmHg                          | 114.2574 | 142.2855 |
| diastolic_mmHg                         |  73.5869 |  82.9517 |
| map_mmHg                               |  95.3243 | 113.6762 |
| pulse_pressure_mmHg                    |  40.6732 |  59.3343 |
| heart_rate_per_min                     |  72.0230 |  71.9722 |
| cardiac_output_L_min                   |   5.7878 |   4.4102 |
| systemic_vascular_resistance_mmHg_s_mL |   0.9394 |   1.4968 |
| baroreceptor_heart_rate_scale          |   0.9997 |   0.9983 |
| baroreceptor_heart_elastance_scale     |   1.0000 |   0.9999 |
| baroreceptor_resistance_scale          |   0.9999 |   0.9991 |
| baroreceptor_compliance_scale          |   1.0000 |   1.0003 |

MAP rose from 95.3 to 113.7 mmHg, CO fell from 5.79 to 4.41 L/min, and SVR rose from 0.94 to 1.50 mmHg·s/mL. All four directly requested baroreflex scales were essentially 1.0 after restabilisation. Empirically, the engine accepted the raised operating pressure as the new accommodated state rather than sustaining a corrective reflex output.

## Acute reach

| phenotype    | status   |   simulated_through_s |   time_to_hypovolemic_shock_s |   time_to_map_below_65_s |   minimum_map_mmHg |   maximum_heart_rate_per_min |   minimum_cardiac_output_L_min |
|:-------------|:---------|----------------------:|------------------------------:|-------------------------:|-------------------:|-----------------------------:|-------------------------------:|
| normotensive | ok       |                  2155 |                        615.16 |                      538 |            41.6096 |                      155.654 |                        1.82966 |
| hypertensive | ok       |                  2155 |                        608.1  |                      527 |            41.5597 |                      151.049 |                        1.01803 |

The fixed 200 mL/min bleed ran from 30 to 655 s. The hypertensive phenotype crossed MAP 65 mmHg 11.0 s earlier and entered hypovolaemic shock 7.06 s earlier. Its minimum cardiac output was 1.02 versus 1.83 L/min. The released modifiers therefore reach the acute scenario materially; they are not merely cosmetic resting-pressure labels.

## Interpretation and limits

Stock Pulse can produce a modest hypertensive haemodynamic state accurately, and that state changes haemorrhage compensation. It cannot cover much of either real cohort because the two-modifier pressure manifold is narrow, the prescribed grid does not reach 150 mmHg systolic, body-definition exclusions remain, and low-pressure targets are outside this raise-oriented domain. Tier 1 is therefore justified by quantified coverage limits rather than by solver instability.

This remains an acute-onset phenotype. It contains no disease duration, vascular remodelling history, exposed baroreflex setpoint, or progression stage. The inverse lookup was learned on StandardMale and transferred to body-specific patients; transfer was accurate for all attempted cases here, but only within the measured hull. The 200-person samples quantify this seeded experiment rather than replacing full-cohort inference.

## Artefacts

- Reproduce with `scripts/run_stage2_tier0.sh all --workers 12`; individual stages and a non-rerunning `report` command are also available.
- `reachability_sweep.csv` and `reachability_and_failure_boundary.png`
- `calibration_lookup_table.csv` and `calibration_reachability_and_residuals.png`
- `population_representability_summary.csv` and `population_representability.png`
- `restabilisation_trace.csv`, metadata, and baroreflex figure
- aligned compressed acute trajectories, summary, and comparison figure
- `stage0_regression_gate.json` and `stage2_summary.json`
