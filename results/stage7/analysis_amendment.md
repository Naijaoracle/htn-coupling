# Stage 7 follow-up amendment (17 August 2026)

## P2 audit

The observed midpoint displacement (3.33 mmHg) divided by the total MAP displacement (5.81 mmHg) is 0.57, but that ratio is not the configured downward-reset fraction. The implementation applies the fraction to the instantaneous displacement at each timestep and integrates fast and slow components; MAP is continuously changing, so an endpoint ratio against the total MAP excursion is not expected to equal 0.30. A fixed-step pressure-clamp test is still required before treating the coefficient as quantitatively validated.

## P5 correction

The original implementation multiplied both fields into the same Emax scalar. That was not a separation of chamber elastance and intrinsic contractility. Commit `a24cd1b51` corrects this: chamber Ees scales Emax, while intrinsic contractility scales the active excursion `(Emax-Emin)`. Isolated reruns now separate: chamber-only (1.20) gives volume range 52.11--138.13 mL and maximum pressure 138.89 mmHg; intrinsic-only (0.92) gives 65.72--147.25 mL and maximum pressure 133.99 mmHg; combined gives 55.73--140.83 mL and 137.46 mmHg. The previous combined result must not be used as a P5 demonstration.

## Fractional haemorrhage comparison

Existing Stage 5 body-spread analysis gives median time to a 30% MAP fall of 462.5 s for normotensive, 412.5 s for resistance-dominant, 475.5 s for compliance-dominant, and 417.0 s for combined. This removes the absolute-baseline confound; it does not validate the direct Stage 7 preset, which is a separate direct-creation route.

## Modifier-route renal diagnostic

The modifier-route comparison was rerun at the existing Stage 2 cells. Across the low-to-high pressure modifier cells, left-kidney inflow was 418.94, 346.81 and 306.35 mL/min while MAP was 97.36, 102.58 and 107.25 mmHg. Relative to the lowest cell, kidney inflow fell to 0.83 and 0.73. In contrast, the direct-route 120/80-to-150/90 diagnostic gave a 1.2946 kidney-flow ratio. This supports assigning the increase to the direct creation route rather than treating it as a universal circuit compensation, but the comparison is not an exactly matched 120/80 versus 150/90 pair and should be followed by a matched modifier run before P1 implementation.
