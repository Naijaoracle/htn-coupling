# Pressure-matched norepinephrine response across bodies: results

**Status:** Completed confirmatory model-characterisation panel.

**Protocol:** [`PRESSURE_MATCHED_DRUG_RESPONSE_MULTIBODY_PROTOCOL.md`](PRESSURE_MATCHED_DRUG_RESPONSE_MULTIBODY_PROTOCOL.md)

**Experiment revision:** `b3bf60fc3abb24d3a029e359a9a907c2ac4471c4`

**Pulse source revision:** `99e2d50cb7d0e0893690bf113d2f7924bb933f56`

## Result in brief

All four preselected Pulse bodies passed the pressure-match and stationarity criteria. Each accepted modifier state passed both independent confirmations. All 16 norepinephrine runs (four bodies × two routes × two fresh-process repeats) completed, and all eight route-pair gates passed.

For every body, the modifier route had a larger peak SVR rise and a larger maximum absolute heart-rate change than the direct route. The modifier route's peak MAP rise was smaller in all four bodies. The effect sizes varied by body; this is descriptive consistency in this fixed panel, not a population estimate. Each body's two repeats had exactly matching numeric traces and event onset times.

## Pressure matches

The accepted modifier coordinates were selected separately for each body. The pressure residual below is modifier minus that body's measured direct state.

| Body | Direct SBP/DBP (mmHg) | Modifier R, C | Modifier SBP/DBP (mmHg) | Residual SBP/DBP (mmHg) | Search evaluations |
|:--|--:|--:|--:|--:|--:|
| Male, low BMI | 138.599 / 89.779 | 1.682230, 0.629164 | 138.642 / 89.908 | +0.043 / +0.129 | 11 |
| Male, high BMI | 138.711 / 89.656 | 1.691898, 0.612919 | 138.737 / 89.640 | +0.026 / −0.016 | 6 |
| Female, low BMI | 140.584 / 89.290 | 1.706074, 0.594313 | 140.582 / 89.289 | −0.002 / −0.001 | 6 |
| Female, high BMI | 138.545 / 89.541 | 1.674889, 0.623824 | 138.580 / 89.511 | +0.034 / −0.030 | 6 |

All residuals were within the predeclared 0.25 mmHg tolerance. All accepted direct and modifier traces passed the predeclared stationarity gate. Every accepted modifier coordinate passed two fresh-process confirmations. The direct pressure achieved by initialization varied by body; matching was to each body's measured direct state, as specified in the protocol.

## Norepinephrine responses

The fixed challenge was 0.20 µg/kg/min at 1 µg/mL for 300 seconds, followed by 300 seconds of observation. For each body, both routes received the same weight-based dose and infusion rate. The table reports one repeat because the two repeats were numerically identical within every body and route. Contrasts are modifier minus direct; a positive value means a larger increase or absolute change in the modifier route.

| Body | Rate (mL/s) | Peak ΔMAP: direct / modifier (mmHg) | ΔMAP contrast (mmHg) | Peak ΔSVR: direct / modifier (mmHg·s/mL) | ΔSVR contrast | Max |ΔHR|: direct / modifier (beats/min) | |ΔHR| contrast |
|:--|--:|--:|--:|--:|--:|--:|--:|
| Male, low BMI | 0.18867 | 27.647 / 26.975 | −0.672 | 0.547 / 0.884 | +0.337 | 6.861 / 11.892 | +5.031 |
| Male, high BMI | 0.26700 | 27.785 / 26.884 | −0.902 | 0.523 / 0.843 | +0.321 | 6.588 / 11.719 | +5.131 |
| Female, low BMI | 0.13200 | 26.463 / 25.711 | −0.752 | 0.634 / 1.006 | +0.372 | 6.383 / 11.399 | +5.016 |
| Female, high BMI | 0.24800 | 26.779 / 25.578 | −1.201 | 0.564 / 0.899 | +0.336 | 6.189 / 11.052 | +4.863 |

Maximum absolute heart-rate change does not encode response direction. The full trajectories and the separate signed extrema for MAP, SBP, DBP, SVR, heart rate, cardiac output, renal flow, urine, sodium, and other measured variables are retained in the compact aggregates and private traces.

## Repeatability and sodium events

All eight body-by-route comparisons in `repeatability.csv` report exact numeric trace agreement (maximum absolute numeric difference 0.0) and identical event onset times across the two fresh-process repeats.

Baseline sodium was higher in each modifier state than in its matched direct state. Three modifier states were already at or above Pulse's 145 mEq/L hypernatremia threshold at the recorded baseline; the fourth began at 144.770 mEq/L and crossed during the infusion. Hypernatremia was first recorded at elapsed second 1 for the three states already over threshold, and at second 163 for the remaining modifier state. Direct-route traces crossed at seconds 654 and 443 in two bodies; no crossing was recorded in the other two direct traces. These are model event observations, not evidence that the route is clinically harmful or that norepinephrine alone caused the events. The within-build infusion implementation adds substance mass and does not transfer carrier volume into the cardiovascular fluid system.

The modifier baseline states also had lower renal plasma flow and urine production than their paired direct states in all four bodies. This co-occurrence is descriptive; the experiment does not isolate a causal pathway for sodium differences.

## Interpretation and limits

Within this four-body Pulse panel at the intermediate pressure target, matched baseline SBP and DBP did not imply equal modeled cardiovascular or renal state, and the same weight-based norepinephrine challenge produced a consistent directional difference in peak SVR and absolute heart-rate response. The smaller modifier-route MAP rises are comparatively modest.

The panel was fixed in advance to include the low- and high-BMI selections for each sex from the specified Stage 5 panel. It is not a random or representative sample. Four virtual bodies do not establish biological generality, and the two deterministic repeats do not increase the number of bodies. These results support a follow-up study across a broader, prospectively selected body panel; they do not justify a clinical inference.

## Provenance and files

The attempt completed with status `complete`: four accepted pairs, eight completed route-pair replicates, and 16 completed drug runs. Protocol, configuration, runner, helper, tests, body panel, Stage 0 gate, binding, and engine revision hashes are recorded in `results/pressure_matched_drug_response_multibody/manifest.json`.

Tracked compact result files are:

- `aggregate.csv` — route- and repeat-specific baselines and challenge summaries;
- `matched_states.csv` — body-specific accepted pressure matches;
- `paired_contrasts.csv` — within-body, within-repeat endpoint contrasts;
- `repeatability.csv` — exact repeat checks;
- `search_evaluations.csv` — every measured modifier search point;
- `manifest.json` — completion status and provenance locks.

Full traces, logs, and generated individual patient/state files remain in the ignored private attempt directory and are not included in the tracked result set.
