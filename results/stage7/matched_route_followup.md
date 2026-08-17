# Matched-route and mechanistic follow-up (17 August 2026)

## Renal flow

Direct creation at requested 120/80 and 150/90 stabilized at approximately 120.01/80.09 and 148.59/90.70 mmHg. Left-kidney flow rose from 508.17 to 660.28 mL/min (ratio **1.30**).

The modifier route has no exact 150/90 cell in the released multiplier grid. The closest cells were R=1.15,C=0.95 (114.95/75.35 at the recorded endpoint) and R=2.0,C=0.4 (152.16/87.79). Left-kidney flow fell from 438.46 to 268.53 mL/min (ratio **0.61**). The pressure residuals and the lack of an exact modifier cell are recorded; nevertheless the two routes show opposite renal directions in the closest available matched sweep.

## P2 held-pressure test

A resistance step raised MAP from approximately 95 to 110--113 mmHg and held it there for several minutes. The logged midpoint remained approximately 95.00 mmHg through 300 s rather than following the Moreira upward-reset trajectory. The later trace drifted only after pressure fell again. This does **not** reproduce the expected upward-reset demonstration (26% at 2 min, approximately 43% at 20 min); P2 remains implementation-incomplete pending diagnosis of why the upward branch is not updating under a held pressure step.

## Established mechanistic haemorrhage

After the P5 separation correction, the all-parameter established direct patient completed the full haemorrhage scenario. Baseline MAP was 121.0 mmHg; the 30%-of-own-baseline threshold was 84.7 mmHg and was crossed at 607.76 s. The Stage 5 modifier combined phenotype had median 30% fractional-MAP-fall time 417.0 s. The mechanistic direct route therefore did not reproduce the modifier ordering; it tolerated the fractional fall approximately 191 s longer. This is a real route/phenotype difference, not a claim of matched patient equivalence.


## P2 lifecycle correction

The upward failure was traced to `NervousModel::Initialize()` resetting the Stage 7 midpoint whenever the mechanics action reinitialized the engine. Commit `e258eae8` preserves an active reset state across reinitialization and still uses the declared chronic midpoint on first initialization. The corrected held-step trace moved the midpoint from 95.00 to 96.44 mmHg at 60 s, 98.33 mmHg at 120 s, and 102.40 mmHg at 300 s while MAP was approximately 113, 110 and 110 mmHg. The long fixture subsequently lost the pressure step, so its 20- and 30-minute values are not a valid constant-pressure Moreira comparison; a pressure-hold fixture is still needed for those checkpoints.

## Same-route mechanistic comparison

Using the same direct 150/90 patient body, default mechanisms crossed a 30%-of-baseline MAP fall at 515.64 s, while the established preset crossed at 607.78 s. The 92.14-second difference is interpretable as a within-route mechanism effect. It is not yet a cohort result: the requested multi-body direct comparison remains outstanding.
