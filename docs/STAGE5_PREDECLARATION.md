# Stage 5 predeclaration: hypertension through the coupled pipeline

This document was fixed before any Stage 5 openBF simulation was run. Stage 5
uses stock Pulse and the pinned, unmodified openBF dependency.

## Phenotypes

All four phenotypes begin from the same admissible `StandardMale` Pulse state.

| Phenotype | Systemic resistance multiplier | Arterial compliance multiplier |
|---|---:|---:|
| Normotensive | 1.0 | 1.0 |
| Resistance-dominant | 2.0 | 1.0 |
| Compliance-dominant | 1.0 | 0.4 |
| Combined | 2.0 | 0.4 |

The combined point was selected from the completed extended Stage 2 sweep: it
achieved approximately 152/88 mmHg, close to the requested 150/90 target. The
two mechanism-isolation points deliberately change one released modifier only.
Mean-pressure matching will be assessed, but it is not forced: a compliance-only
modifier mainly redistributes systolic and diastolic pressure and cannot reach
the high mean pressure produced by a doubled resistance without ceasing to be a
one-mechanism phenotype. Any mismatch is retained and reported.

## Pulse-to-openBF mapping

Each Pulse phenotype supplies its own stable, cycle-averaged `Aorta-InFlow`,
cardiac period, and achieved systemic vascular resistance. All openBF WK3 `R1`
and `R2` values are multiplied by one global factor that makes their parallel
equivalent equal to that phenotype's Pulse systemic resistance. Published WK3
`Cc` is unchanged in the primary arms.

- **Arm 1 — inlet only:** published vessel Young's moduli are unchanged.
- **Arm 2 — matched stiffening:** every vessel Young's modulus is multiplied by
  `1 / Pulse arterial-compliance multiplier`. Thus a Pulse compliance multiplier
  of 0.4 maps to an openBF modulus multiplier of 2.5.

The Arm 2 rule follows the thin-wall first-order relation `C proportional to
1/E` only as a transparent perturbation mapping. A global conduit-wall modulus
scale is not equivalent to Pulse's lumped arterial compliance, and no fitted
equivalence is claimed. A targeted terminal-only diagnostic scales WK3 `Cc` to
0.4 while leaving the tree unchanged; it is diagnostic, not a third calibrated
phenotype arm.

## Metrics and attribution

Metrics are evaluated at the aortic root, distal right external carotid, and
distal right internal carotid. Pressure metrics are systolic, diastolic, cycle
mean, and pulse pressure. Shape metrics are peak phase, reflected-wave phase,
augmentation index, and phase-aligned normalised waveform RMSE.

The reflected wave is the first local pressure maximum after the primary peak
and an intervening local minimum. Augmentation pressure is that secondary peak
minus the intervening minimum; augmentation index is 100 times augmentation
pressure divided by pulse pressure. This explicit rebound definition is not
presented as the clinical `P2-P1` definition. Missing identifiable extrema are
reported as missing, not manufactured.

For every metric, the noise floor is the largest absolute change caused by the
four Stage 4.6 inlet perturbations (flow +/-5%, period +/-5%). A phenotype effect
passes attribution only when its magnitude is at least **1.25 times** its
metric-specific noise floor. Amplitude and shape results are reported
separately. For waveform shape, the primary statistic is phase-aligned RMSE
after min-max normalisation. A modulus sweep of 1.10, 1.25, 1.50, 1.75, 2.00,
and 2.50 will identify the smallest tested stiffness change clearing that shape
floor at each carotid site.

## Low-pulsatility and ICA diagnostics

The compliance-dominant response is measured from both the Pulse-driven,
low-pulsatility baseline and ADAN56's published default inlet. This tests
attenuation; the default inlet is a sensitivity reference, not a Pulse patient.

The distal ICA/ECA difference is not interpreted anatomically until the outlet
structure is inspected and the terminal-only diagnostic is compared with the
distributed-stiffness response. Both sites terminate directly in WK3 loads in
ADAN56, standing in for vascular beds that the model does not contain.

## Acute panel

The four Pulse phenotypes are run through the fixed Stage 0 haemorrhage protocol
on several admissible male and female bodies. Time to MAP below 65 mmHg, time to
the first irreversible-state event, and minimum cardiac output are reported as
distributions. These are Pulse-side results and do not use openBF.
