# Stage 7 implementation status (17 August 2026)

## Completed gates

- Stage 7.1 regional-flow diagnostic: direct 120/80 versus 150/90 completed. The endpoint flows increased in all logged beds (brain 1.0595, kidneys 1.2946, gut 1.0599, liver 1.0576, muscle 1.0584, skin 1.0584, myocardium 1.0600). This is compensated/mixed behavior, not the predicted blanket hypoperfusion; renal and hepatosplanchnic P1 flow targets remain deferred.
- P4 named haemodynamic-stage metadata is implemented in Pulse commit `7ad43da5b`. `Unspecified` preserves upstream behavior; named early/borderline, established, and long-standing values are provenance labels only at this step.
- P3 baroreflex gain is implemented in Pulse commit `877586fce`. It is a dimensionless multiplier on all four reflex effector responses; absent or `1.0` preserves upstream behavior. Values outside the established-hypertension range [0.40, 0.80] warn during setup.

## Regression

The focused SetupPatient test passed, including the named-stage metadata case. The full Stage 0 haemorrhage control completed to 2,155 s in 224.262 s. Its output was 46,098,446 bytes with SHA-256 `462c43248785ce45771b056b53443252414ec066ae50bee0d3b276a42fcfab0a`, identical to the archived control.

The complete distributed verification suite remains unavailable in this checkout because its verification directory and baseline corpus are absent.

- P2 stateful resetting is implemented in Pulse commits `b3e033710` and `15fecf445` (the latter exposes the midpoint as a data request): chronic midpoint, directional rapid-reset fractions, and fast/slow time constants are optional patient fields; omission retains upstream accommodation. A configured two-minute patient smoke test stabilized successfully. A 1,830-second pressure-perturbation demonstration then moved the logged chronic midpoint from 95.00 mmHg to 91.67 mmHg while MAP moved from 95.32 to 89.51 mmHg, showing the intended stateful slow component.
- P5 ventricular controls are implemented in Pulse commit `7705c6fe7`: optional chamber end-systolic elastance and intrinsic contractility multipliers are applied to left-ventricular maximum elastance. A configured two-minute smoke test stabilized successfully. A paired 120-second pressure-volume demonstration with chamber elastance 1.20 and intrinsic contractility 0.92 changed the final-cycle volume range from 80.46 to 85.10 mL and the maximum pressure from 136.64 to 137.46 mmHg. This demonstrates wiring, not validation of a clinical PV relation. Diastolic beta and relaxation-time parameters remain architecture-dependent and are not guessed.

## P1 decision

The 7.1 diagnostic showed compensated/mixed flow behavior rather than blanket hypoperfusion: direct 120/80 to 150/90 endpoint flow ratios were brain 1.0595, kidneys 1.2946, gut 1.0599, liver 1.0576, muscle 1.0584, skin 1.0584, and myocardium 1.0600. Therefore the proposed renal/hepatosplanchnic flow targets are not applied. P1 remains a documented deferred decision until the circuit compensation mechanism is isolated.

## Final regression

After P5, the full Stage 0 haemorrhage control again completed to 2,155 s in 254.246 s. Output size was 46,098,446 bytes and SHA-256 remained `462c43248785ce45771b056b53443252414ec066ae50bee0d3b276a42fcfab0a`.

The complete distributed verification suite remains unavailable in this checkout because its verification directory and baseline corpus are absent.

## Combined established preset demonstration

The direct 150/90 patient with baroreflex gain 0.40, chronic midpoint 110 mmHg, reset fractions 0.10/0.30, 120/1,500 s time constants, chamber elastance 1.20 and intrinsic contractility 0.92 completed the full 2,155 s haemorrhage scenario. It initialized at 148/90.7 mmHg (MAP 121.0) and remained above MAP 65; at 2,155 s it was 100/71.0 mmHg (MAP 86.3), HR 93.4/min and cardiac output 4.08 L/min. The Standard control crossed MAP 65 at 537.66 s and ended at MAP 71.6 mmHg. This is a mechanism demonstration, not a matched comparison: the direct patient achieved MAP 121 rather than the nominal 110 and the direct route is known to differ from the modifier route.

The renal endpoint flow ratio of 1.2946 remains a candidate engine finding against the proposed established-disease target of 0.80--0.90. No P1 flow target has been applied. The next diagnostic is to isolate whether the increased renal flow is the direct route's hyperkinetic phenotype or a pressure-control/circuit compensation artifact.
