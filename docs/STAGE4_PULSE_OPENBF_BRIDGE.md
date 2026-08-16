# Stage 4: Pulse-to-openBF bridge

## Outcome

**The original predeclared aortic acceptance gate failed.** This historical gate result is retained below. Stage 4b subsequently attributed the gap to the Pulse inlet and adopted an amended physiological-plausibility gate; carotid plausibility and sensitivity were then completed. See `STAGE4B_PULSE_PRESSURE_DIAGNOSIS.md` and `STAGE4_COMPLETION.md`.

## Interface and inlet checks

The versioned interface is `config/stage4_interface_v1.json`. It transfers one stable Pulse `Aorta-InFlow` cycle, cycle length, MAP, systemic vascular resistance, heart rate, and provenance. Geometry and distributed material properties remain ADAN56-owned. All conversions are isolated in `scripts/bridge_units.py` and covered by four unit tests.

Eight stable StandardMale cycles were phase-aligned and averaged onto 201 points. Their periods were all 0.840 s and the maximum cycle-to-mean flow RMSE was 0.008% of peak flow. The periodic endpoint error was zero. The integral implied 5.739 L/min versus Pulse's reported 5.787 L/min, a 0.83% difference. Exact zero flow is represented as `1e-10 m3/s`, matching ADAN56's inlet convention; the cycle begins immediately before systolic upstroke. An earlier peak-start/exact-zero probe generated non-finite openBF pressure and was rejected before either acceptance arm was interpreted.

## Resistance arms

Published ADAN56 terminal resistance is 0.892 mmHg·s/mL in parallel; Pulse reported 0.939 mmHg·s/mL. Arm A retained published R1, R2, and Cc. Arm B multiplied every R1 and R2 by 1.0533 and left Cc published, deliberately isolating mean-resistance matching. Both configurations use the unmodified openBF solver at revision `928c046906687c1347bf5496b47325acd0b2c032`.

| arm | openBF SBP | openBF DBP | openBF MAP | openBF PP | MAP error vs Pulse | PP error vs Pulse | gate |
|---|---:|---:|---:|---:|---:|---:|---|
| published | 95.36 | 74.78 | 87.27 | 20.57 | -8.05 | -20.07 | fail |
| resistance-scaled | 99.57 | 79.12 | 91.44 | 20.45 | -3.88 | -20.19 | fail |

The predeclared tolerances were ±5 mmHg for mean pressure and ±10 mmHg for pulse pressure against Pulse's aortic 95.32 mmHg mean and 40.64 mmHg pulse pressure. The scaled arm passed the mean criterion but failed pulse pressure by roughly 20 mmHg. The unscaled arm failed both.

## Interpretation

The bridge is correct enough to expose a specific incompatibility, not to support downstream claims. Flow units, cycle length, flow integral, periodicity, and solver convergence passed. A single global terminal-resistance scale controls mean pressure in the expected direction but does not repair the roughly twofold pulse-pressure mismatch. That mismatch implicates the inlet-waveform/material-compliance combination rather than mean resistance alone. Fitting Cc merely to pass this gate would be a new calibration arm and must be predeclared and justified, not silently folded into Stage 4.

The two end-to-end base runs took 54.4 s (published) and 59.3 s (scaled), including Julia/openBF startup; openBF itself converged in four and five cycles respectively. Because neither arm passed the complete aortic gate, the protocol correctly blocked carotid morphology, inlet sensitivity, and Stage 5 hypertension propagation.

## Acceptance criteria

1. Stage 0 byte identity: pass.
2. Extended sweep: complete; practical flattening plus one censored non-convergence recorded.
3. Versioned interface and tested conversions: pass.
4. Stable, periodic inlet with consistent flow integral: pass.
5. Both resistance arms: run and reported.
6. Original aortic agreement: **fail**; amended Stage 4b gate: **pass** for the resistance-scaled arm.
7. Carotid plausibility: subsequently **pass** at both distal references under the amended gate.
8. Inlet sensitivity: subsequently quantified, including the isolated 2x wall-stiffness comparator.
9. Runtime: recorded.

## Artefacts

- `results/stage4/pulse_aortic_inlet.dat` and `pulse_inlet_metadata.json`
- generated unscaled and scaled YAML/inlet pairs under `results/stage4/configs`
- `results/stage4/aortic_agreement.csv`, `aortic_gate.json`, and `aortic_agreement.png`
