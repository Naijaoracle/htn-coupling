# Stage 7 demonstrations (17 August 2026)

## P2 stateful resetting

Fixture: `Stage7P2ResetDemonstration.json`; 30-minute pressure perturbation after a 30-second baseline. The configured chronic midpoint began at 95.00 mmHg and was 91.67 mmHg at 1,800 s while MAP moved from 95.32 to 89.51 mmHg. The midpoint therefore followed the perturbation on the intended slow time scale; this demonstrates stateful behavior, not clinical validation of the animal-derived coefficients.

## P5 ventricular controls

A 120-second paired run compared the default patient with chamber end-systolic elastance multiplier 1.20 and intrinsic contractility multiplier 0.92. In the final 10 s, the default left-heart pressure-volume trajectory spanned 61.73--142.19 mL and 5.91--136.64 mmHg (stroke-volume range 80.46 mL); the configured trajectory spanned 55.73--140.83 mL and 5.84--137.46 mmHg (stroke-volume range 85.10 mL). The trajectory moved, demonstrating that the controls are wired. This is not a fitted or validated pressure-volume relation.

## All-parameter established preset

The direct 150/90 patient with gain 0.40, chronic midpoint 110 mmHg, rapid reset fractions 0.10/0.30, 120/1,500 s time constants, chamber elastance 1.20 and intrinsic contractility 0.92 completed the full 2,155 s haemorrhage scenario. It initialized at 148/90.7 mmHg (MAP 121.0) and remained above MAP 65 throughout; at 2,155 s it was 100/71.0 mmHg (MAP 86.3), HR 93.4/min and cardiac output 4.08 L/min. The stock Standard control crossed MAP 65 at 537.66 s and had MAP 71.6 mmHg at 2,155 s. These are not a matched-mechanism comparison: the direct patient achieved MAP 121 rather than the nominal 110, and the direct route is known to differ from the modifier route.

## P1 status

The renal endpoint flow ratio of 1.2946 (120/80 to 150/90), versus the proposed established-disease target of roughly 0.80--0.90, remains a candidate engine finding. No renal or hepatosplanchnic flow target has been applied. The next diagnostic is to isolate whether this is the direct route's hyperkinetic early phenotype or a pressure-control/circuit compensation artifact before implementing P1.
