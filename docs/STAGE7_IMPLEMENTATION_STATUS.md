# Stage 7 implementation status (17 August 2026)

## Completed gates

- Stage 7.1 regional-flow diagnostic: direct 120/80 versus 150/90 completed. The endpoint flows increased in all logged beds (brain 1.0595, kidneys 1.2946, gut 1.0599, liver 1.0576, muscle 1.0584, skin 1.0584, myocardium 1.0600). This is compensated/mixed behavior, not the predicted blanket hypoperfusion; renal and hepatosplanchnic P1 flow targets remain deferred.
- P4 named haemodynamic-stage metadata is implemented in Pulse commit `7ad43da5b`. `Unspecified` preserves upstream behavior; named early/borderline, established, and long-standing values are provenance labels only at this step.
- P3 baroreflex gain is implemented in Pulse commit `877586fce`. It is a dimensionless multiplier on all four reflex effector responses; absent or `1.0` preserves upstream behavior. Values outside the established-hypertension range [0.40, 0.80] warn during setup.

## Regression

The focused SetupPatient test passed, including the named-stage metadata case. The full Stage 0 haemorrhage control completed to 2,155 s in 224.262 s. Its output was 46,098,446 bytes with SHA-256 `462c43248785ce45771b056b53443252414ec066ae50bee0d3b276a42fcfab0a`, identical to the archived control.

The complete distributed verification suite remains unavailable in this checkout because its verification directory and baseline corpus are absent.

- P2 stateful resetting is implemented in Pulse commit `b3e033710`: chronic midpoint, directional rapid-reset fractions, and fast/slow time constants are optional patient fields; omission retains upstream accommodation. A configured two-minute patient smoke test stabilized successfully.
- P5 ventricular controls are implemented in Pulse commit `7705c6fe7`: optional chamber end-systolic elastance and intrinsic contractility multipliers are applied to left-ventricular maximum elastance. A configured two-minute smoke test stabilized successfully. Diastolic beta and relaxation-time parameters remain architecture-dependent and are not guessed.

## P1 decision

The 7.1 diagnostic showed compensated/mixed flow behavior rather than blanket hypoperfusion: direct 120/80 to 150/90 endpoint flow ratios were brain 1.0595, kidneys 1.2946, gut 1.0599, liver 1.0576, muscle 1.0584, skin 1.0584, and myocardium 1.0600. Therefore the proposed renal/hepatosplanchnic flow targets are not applied. P1 remains a documented deferred decision until the circuit compensation mechanism is isolated.

## Final regression

After P5, the full Stage 0 haemorrhage control again completed to 2,155 s in 248.463 s. Output size was 46,098,446 bytes and SHA-256 remained `462c43248785ce45771b056b53443252414ec066ae50bee0d3b276a42fcfab0a`.

The complete distributed verification suite remains unavailable in this checkout because its verification directory and baseline corpus are absent.
