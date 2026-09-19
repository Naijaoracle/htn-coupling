# Pressure matched norepinephrine response: confirmatory results

## Scope and provenance

This is the confirmatory StandardMale model run performed under [PRESSURE_MATCHED_DRUG_RESPONSE_CONFIRMATORY_PROTOCOL.md](PRESSURE_MATCHED_DRUG_RESPONSE_CONFIRMATORY_PROTOCOL.md). The exploratory dose selection and sodium diagnostic are reported separately in [PRESSURE_MATCHED_DRUG_RESPONSE_RESULTS.md](PRESSURE_MATCHED_DRUG_RESPONSE_RESULTS.md); those exploratory runs are not included here.

The committed protocol/configuration, Pulse revision, Stage 0 gate, input-state hashes, runner hashes, and compact result hashes are recorded in [manifest_confirmation_02.json](../results/pressure_matched_drug_response_confirmatory/manifest_confirmation_02.json). Full traces and logs remain in the ignored private results tree.

The first execution attempt was aborted after a runner pipe-handling error. All six no-drug screen pairs passed. Two mild challenge pairs passed the fresh-baseline gate, but their processes were interrupted before complete response traces were collected; whether a dose step occurred cannot be established. An intermediate pair was stopped before its challenged-baseline gate. These partial results are invalid, retained privately, and excluded. The runner fix and an attempt-specific output label were committed before the clean execution. The clean results below are from `confirmation_02` only.

## Design and validity

The clean execution completed six independent no-drug screening pairs and 12 challenged runs: three pressure targets × two routes × two fresh-process repetitions. Each direct/modifier challenge pair was synchronized at a pre-infusion gate; both routes had to pass pressure matching and stationarity before either received the fixed infusion.

All six screening pairs and all six challenged-pair gates passed. All 12 challenge traces contain the full 660 one-second samples from pre-infusion through follow-up. Every infusion and post-infusion observation completed. No run entered an irreversible state. For each target and route, the two numeric traces and event onset times were identical; the maximum absolute numeric difference was 0.0 across all six repeat comparisons. These are deterministic model repeats, not biological replicates.

The intervention was fixed at 0.20 µg/kg/min norepinephrine, 1 µg/mL, 0.25703567633333335 mL/s for 300 seconds, followed by 300 seconds of observation. The nominal volume-equivalent was 77.1107029 mL. Pulse revision `99e2d50cb7d0e0893690bf113d2f7924bb933f56` does not transfer carrier fluid into the cardiovascular fluid system, so that volume-equivalent is intervention provenance and not a modeled fluid load.

## Pressure match and cardiovascular response

Entries show direct/modifier route values. Baseline pressures met the ±0.25 mmHg pair criterion in every target and repeat.

| Target | Baseline SBP/DBP (mmHg), direct / modifier | Peak ΔMAP (mmHg), direct / modifier | Peak ΔSVR (mmHg·s/mL), direct / modifier | Maximum |ΔHR| (/min), direct / modifier | Minimum ΔCO (L/min), direct / modifier |
|:--|:--|:--|:--|:--|:--|
| Mild | 129.018/80.187 ; 128.857/80.268 | 25.324 / 24.925 | 0.456 / 0.595 | 6.958 / 9.564 | −0.870 / −0.803 |
| Intermediate | 139.954/89.761 ; 139.789/89.581 | 27.909 / 26.948 | 0.533 / 0.857 | 6.749 / 11.906 | −0.956 / −0.800 |
| Higher | 148.603/90.703 ; 148.664/90.738 | 29.081 / 27.707 | 0.507 / 1.078 | 5.901 / 12.851 | −0.936 / −0.824 |

Across both numerical repeats, direct minus modifier peak MAP change was +0.399, +0.961, and +1.374 mmHg at mild, intermediate, and higher targets. Modifier states had the larger SVR and absolute heart-rate responses at every target, while direct states had slightly larger MAP rises and CO reductions. The route contrasts repeat exactly in this deterministic build. Their magnitude should be read as model effect estimates for this one body and dose, without population or clinical inference.

Per-run endpoints and baseline states are in [aggregate_confirmation_02.csv](../results/pressure_matched_drug_response_confirmatory/aggregate_confirmation_02.csv); paired route contrasts are in [paired_contrasts_confirmation_02.csv](../results/pressure_matched_drug_response_confirmatory/paired_contrasts_confirmation_02.csv). Repeat comparisons are in [repeatability_confirmation_02.csv](../results/pressure_matched_drug_response_confirmatory/repeatability_confirmation_02.csv).

## Sodium and renal outcomes

The 145 mEq/L Hypernatremia threshold and its event were prespecified outcomes. No run was excluded or dose-adjusted because of sodium.

| Target | Baseline sodium (mEq/L), direct / modifier | Baseline renal plasma flow (mL/min), direct / modifier | Baseline urine production (mL/min), direct / modifier | Direct sodium peak / event | Modifier sodium peak / event |
|:--|:--|:--|:--|:--|:--|
| Mild | 142.782 / 144.567 | 648.9 / 490.9 | 1.413 / 1.027 | 144.568 / none | 145.749 / elapsed 261 s, infusion |
| Intermediate | 142.882 / 144.901 | 707.8 / 430.3 | 1.848 / 1.276 | 144.531 / none | 145.790 / elapsed 93 s, infusion |
| Higher | 142.932 / 145.216 | 775.7 / 389.8 | 2.322 / 1.210 | 144.643 / none | 145.802 / active before infusion; first observed at elapsed 1 s |

Each row applies to both exact numerical repeats. At mild and intermediate targets, modifier sodium began below 145 mEq/L and the event first appeared during infusion. At the higher target, modifier sodium was already above the event threshold at baseline, so Hypernatremia is a pre-existing state rather than an infusion-onset event. No direct route crossed the threshold. The modifier states also had lower baseline renal plasma flow and urine production at every target.

The experiment establishes the observed model outcomes and their repeatability. It does not isolate why sodium rises or establish that renal perfusion caused the threshold crossing. The sodium findings remain a distinct prespecified outcome alongside the cardiovascular response.

## Interpretation

Under the pinned Pulse configuration, direct and cardiovascular-mechanics-modifier states with matched baseline SBP/DBP showed repeatable differences in several norepinephrine response endpoints. The strongest differences were in SVR and heart-rate response; MAP changes were closer. Sodium outcomes also differed by route, including a pre-existing higher-target modifier event.

This confirms a route-dependent response pattern within one StandardMale model. The target severities are distinct simulated states, while the two repeats per state establish numerical reproducibility only. They do not establish a population-level or clinical treatment interaction.
