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
