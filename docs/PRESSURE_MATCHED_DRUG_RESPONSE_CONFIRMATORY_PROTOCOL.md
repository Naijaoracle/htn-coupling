# Pressure matched norepinephrine response: confirmatory protocol

**Status:** Confirmatory precommit. This protocol and its configuration must be committed before any initialization. It follows an exploratory StandardMale study and does not retroactively make that study precommitted.
**Prepared:** 2026-09-19.

## 1. Question and scope

In the pinned Pulse model, do direct patient initialization and cardiovascular mechanics modification states with matched baseline SBP and DBP show different responses to one fixed norepinephrine infusion?

This is a single-body model confirmation using StandardMale. Two fresh-process runs per state assess numerical repeatability; they are not biological or population replicates. No clinical dosing or patient-care interpretation is intended.

The exploratory dose-selection, paired results, and sodium diagnostic are documented in [PRESSURE_MATCHED_DRUG_RESPONSE_RESULTS.md](PRESSURE_MATCHED_DRUG_RESPONSE_RESULTS.md). Confirmatory outcomes must be recorded separately and must not be merged with the exploratory runs.

## 2. Pinned model and states

- Pulse revision: `99e2d50cb7d0e0893690bf113d2f7924bb933f56`.
- Pulse timestep: 0.02 s.
- Stage 0 regression-gate SHA-256: `1b0c930372fc7c82982f4ecccda7dab34569b03c2a8bd678c78194e79b7a56eb`.
- StandardMale modifier source checkpoint SHA-256: `2f1c4416afec84b1b903988aa98833b7e672169a072c6f826a45aa90a7ef2115`.
- Direct patient payload SHA-256 values from the pressure matched v2 experiment:
  - Mild: `cce4d70a81f562df7eae0a2e14d69046e99ba3d358474cb3f2e3bf2ff5fc505d`.
  - Intermediate: `8119bfb3e07a376d35d81753ea4dd6deb07a6e57deb1640f64c4779338448c0d`.
  - Higher: `ab880365e42a6c4aab1836b3cb4d608524a2d1b040f24566f336520567ba556e`.
- Use these exact input states from the pressure matched v2 experiment without regeneration.
- The Pulse checkpoint restart repair is part of the pinned revision. Do not change Pulse source, substance parameters, scenario data, baseline states, or data-request definitions after committing this protocol. Any such change requires a dated amendment before affected runs.

| Target label | Direct patient request | Modifier resistance R | Modifier compliance C |
|:--|:--:|--:|--:|
| Mild | 130/80 mmHg | 1.300 | 0.715 |
| Intermediate | 140/90 mmHg | 1.715 | 0.595 |
| Higher | 150/90 mmHg | 1.985 | 0.460 |

## 3. Norepinephrine intervention

Use the same infusion in all states and repeats:

- Substance: Norepinephrine.
- Weight basis: 170 lb = 77.1107029 kg.
- Dose: 0.20 µg/kg/min.
- Concentration: 1 µg/mL.
- Pulse rate: 0.25703567633333335 mL/s.
- Start: 60 s after the start of the observation window.
- Duration: 300 s.
- Post-infusion observation: 300 s.
- Nominal solution volume delivered: rate × 300 s = 77.1107029 mL (77.112 mL at the rounded rate 0.25704 mL/s).
- Infusion reservoir volume field: 77.11584361352666 mL, leaving a small buffer above the 300-second delivered volume.
- Norepinephrine mass delivered: 77.1107029 µg.

Pulse's infusion handler uses the volume value to deplete the reservoir and adds substance mass from concentration × rate × timestep. In this revision it does not add carrier fluid to the cardiovascular fluid system. The nominal solution volume remains part of the intervention record, but it is not a modeled fluid load. Do not interpret the fourfold-concentration sensitivity as a vehicle-volume control, and do not add a vehicle arm unless the pinned engine's fluid-infusion implementation changes under a prior amendment.

Carrier volume is therefore reported as an explicit administration variable, while its direct fluid-loading effect is absent from this engine path. The 1-to-4 µg/mL sensitivity holds nominal drug delivery fixed and changes the volume field fourfold; it yielded identical trajectories in the exploratory diagnostic. A zero-concentration infusion would still not test fluid loading in this revision.

## 4. Run structure and baseline gate

For each of the three targets, perform two repetitions. Each route and repetition uses a fresh Pulse process and fresh initialization. This gives 12 challenged runs: 3 targets × 2 routes × 2 repetitions.

For each target and repetition:

