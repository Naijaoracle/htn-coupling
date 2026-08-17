# Stage 7 parameter isolation (same direct 150/90 body)

All runs used the same haemorrhage scenario and fractional MAP endpoint. Default direct mechanics crossed a 30%-of-baseline MAP fall at **515.64 s**.

| Variant | 30% fractional-MAP time | Result |
|---|---:|---|
| Gain 0.40 only | 591.34 s | stabilised |
| Chronic midpoint 110 only | 597.60 s | stabilised |
| Chamber Ees 1.20 only | 524.40 s | stabilised |
| Intrinsic contractility 0.92 only | — | **failed initial circuit tuning / irreversible state** |
| All established parameters | 607.78 s | stabilised |

The 92.14-second combined delay is therefore dominated by baroreflex gain/midpoint changes; chamber Ees alone has a small effect, and the isolated contractility reduction cannot be instantiated at this direct 150/90 operating point. The combined preset is not a simple sum of independently viable mechanisms.

P2's corrected upward branch moved the midpoint from 95.00 to 96.44 mmHg at 60 s, 98.33 at 120 s, and 102.40 at 300 s during the step test. The pressure later decayed, so 20- and 30-minute Moreira checkpoints remain unvalidated.


## Absolute MAP 65 endpoint

The same traces crossed absolute MAP 65 at 549.24 s (default), 647.18 s (midpoint-only), and 557.42 s (chamber-only). Gain-only and combined did not cross MAP 65 before the 2,155-second scenario ended. Thus the fractional and absolute endpoints do not reverse the ordering; the gain/midpoint presets provide stronger pressure preservation in both definitions.

## Pressure-hold attempt

A repeated-action fixture re-applied the resistance step every 300 s, but the engine entered cardiovascular collapse at 952.22 s. It did not provide a valid 20- or 30-minute constant-pressure trace. P2 remains calibrated only qualitatively at the early 60--300 s checkpoints.


## Gain-direction counter-test

A gain multiplier of 2.0 did not reproduce the apparent protection: the same direct 150/90 haemorrhage run entered cardiovascular collapse at 517.0 s and failed with negative left-heart volume at 519.08 s. The implementation multiplies the effector-state update increments directly, so this counter-test confirms the field is not being applied as a reciprocal or sign-inverted scalar. The surprising protection at gain 0.40 is therefore an engine dynamical interaction, not a simple gain-direction coding error.

## Stabilisation manifold

The isolated contractility failure, the gain-2 collapse, and the previously observed non-monotonic pressure-grid failures are recorded together as a non-monotonic stabilisation manifold: parameter combinations can fail at ordinary pressures while more extreme combinations succeed. Calibration must treat non-convergence as an expected domain outcome.


## Gain trace audit

The 600-second traces requested the actual effector outputs. At 300 s, gain 1.0 versus gain 0.40 produced HR scales 1.386 versus 1.435 and resistance scales 1.227 versus 1.238, at MAP 118.5 versus 117.8 mmHg. The lower-gain trace therefore does not settle at a lower effector level; it follows a different transient trajectory. This is consistent with gain multiplying the Euler update increment (including the decay term), i.e. changing adaptation rate, not defining a steady-state reflex sensitivity. At 600 s the trajectories diverge into different collapse dynamics (MAP 42.8 versus 83.8), so the endpoint difference is not a valid physiological gain comparison. P3 is therefore a numerical update-rate control until redesigned.


## P3 drive-only correction

Pulse commit `a04eaa690` changes P3 so gain multiplies only the reflex drive; the state-decay term is unscaled. P2 was audited separately: its reset fraction defines the target offset and the first-order relaxation remains unscaled, so it is not subject to the same cancellation.

The corrected 600-second traces behave directionally: gain 2.0 drives HR/resistance scales to approximately 1.96/1.83 before failing at 74 s; gain 0.40 produces lower scales (0.77/1.01 at 600 s) and fails at 617 s; gain 1.0 reaches 1.71/1.17 and fails later. This is now a sensitivity-like direction, but the high-gain instability and low-gain collapse mean the usable range still needs bounded calibration. The previous 92-second mechanism result is invalidated.


## Matched-time corrected P3 comparison

At 60 s after the bleed began, before the divergent failures: gain 0.40 gave HR/resistance scales **0.839/0.895**; gain 1.0 gave **1.048/1.022**; gain 2.0 gave **1.614/1.628**. The corrected drive-only implementation therefore has the expected common-time ordering. There are no BLIM/clamp calls on these normalized effector scales. Gain 2 reaches a rapidly overdriven trajectory and fails at 74 s; this is an unbounded numerical instability, not validated physiology.

## Corrected isolation endpoint

The corrected gain 0.40 trace crossed the 30%-fractional-MAP endpoint at **459.54 s**; the corrected combined preset crossed at **427.14 s**. The default direct trace remains 515.64 s. These are replacement numbers for the old P3 results, but the gain-2 instability and the short-run failures mean P3 still requires bounded calibration before mechanistic interpretation.


## Gain range sweep

Corrected P3 gain sweep (common 600-second fixture) found failure times of approximately 649 s (0.2), 617 s (0.4), 680 s (0.8), and 200 s (1.5). Gains 0.6, 1.0 and 1.2 did not fail within the recorded 600-second window, although the driver’s stabilization extension is logged separately. At 60 s, HR/resistance scales increased monotonically with gain: 0.2 = 0.764/0.882, 0.4 = 0.839/0.895, 0.8 = 0.992/0.930, 1.0 = 1.048/1.022, 1.2 = 1.116/1.122, 1.5 = 1.277/1.298. No effector clamp is present in this path.

## P2 fraction/time-constant audit

Changing the upward/downward fraction from 0.45/0.35 to 0.10/0.10 gave midpoint 95.81 mmHg at 120 s and 97.10 at 300 s; changing to 0.80/0.80 gave 100.43 and 105.55. Changing time constants while holding fraction at 0.45/0.35 gave midpoint 100.85 at 120 s and 106.05 at 300 s for fast tau 60 s, versus 98.25 and 102.27 for slow tau 3,000 s. The fraction and relaxation controls therefore affect distinct parts of the trajectory; neither is a shared drive/decay step-size multiplier.


## Failure classification

Low-gain failures are exsanguination/collapse trajectories: gain 0.2 entered hypovolemic shock at 613.02 s and intracranial hypotension at 613.56 s before the negative pulmonary-vein volume at 648.8 s; gain 0.4 entered hypovolemic shock at 610.6 s before negative volume at 617.36 s. Gain 1.5 failed at 199.98 s with negative pulmonary-vein volume and tachycardia, without preceding hypovolemic-shock logging, while its effector scales were rapidly increasing. These are distinct low-gain physiological collapse versus high-gain overdrive/numerical failure modes; failure time is not a monotonic gain range.

The stock engine does clamp the final heart-driver frequency to the patient HR minimum/maximum, but it does not clamp the baroreceptor normalized HR/resistance/compliance scales. Thus the existing upstream bound is downstream and does not protect the effector state or systemic-resistance path.
