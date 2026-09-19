# Pressure matched drug response experiment: dose selection and paired results

## Scope

This is a Pulse model characterisation experiment. It is not a clinical dosing recommendation. The comparison asks whether pressure matched direct patient initialisation and cardiovascular mechanics modification states show different simulated responses to the same norepinephrine infusion.

The runs use Pulse `99e2d50cb7d0e0893690bf113d2f7924bb933f56`, HTN coupling revision `5bd9637e289393bb07f38e367e30e7400d5e5047`, and the pressure matched v2 Stage 0 gate SHA-256 `1b0c930372fc7c82982f4ecccda7dab34569b03c2a8bd678c78194e79b7a56eb`. The protocol file was in Downloads and was not committed before paired runs, so its formal commit-before-run requirement was not met. The selected dose and other run settings were saved in a local configuration before paired exposure, but these results should be treated as exploratory model characterisation rather than a formally precommitted experiment. The locked configuration is [pressure_matched_drug_response_v1.json](../config/pressure_matched_drug_response_v1.json). Compact outputs are [dose_selection_v1.csv](../results/pressure_matched_drug_response/dose_selection_v1.csv), [aggregate_v1.csv](../results/pressure_matched_drug_response/aggregate_v1.csv), and [manifest_v1.json](../results/pressure_matched_drug_response/manifest_v1.json). Full traces and run logs remain in the ignored private results directory.

## Dose selection

Dose selection used the direct intermediate state (requested 140/90 mmHg), a 77.1107029 kg patient, 1 µg/mL norepinephrine, a 300 second infusion, and a 300 second post-infusion observation. A no-drug run set the largest absolute 10-second median drift at 0.05532 mmHg for MAP and 0.008583 mmHg·s/mL for SVR. The predeclared screen selected the lowest dose with positive MAP and SVR changes both greater than three times those drifts, no irreversible-state event, and an independent repeat that also passed.

| Dose (µg/kg/min) | Rate (mL/s) | Volume equivalent over 300 s (mL) | Peak 10 s ΔMAP (mmHg) | Peak 10 s ΔSVR (mmHg·s/mL) | Screen |
|---:|---:|---:|---:|---:|:---|
| 0.05 | 0.06426 | 19.28 | 0.0553 | 0.00858 | Fail: response did not exceed both drift thresholds |
| 0.10 | 0.12852 | 38.56 | 1.1032 | 0.01641 | Fail: SVR did not exceed its threshold |
| 0.20, replicate 1 | 0.25704 | 77.11 | 27.9088 | 0.53276 | Pass |
| 0.20, replicate 2 | 0.25704 | 77.11 | 27.9088 | 0.53276 | Pass |

The selected challenge was 0.20 µg/kg/min, delivered at 0.2570356763 mL/s for 300 seconds. The two selection replicates were identical at the recorded precision. Higher ladder doses were not run after this lowest qualifying dose was selected.

Pulse's pinned infusion implementation uses the volume field to track reservoir depletion and adds drug mass from concentration and rate; it does not add carrier fluid to the cardiovascular fluid system. Thus 77.11 mL is the nominal delivered-volume equivalent, not a modeled fluid load. A vehicle-only control would not test fluid loading in this engine revision.

## Fresh baseline gate

Each route was initialized in a fresh engine and observed without drug for 60 seconds. Pair pressure was assessed from the final 30-second median (`30 <= elapsed_s < 60`), with stationarity checked over four consecutive 3-second bins at the end of that interval. All six route baselines passed stationarity, and all three pairs passed the ±0.25 mmHg SBP and DBP match gate before any paired challenge was run.

| Target | Direct SBP/DBP (mmHg) | Modifier SBP/DBP (mmHg) | Direct − modifier SBP/DBP (mmHg) |
|:--|:--:|:--:|:--:|
| Mild | 129.018 / 80.187 | 128.857 / 80.268 | +0.161 / −0.081 |
| Intermediate | 139.954 / 89.761 | 139.789 / 89.581 | +0.165 / +0.179 |
| Higher | 148.603 / 90.703 | 148.664 / 90.738 | −0.061 / −0.035 |

The challenge runs repeated these baseline checks before infusion and again passed. During execution, the gate code included the sample at elapsed second 60, which was captured immediately before the infusion action. Final analysis now uses the protocol-defined half-open interval `[30,60)`, recomputed from the saved traces. All three screening pairs and all three challenge-trace pairs still pass the ±0.25 mmHg gate and stationarity rule. All routes received the same concentration, rate, start time, and duration. No vehicle-fluid effect is represented by this Pulse implementation.

## Paired responses

Values below are maximum 10-second rolling-median change from each route's own final 30-second pre-infusion median (`30 <= elapsed_s < 60`). SVR is in mmHg·s/mL; CO is the minimum change. These are descriptive single runs per route and target.