1. Generate fresh no-drug baseline traces for direct and modifier routes.
2. Record 60 s of output before any infusion. Use the median over elapsed seconds `[30,60)` as the baseline.
3. Require absolute direct-minus-modifier baseline differences of no more than 0.25 mmHg for both SBP and DBP.
4. Apply the stationarity rule over the final 12 s before infusion: divide into four consecutive 3 s bins and require the range of bin medians to be no more than 0.25 mmHg for both SBP and DBP.
5. If either route fails the pair gate, do not challenge either route in that target/repetition. Preserve the traces and record the validity failure. Do not replace a failed run with interpolation or tune R/C after seeing its response.
6. For the actual challenged runs, repeat the same pre-infusion checks in each fresh process. Before administering either route's drug, verify its measured SBP and DBP remain within 0.25 mmHg of the screened peer baseline and that stationarity passes. If either challenged baseline fails, do not administer the drug to either route for that target/repetition.

The pressure gate does not require equality of sodium, renal perfusion, urine output, or other hidden state. For every target, route, and repetition, report baseline sodium concentration, renal plasma flow, and urine production using that run’s `[30,60)` window. Hypernatremia uses Pulse’s fixed 145 mEq/L threshold. Record whether its event is already active before infusion, its first observed onset and whether that occurs during infusion or follow-up, peak sodium, and change from that run’s own baseline. Hypernatremia after a valid baseline is a prespecified model outcome, not a validity failure. Do not exclude a run, adjust the dose, or alter the analysis because of its sodium response.

## 5. Measurements

Sample at 1 s intervals from the start of the 60 s pre-infusion period through the 300 s post-infusion period. Preserve full traces and event logs.

### Primary cardiovascular outputs

- SBP, DBP, MAP.
- Heart rate and cardiac output.
- Systemic vascular resistance.
- Left and right renal blood flow.
- Cerebral blood flow.
- Baroreflex heart-rate, heart-elastance, resistance, and compliance scales.

### Sodium, volume, and renal outputs

- Aortic sodium molarity (mEq/L) and mass concentration (mg/mL).
- Blood volume.
- Renal plasma flow.
- Urine production rate and urine osmolality.
- Left and right ureter inflow and sodium concentration.
- Derived urinary sodium mass output, calculated as the sum of left and right ureter flow × sodium concentration (mg/min).
- Hypernatremia and Diuresis event state, onset, and offset; preserve all other active event transitions as well.

The pinned Pulse public data interface does not expose ADH or aldosterone scalars. Do not infer them from urine output or osmolality.

## 6. Endpoints and comparisons

For each run, calculate changes from that run's own `[30,60)` pre-infusion baseline. Report the complete time series, peak or minimum change, and time of each endpoint for:

- Peak MAP change.
- Peak SBP change.
- Peak DBP change.
- Peak SVR change.
- Minimum cardiac output change.
- Maximum absolute heart-rate change.
- Renal and cerebral flow at peak MAP response and their minimum values.
- Sodium concentration and its event-threshold crossing time.
- Blood volume, urine production, urine osmolality, renal plasma flow, and derived urinary sodium output over time.

For each endpoint, report direct-minus-modifier contrasts separately by target and repetition. Report both absolute and relative changes where defined, the agreement between numerical repeats, and the full trajectory. Do not pool across pressure targets if direction reverses. Do not apply a post hoc significance or minimum-effect threshold; interpret the predeclared effect estimates and their repeat consistency.

## 7. Replication and validity

The second run for each route/target is an independent fresh-process numerical repeat. Compare the complete requested numeric traces and event timing between repeats. Report the maximum absolute difference for each variable. Exact agreement is expected for this deterministic pinned build; any nonzero difference is reported as a repeatability discrepancy, not removed by widening a tolerance after seeing results.

The exploratory runner `scripts/run_pressure_matched_drug_response.py` implements only the original single-run experiment. It is not the confirmatory runner. The confirmatory runner must create fresh Pulse processes for all baseline screens and all 12 challenges, encode target, route, replicate, and phase in unique output paths, and record protocol, configuration, engine, and input-state hashes in a new manifest. For each challenge pair, both fresh processes must report valid pre-infusion baselines and wait at a synchronization gate; neither receives norepinephrine unless both pass the pair pressure gate and stationarity rule. Commit this protocol and configuration first, then commit and test the runner before any confirmatory initialization.

A run is technically invalid only for a predeclared reason: baseline pressure mismatch, failed stationarity, missing/non-finite required output, Pulse runtime failure, or infusion action failure. Preserve and report all invalid traces. A drug-induced Hypernatremia, Diuresis, or IrreversibleState event after a valid baseline remains an outcome and is not silently excluded.

## 8. Interpretation limit

A reproducible route contrast in this experiment establishes a model-level response difference for one StandardMale body under the pinned Pulse configuration. It does not establish a population effect, biological route of hypertension, or clinical treatment response. The prior exploratory runs remain permanently labelled exploratory and are not counted among the confirmatory repeats.

## 9. Pre-run lock

Commit this protocol and its exact configuration before starting any confirmatory initialization. Record the resulting protocol commit SHA, configuration SHA-256, Pulse SHA, Stage 0 gate SHA, and direct/modifier input hashes in the run manifest. No confirmatory initialization or challenge run has been performed as of this precommit.
