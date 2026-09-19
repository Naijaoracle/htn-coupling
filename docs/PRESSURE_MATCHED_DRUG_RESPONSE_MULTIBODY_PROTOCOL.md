# Pressure matched norepinephrine response across bodies: protocol

**Status:** Confirmatory model-characterisation precommit. The exact panel, engine, target, pressure criteria, dose, and analysis are fixed here and in the linked configuration before any Pulse initialization for this study.
**Prepared:** 2026-09-19.

## Question and scope

Across a fixed panel of four Pulse bodies, can direct patient initialization and cardiovascular mechanics modification produce stationary states matched at 140/90 mmHg, and do those pressure-matched states show different responses to the same weight-based norepinephrine challenge?

This is a four-body model-characterisation panel. It is not a random sample and does not estimate a population effect or support a clinical inference. Each body is matched independently. A modifier coordinate accepted for one body must not be transferred to another.

## Engine and body panel

- Pulse source revision: `99e2d50cb7d0e0893690bf113d2f7924bb933f56`.
- Python binding source hash: `99e2d50cb`.
- Python binding binary SHA-256: `1f36fbd303b711ccfb1fbb96337b283221705fc6a5cf7214fc8ad14f838523d3`.
- Pulse C library SHA-256: `60d82177db58b2c502f738c37719489813b84127ed3baed884e564977165a7a6`.
- Stage 0 reference-trace CSV SHA-256: `c22dd3e5153ab19d18a9efef8c6e52a4a3a8575e43b317020181983c5e3fb932`.
- Stage 0 gate-manifest SHA-256: `1b0c930372fc7c82982f4ecccda7dab34569b03c2a8bd678c78194e79b7a56eb`.
- Body-panel source SHA-256: `d317a0d02fa37ec43bff2ee9275df4a5ed96fa5b7e94605a02ec9caca428ddf4`.
- The panel is copied, without further selection, from `config/stage5_acute_panel_v1.json`. That panel selected the lowest- and highest-BMI admissible body within each sex from the fixed anonymous Stage 2 sample, restricted to ages 40–65; pressure was not a selection variable.

| Body | Sex | Age (y) | Height (cm) | Weight (kg) | BMI (kg/m²) |
|:--|:--|--:|--:|--:|--:|
| male_low_bmi | Male | 41 | 186.6 | 56.6 | 16.26 |
| male_high_bmi | Male | 64 | 163.5 | 80.1 | 29.96 |
| female_low_bmi | Female | 52 | 155.5 | 39.6 | 16.38 |
| female_high_bmi | Female | 51 | 157.5 | 74.4 | 29.99 |

Initialize each body from its sex, age, height, and weight using a pinned patient JSON payload. Keep Pulse's derived body-composition calculation by omitting `BodyFatFraction`. Heart rate and respiration baseline requests remain the common 72/min and 12/min used by the preceding Stage 5 panel. Serialize each body's 114/73.5 mmHg unmodified initialized state for modifier-route evaluations. Direct states use the same body attributes and a 140/90 mmHg baseline request with the declared Stage 6 pressure envelope. No body or body-specific parameter is replaced based on its pressure-matching or drug-response result.

## Pressure matching

The sole target is SBP/DBP 140/90 mmHg. For each body:

1. Initialize and measure that body's direct 140/90 state using the 12-second stable trace. Require stationarity under four consecutive 3-second bin medians; the range of bin medians must be at most 0.25 mmHg for both SBP and DBP.
2. Search the modifier domain `R ∈ [1.0, 2.0]`, `C ∈ [0.4, 1.0]`, where `R` is systemic resistance multiplier and `C` is arterial compliance multiplier. Start at `(R=1.715, C=0.595)`, the previously confirmed StandardMale intermediate solution. It is only a starting point, not an assumed match.
3. Use measured SBP and DBP residuals to estimate the local 2×2 finite-difference Jacobian and take bounded Newton steps. Use central differences with initial coordinate steps `ΔR=0.1`, `ΔC=0.1`; cap each coordinate step at 0.25 and backtrack a non-improving proposal by halves, at most three times. Stop if a measured point passes both pressure residuals and stationarity gates.
4. Limit the search to four Newton iterations and 20 unique modifier evaluations per body. Save every measured point. Do not interpolate a final match, expand the domain, relax the pressure or stationarity tolerance, or replace a body after seeing a failure.
5. Independently initialize the accepted modifier point twice from fresh Pulse processes. Both must pass stationarity and match that body's direct state within 0.25 mmHg in SBP and DBP. If either confirmation fails, that body has no accepted pair and receives no drug challenge.

Each body's unmodified initialized state and direct 140/90 state are distinct routes under study. The former is the starting state for the modifier search; the latter is measured directly under the target patient initialization. Record hashes of the state, patient payload, engine binding, protocol, and configuration.

## Norepinephrine challenge

Use a fixed weight-based dose of `0.20 µg/kg/min` at `1 µg/mL` for 300 seconds, followed by 300 seconds of observation. Start at elapsed second 60. Calculate a body-specific infusion rate from that body's stated mass:

`rate (mL/s) = dose (µg/kg/min) × mass (kg) / (60 × concentration (µg/mL))`.

The resulting rates are 0.1886666667 mL/s (male_low_bmi), 0.267 mL/s (male_high_bmi), 0.132 mL/s (female_low_bmi), and 0.248 mL/s (female_high_bmi). At the pinned engine revision, infusion adds substance mass but does not transfer carrier fluid into the cardiovascular fluid system. Record the nominal volume delivered, but do not interpret it as a modeled fluid load.

For each accepted body, run each route twice in fresh Pulse processes (eight runs per accepted body pair). For each repeat, both routes wait at a pre-infusion pair gate. Administer drug to neither route unless each challenged baseline passes stationarity and both measured SBP/DBP values are within 0.25 mmHg of the confirmed screened pair. Use identical dose per kg, concentration, start time, and duration within that body pair. No dose adjustment is allowed based on body, route, or observed response.

## Measurements and analysis

Sample the same cardiovascular, renal, sodium, volume, urine, and event outputs as the single-body confirmatory protocol, at 1-second intervals from elapsed second 1 through 660. Use `[30,60)` for pre-infusion baseline medians. Report every body and repeat separately, including all pressure-matching evaluations, confirmation outcomes, baseline state, infusion rate, full trace, events, and run validity.

Primary endpoints are the peak 10-second rolling-median change in SVR and maximum absolute 10-second rolling-median change in heart rate, each relative to that run's own `[30,60)` baseline. Report direct-minus-modifier contrasts within each body and repeat. Also report MAP, SBP, DBP, cardiac output, renal plasma flow, urine production, sodium, cerebral and renal flow, event timing, and complete trajectories.

The four bodies are the cross-body units. The two fresh-process repeats assess deterministic numerical reproducibility and do not increase the number of bodies. Report directional consistency across the fixed panel descriptively; do not treat repeated runs as biological replicates or calculate a population-level inference. Preserve no-match, invalid, adverse-event, and interrupted cases; none is silently replaced or omitted.

## Execution lock

The exact machine-readable configuration is `config/pressure_matched_drug_response_multibody_v1.json`. The runner, protocol, configuration, helper logic, and tests must be committed before any model initialization. Each attempt receives a unique results directory under the ignored `results/pressure_matched_drug_response_multibody/private/` namespace; only compact aggregates, the manifest, and this protocol are eligible for tracking. Full traces, logs, and generated individual patient/state files remain private.

No multi-body initialization or response run has been performed as of this precommit.