| Target | Route | Peak ΔMAP (mmHg) | Peak ΔSBP (mmHg) | Peak ΔDBP (mmHg) | Peak ΔSVR | Minimum ΔCO (L/min) | Peak ΔHR (/min) |
|:--|:--|--:|--:|--:|--:|--:|--:|
| Mild | Direct | +25.32 | +27.50 | +24.70 | +0.456 | −0.870 | +6.96 |
| Mild | Modifier | +24.92 | +26.11 | +24.49 | +0.595 | −0.803 | +9.56 |
| Intermediate | Direct | +27.91 | +30.36 | +26.59 | +0.533 | −0.956 | +6.75 |
| Intermediate | Modifier | +26.95 | +27.11 | +28.83 | +0.857 | −0.800 | +11.91 |
| Higher | Direct | +29.08 | +33.12 | +26.56 | +0.507 | −0.936 | +5.90 |
| Higher | Modifier | +27.71 | +28.04 | +30.34 | +1.078 | −0.824 | +12.85 |

All six infusions and 300-second post-infusion observations completed. No run entered an irreversible state. MAP and SBP were close to their pre-infusion medians by the end of follow-up. DBP retained small positive residuals in several runs, largest +0.67 mmHg (higher modifier). The recorded event sets are preserved in the aggregate and detailed manifest.

Hypernatremia was logged in modifier runs. It arose during state initialization before infusion in the mild and higher cases, and during infusion in the intermediate case, so it cannot be treated uniformly as a norepinephrine-caused event. Diuresis was logged during all three direct infusion trajectories and was also present during initialization in the intermediate and higher modifier runs. Full event timing is retained in the private logs. No irreversible-state event occurred.

## Interpretation

At this selected challenge, all six states showed a large, reversible pressor response. Across the three targets, peak MAP increases were similar in paired routes (direct +25.3 to +29.1 mmHg; modifier +24.9 to +27.7 mmHg). The modifier route showed larger peak SVR and heart-rate changes in each pair, while its peak MAP rise was slightly smaller. The magnitudes and directions are descriptive; one run per route and target does not establish a statistically reliable route-by-drug interaction.

This smoke-selected dose is a strong perturbation in the simulated model. It gives clear dynamic range, while also producing secondary event and flow changes. The follow-up question is whether those route differences repeat under independent fresh initializations; this run alone does not answer that. No fine dose search or clinical interpretation is supported by these results.

## Focused intermediate-pair sodium diagnostic

A follow-up diagnostic repeated the intermediate direct/modifier pair with aortic sodium, blood volume, renal plasma flow, urine production, urine osmolality, left/right ureter flow, and left/right ureter sodium concentration requests. It remains exploratory and uses one fresh trajectory per route and concentration.

Before norepinephrine, aortic sodium was **142.882 mEq/L** in the direct state and **144.901 mEq/L** in the modifier state. Pulse raises the Hypernatremia event above 145 mEq/L, so the modifier state began only 0.10 mEq/L below that threshold. Baseline blood volume differed by less than 1 mL (modifier −0.676 mL). The modifier baseline had lower urine production (1.276 vs 1.848 mL/min), higher urine osmolality (608.4 vs 575.5 mOsm/kg), and lower renal plasma flow (430 vs 708 mL/min).

Using left and right ureter flow multiplied by ureter sodium concentration, baseline urinary sodium mass output was about 6.02 mg/min in the modifier state and 7.48 mg/min in the direct state. During the same 1 µg/mL challenge, the direct state peaked at 144.531 mEq/L without Hypernatremia. The modifier crossed the event threshold at elapsed second 93 (about 33 seconds after infusion began) and peaked at 145.790 mEq/L. At infusion end, modeled blood volume had fallen 13.77 mL in modifier and 4.44 mL in direct; minimum urine production was 0.027 vs 0.735 mL/min. Peak modeled urinary sodium output was 15.09 vs 18.55 mg/min, respectively.

The same total norepinephrine mass was then delivered at 4 µg/mL and one quarter the rate: 0.06426 mL/s, or 19.278 mL nominal volume equivalent rather than 77.111 mL. For each route, every recorded numeric trajectory was identical between the 1 and 4 µg/mL runs (maximum absolute difference 0.0). This confirms that the pinned implementation responds to the concentration-rate product. It does **not** test a fourfold reduction in a modeled fluid load: the infusion routine does not add carrier fluid to the fluid system. A vehicle-only infusion would therefore not be informative for fluid loading in this Pulse revision.

This diagnostic supports the threshold-proximity explanation: the modifier state starts with higher sodium and crosses a fixed event threshold under the same drug mass input while its renal/urine trajectories differ. It does not isolate whether that starting sodium difference, renal perfusion, urine water handling, sodium handling, or another state variable drives the crossing. The pinned build exposes sodium concentration, renal plasma flow, urine production/osmolality, and ureter sodium concentration/flow. No ADH or aldosterone scalar/request was found in this revision. The enriched compact table is [hypernatremia_diagnostic_v2.csv](../results/pressure_matched_drug_response/hypernatremia_diagnostic_v2.csv); detailed traces and logs remain private.
