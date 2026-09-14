# Stage 7 implementation status (17 August 2026)

## Completed gates

- Stage 7.1 regional-flow diagnostic: direct 120/80 versus 150/90 completed. The endpoint flows increased in all logged beds (brain 1.0595, kidneys 1.2946, gut 1.0599, liver 1.0576, muscle 1.0584, skin 1.0584, myocardium 1.0600). This is compensated/mixed behavior, not the predicted blanket hypoperfusion; renal and hepatosplanchnic P1 flow targets remain deferred.
- P4 named haemodynamic-stage metadata is implemented in Pulse commit `7ad43da5b`. `Unspecified` preserves upstream behavior; named early/borderline, established, and long-standing values are provenance labels only at this step.
- P3 baroreflex gain is implemented in Pulse commit `877586fce`. It is a dimensionless multiplier on all four reflex effector responses; absent or `1.0` preserves upstream behavior. Values outside the established-hypertension range [0.40, 0.80] warn during setup.

## Regression

The focused SetupPatient test passed, including the named-stage metadata case. The full Stage 0 haemorrhage control completed to 2,155 s in 224.262 s. Its output was 46,098,446 bytes with SHA-256 `462c43248785ce45771b056b53443252414ec066ae50bee0d3b276a42fcfab0a`, identical to the archived control.

The complete distributed verification suite remains unavailable in this checkout because its verification directory and baseline corpus are absent.

- P2 stateful resetting is implemented in Pulse commits `b3e033710` and `15fecf445` (the latter exposes the midpoint as a data request): chronic midpoint, directional rapid-reset fractions, and fast/slow time constants are optional patient fields; omission retains upstream accommodation. A configured two-minute patient smoke test stabilized successfully. A 1,830-second pressure-perturbation demonstration then moved the logged chronic midpoint from 95.00 mmHg to 91.67 mmHg while MAP moved from 95.32 to 89.51 mmHg, showing the intended stateful slow component.
- P5 ventricular controls are implemented in Pulse commits `7705c6fe7` and corrected in `a24cd1b51`: optional chamber end-systolic elastance and intrinsic contractility multipliers are applied to left-ventricular maximum elastance. A configured two-minute smoke test stabilized successfully. The first implementation incorrectly multiplied both fields into Emax and has been corrected in `a24cd1b51`: chamber Ees scales Emax, while intrinsic contractility scales the active (Emax-Emin) excursion. Isolated 120-second reruns now give chamber-only volume range 52.11--138.13 mL, intrinsic-only 65.72--147.25 mL, and combined 55.73--140.83 mL. This demonstrates separability/wiring, not validation of a clinical PV relation. Diastolic beta and relaxation-time parameters remain architecture-dependent and are not guessed.

## P1 decision

The 7.1 diagnostic showed compensated/mixed flow behavior rather than blanket hypoperfusion: direct 120/80 to 150/90 endpoint flow ratios were brain 1.0595, kidneys 1.2946, gut 1.0599, liver 1.0576, muscle 1.0584, skin 1.0584, and myocardium 1.0600. Therefore the proposed renal/hepatosplanchnic flow targets are not applied. P1 remains a documented deferred decision until the circuit compensation mechanism is isolated.

## Final regression

After P5, the full Stage 0 haemorrhage control again completed to 2,155 s in 254.246 s. Output size was 46,098,446 bytes and SHA-256 remained `462c43248785ce45771b056b53443252414ec066ae50bee0d3b276a42fcfab0a`.

The complete distributed verification suite remains unavailable in this checkout because its verification directory and baseline corpus are absent.

## Combined established preset demonstration

The direct 150/90 patient with baroreflex gain 0.40, chronic midpoint 110 mmHg, reset fractions 0.10/0.30, 120/1,500 s time constants, chamber elastance 1.20 and intrinsic contractility 0.92 completed the full 2,155 s haemorrhage scenario. It initialized at 148/90.7 mmHg (MAP 121.0) and remained above MAP 65; at 2,155 s it was 100/71.0 mmHg (MAP 86.3), HR 93.4/min and cardiac output 4.08 L/min. The Standard control crossed MAP 65 at 537.66 s and ended at MAP 71.6 mmHg. This is a mechanism demonstration, not a matched comparison: the direct patient achieved MAP 121 rather than the nominal 110 and the direct route is known to differ from the modifier route.

The renal endpoint flow ratio of 1.2946 remains a candidate engine finding against the proposed established-disease target of 0.80--0.90. No P1 flow target has been applied. The next diagnostic is to isolate whether the increased renal flow is the direct route's hyperkinetic phenotype or a pressure-control/circuit compensation artifact.


## Follow-up audits

The P2 endpoint displacement ratio (3.33/5.81 = 0.57) is not interpreted as the configured 0.30 fraction: the implementation applies the fraction to instantaneous displacement and integrates fast/slow components while pressure is continuously changing. A fixed-pressure-clamp test remains required for quantitative coefficient validation.

The Stage 5 fractional-MAP analysis gives median time to a 30% fall of 462.5 s (normotensive), 412.5 s (resistance-dominant), 475.5 s (compliance-dominant), and 417.0 s (combined).

The modifier-route renal diagnostic shows left-kidney flow falling from 418.94 to 306.35 mL/min across its low-to-high pressure cells (ratio 0.73), unlike the direct-route 1.2946 increase. This supports a direct-route-specific hyperkinetic interpretation, but the cells are not exactly matched 120/80 and 150/90; a matched modifier run remains the final P1 check.


