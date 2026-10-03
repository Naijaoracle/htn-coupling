# First mechanistic forecast experiment

## Question

Among a predeclared family of plausible Pulse exercise–recovery trajectories, which trajectories are compatible with the H10 RR-derived heart-rate context from 0–30 s, and what distribution of Pulse heart rates do they project over 31–60 s?

This is an **HR-constrained mechanistic projection**. It is not a claim that H10 identifies the participant's full cardiovascular state or Pulse parameters.

## Frozen comparison

- **Target:** `h10_raw_ecg_rr_bpm` from H10, in the selected recovery take.
- **Visible measurements:** the complete measured take from 0–60 s.
- **Context:** H10 samples at or before 30 s only. The TimesFM input uses the regular 1 Hz grid at 1–30 s, formed without extrapolation and with interpolation only across gaps no wider than 4.1 s.
- **Pulse conditioning points:** six fixed block endpoints at 5, 10, 15, 20, 25 and 30 s. The other second-by-second context values are not treated as independent likelihood observations.
- **Held-out region:** 31–60 s. No held-out H10 value may be used in candidate generation, candidate weighting, or model selection.
- **Scoring:** use only actual measured H10 timestamps in the forecast horizon. Do not interpolate or extrapolate the held-out observations.
- **Reference baselines:** persistence at the last context value, and a least-squares straight line fitted to context values from 21–30 s and projected forward.
- **ML branch:** TimesFM-3 forecast of H10 RR-derived HR.
- **Mechanistic branch:** Pulse exercise–recovery ensemble, weighted from H10 context only.

The six conditioning blocks use equal prior candidate weights and the declared Gaussian discrepancy rule:

\[
\log \tilde w_j = -\frac{1}{2\sigma^2}
\sum_{t\in\{5,10,15,20,25,30\}}
\left(HR^{Pulse}_j(t)-HR^{H10}(t)\right)^2.
\]

Weights are normalized across candidates. `conditioning_sigma_bpm` must be declared before inspecting the held-out scores and must be identical on every candidate row. No default value is supplied by the application.

## Reported outputs

- Pulse ensemble weighted median and 10th–90th percentile interval for seconds 31–60;
- number of candidates and effective ensemble size \(1/\sum_j w_j^2\);
- conditioning-block RMSE and posterior weight, with the highest-weight member identified only as a diagnostic;
- MAE and RMSE for TimesFM, Pulse ensemble median, persistence and linear trend, all on the same measured held-out timestamps;
- central 80% interval coverage and mean interval width for TimesFM and Pulse;
- predicted and observed heart-rate change over the common scored span, plus the change error.

An 80% empirical ensemble interval is not automatically a calibrated 80% predictive interval. Coverage is descriptive for this experiment.

## Frozen candidate-generating experiment

Pulse's documented `Exercise` action accepts an intensity from 0 to 1 and an intensity of 0 removes the action. Pulse defines intensity as requested work rate relative to the body's maximal work rate; this is not a MET scale. See the official [scenario action specification](https://pulse.kitware.com/_scenario_file.html) and [exercise energy methodology](https://pulse.kitware.com/_energy_methodology.html). The Adult Compendium's jumping-jack MET value may contextualize activity level, but it is not converted into Pulse intensity.

The predeclared factorial candidate family is:

| Input | Frozen values |
|---|---|
| Pulse baseline | Unmodified `StandardMale` stock patient from a frozen stabilized checkpoint; no cardiovascular modifiers |
| Exercise action | Constant `Exercise` intensity, followed by a new `Exercise` action at intensity 0 |
| Exercise intensity | 0.05, 0.10, 0.15, 0.20, 0.25, 0.30 |
| Exercise duration | 30, 45, 60 s |
| Cessation-to-Recovery-1-origin delay | 0, 5, 10, 15 s at rest after intensity is set to 0 |
| Recovery action | Abrupt cessation; no taper |
| Additional autonomic/recovery parameter | None |
| Candidate prior | Equal |
| Conditioning discrepancy | \(\sigma=10\) bpm, treated as model discrepancy, not H10 measurement noise |
| Candidate count | 6 × 3 × 4 = 72 |

The six conditioning points and 31–60 s evaluation are as defined above. Each run starts from the same named stable checkpoint. It applies the exercise action for the selected duration, sets intensity to zero, advances through the selected delay, defines that moment as Recovery 1 time zero, and exports the following 60 s of Pulse HR. The delay family brackets capture timing; it does not claim that 30 jumping jacks correspond to any one Pulse intensity. No recovery parameter or candidate range is changed after inspecting the H10 context or held-out results.

The stabilized checkpoint used for this experiment has SHA-256 `2f1c4416afec84b1b903988aa98833b7e672169a072c6f826a45aa90a7ef2115` and reports Pulse `4.3.2-e8a36497b`. Candidate exports must carry that baseline identity, model version, exercise intensity, duration, delay, and `conditioning_sigma_bpm=10`.

Candidate validity is limited to successful engine initialization, accepted action processing, completion through the 60 s projection horizon, and finite HR values throughout the exported interval. Do not reject a completed candidate because its values look unexpected or because it disagrees with held-out H10. If the full family poorly represents the 0–30 s context, report that result; do not widen the family after seeing 31–60 s.

This is a retrospective forecast evaluation with a frozen pre-generation protocol: the future samples are withheld from software conditioning and model selection, but the investigator has already seen these recordings. The same 72 H10-independent Pulse trajectories are reused unchanged against Recovery 1, Recovery 2 and Recovery 3 contexts. Each recovery is weighted separately from its own 0–30 s H10 history and scored separately; the three takes are repeated segments, not independent participants.

OpenBF is not used to produce this HR target. The first mechanistic HR projection is generated by Pulse; OpenBF can later consume corresponding Pulse vascular boundary/state outputs for a separate pressure/flow or synthetic-observation target. The existing 0.84 s Pulse/OpenBF representative cycle is not an exercise/recovery trajectory and is ineligible.

## Claim boundary

Use the dashboard labels:

- **ML forecast of H10 RR-derived HR**
- **Mechanistic projection: Pulse exercise–recovery ensemble constrained using H10 HR from 0–30 s**
- **Held-out observation: H10 RR-derived HR from 31–60 s**

Do not label the projection an individualized forecast or state estimate. A later multimodal state-inference layer would be needed for that stronger claim.