## Final follow-up gates

The direct-route renal result is now 1.30 for the closest 120/80-to-150/90 direct pair; the closest modifier cells give 0.61. The modifier route has no exact 150/90 grid cell, so the residuals are retained and this is not described as exact pressure matching.

The held-pressure P2 test did not reproduce upward resetting: MAP was held near 110--113 mmHg while the midpoint stayed near 95 mmHg through 300 s. P2 is therefore not closed.

The corrected established direct preset crossed a 30%-of-own-baseline MAP fall at 607.76 s, versus 417.0 s for the Stage 5 modifier combined phenotype. Mechanistic representation does not reproduce the modifier ordering in this comparison.


## P2 correction and within-route comparison

The upward reset failure was caused by Stage 7 state being reinitialized during a mechanics action. Pulse commit `e258eae8` preserves an active midpoint across reinitialization. The corrected held-step trace moved 95.00 -> 96.44 mmHg at 60 s, 98.33 at 120 s, and 102.40 at 300 s. The long fixture did not hold pressure through 20--30 minutes, so those checkpoints remain pending.

A same-body direct comparison at 150/90 crossed the 30%-fractional-MAP endpoint at 515.64 s with default mechanisms and 607.78 s with the established preset, a 92.14-second within-route effect. Multi-body replication remains pending.


## Parameter isolation

Same-body direct isolation gives 30%-fractional-MAP times of 515.64 s (default), 591.34 s (gain 0.40), 597.60 s (midpoint 110), and 524.40 s (chamber Ees 1.20). Intrinsic contractility 0.92 alone fails initial circuit tuning, while the combined preset reaches 607.78 s. The combined effect is therefore dominated by gain/midpoint and is not a simple sum of independently viable parameters.


Absolute MAP 65 crossings in the isolation traces were 549.24 s (default), 647.18 s (midpoint-only), and 557.42 s (chamber-only); gain-only and combined did not cross MAP 65 by 2,155 s. The endpoint ordering therefore does not reverse.

The repeated-action pressure-hold fixture entered cardiovascular collapse at 952.22 s, so it did not generate valid Moreira 20/30-minute checkpoints. P2 remains qualitatively demonstrated only through the early 60--300 s movement.


A gain-2.0 counter-test collapsed at 517--519 s, confirming that the gain field is applied directly to effector update increments rather than reciprocally or with a reversed sign. The gain-0.40 protection is therefore a dynamical interaction in the engine, not a simple coding-direction error. Together with isolated contractility failure and prior pressure-grid holes, this establishes a non-monotonic stabilisation manifold.


The gain trace audit confirms the P3 concern: at 300 s, gain 0.40 produced HR/resistance scales 1.435/1.238 versus 1.386/1.227 at gain 1.0, rather than a lower steady effector response. Since gain multiplies both the state decay and drive increments, it changes update rate. P3 is not currently a literature-calibrated reflex sensitivity parameter. Multi-body replication is suspended pending a redesign or explicit relabelling.


P3 was corrected in Pulse commit `a04eaa690`: gain now scales only the drive, not the state-decay term. P2's reset fraction was audited separately and already uses a target offset with unscaled first-order relaxation. Corrected short traces now show gain 2 > gain 1 > gain 0.40 in effector scale, but gain 2 fails at 74 s, gain 0.40 at 617 s, and gain 1 later; bounded calibration is required. All previous P3-based haemorrhage effects are invalidated.


Corrected P3 common-time audit at 60 s: gain 0.40 HR/resistance scales 0.839/0.895, gain 1.0 1.048/1.022, gain 2.0 1.614/1.628. No clamp is present on the normalized effector scales. Gain 2 is therefore an unbounded overdrive instability, not a validated physiological response. Replacement fractional-MAP times are 459.54 s (gain 0.40) and 427.14 s (combined), against 515.64 s default direct.


The corrected gain sweep found failures near 649 s (0.2), 617 s (0.4), 680 s (0.8), and 200 s (1.5); 0.6, 1.0 and 1.2 survived the 600-second recording window. Effector scales rose monotonically with gain at 60 s and no clamp exists. P2 trace audits separated fraction effects (0.10 -> midpoint 95.81/97.10 at 120/300 s; 0.80 -> 100.43/105.55) from time-constant effects (fast tau 60 -> 100.85/106.05; slow tau 3,000 -> 98.25/102.27).


Gain failures are now classified rather than ranked: 0.2/0.4 show hypovolemic-shock and intracranial-hypotension/exsanguination trajectories before negative volume; 1.5 fails early with tachycardia and negative volume without hypovolemic-shock logging, consistent with a distinct overdrive instability. The stock engine clamps final heart-driver frequency, but no clamp exists on normalized baroreceptor effector scales or their resistance path.


## Engine finding 6: open-loop renal fraction interaction

The renamed `RenalResistanceAdjustmentFraction` smoke test ran on a fresh StandardMale runtime. The parameter was accepted at 0.85 after the 30-second baseline advance; MAP and renal flow were recorded at 60-second intervals through the requested 600-second post-action window. The action triggers an internal stabilization pass, so the driver reports a known expected-end-time bookkeeping mismatch; the runtime trace and samples are retained under `results/stage7/p1_runtime_smoke/`. The pressure-grid result remains the finding: renal fraction rises with systemic pressure under the open-loop controller, so the parameter is not an invariant flow target. See `docs/ENGINE_FINDINGS.md` item 6.
