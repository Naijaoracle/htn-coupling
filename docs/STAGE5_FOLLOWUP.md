# Stage 5 follow-up: waveform diagnostics and expanded acute test

## Decision

The automated reflection-phase endpoint is withdrawn: visual inspection shows that it silently switches between different waveform features. The earlier physiological-recognisability failure is therefore **unassessable under that detector**, not confirmed. Normalised full-waveform RMSE remains the valid shape endpoint.

The expanded acute result is robust within the tested engine panel. Across 20 paired bodies (10 female, 10 male), high-resistance phenotypes reached a 30% fall from their own baseline MAP earlier than control in every body, while compliance-only reached it later in every body.

## Augmentation pressure, not only the index

The custom augmentation index was `100 × rebound pressure / pulse pressure`, so pulse-pressure widening magnified its decline. Recovering the numerator shows that the denominator was a confound but not the whole explanation.

| Phenotype | Site | Rebound pressure before → central stiffening (mmHg) | Pulse pressure before → after (mmHg) |
|---|---:|---:|---:|
| Normotensive | ECA | 4.59 → 1.69 | 28.48 → 51.65 |
| Normotensive | ICA | 8.15 → 4.34 | 39.20 → 58.32 |
| Compliance-only | ECA | 5.73 → 2.88 | 25.10 → 45.51 |
| Compliance-only | ICA | 8.42 → 6.55 | 34.65 → 51.44 |
| Combined | ECA | 0.95 → 6.44 | 16.95 → 32.34 |
| Combined | ICA | 9.79 → 9.78 | 24.61 → 37.76 |

The selected rebound pressure genuinely decreased in four of six comparisons, increased in combined ECA, and was essentially unchanged in combined ICA. This is the predeclared post-primary rebound, not the clinical `P2−P1` definition of augmentation pressure.

## Reflection-detector audit

Annotated overlays show feature substitution rather than physiological travel-time shifts:

- Uniform-stiffening ICA traces label late plateau notches at phase 0.46–0.52, while inlet-only traces label early systolic features at 0.28–0.32. The reported 0.17–0.20-cycle delay is invalid.
- Some uniform-stiffening ECA traces have no distinct secondary maximum.
- In combined ECA, the baseline detector labels a late hump near 0.54 and central stiffening labels an early shoulder near 0.28. The apparent advance compares different features.
- Where central stiffening visibly preserves the same ICA feature, movement is only about 0.00–0.01 cycle: no resolved timing change at the current phase resolution.

Eight of 12 cross-arm comparisons were classified invalid, ambiguous, or missing. Reflection phase must not be used for cross-arm inference without a feature-tracking method validated against the waveform itself.

## Expanded paired acute test

The predeclared panel used 20 anonymous engine-admissible HAALSI-derived bodies, 10 per sex, spanning within-sex BMI ranks at ages 40–65. Each body received all four phenotypes under the same fixed 200 mL/min haemorrhage. All 80 deterministic Pulse runs completed. The primary endpoint was time to a 30% fall from each run's own median baseline MAP during seconds 0–29.

| Phenotype | Median endpoint (s) | Paired median difference from control (s) | Bootstrap 95% interval (s) | Direction across bodies |
|---|---:|---:|---:|---:|
| Normotensive | 481.0 | — | — | — |
| Resistance-only | 416.0 | −57.0 | −62.5 to −42.5 | earlier 20/20 |
| Compliance-only | 487.5 | +7.0 | +7.0 to +8.0 | later 20/20 |
| Combined | 428.5 | −49.5 | −54.5 to −39.5 | earlier 20/20 |

Relative to the control median, resistance-only was 11.9% earlier, combined 10.3% earlier, and compliance-only 1.5% later. Two-sided paired Wilcoxon tests were `p=0.000002` for all three comparisons; Holm adjustment remained `0.000006`. These p-values describe numerical consistency in a deliberately selected deterministic engine panel, not population inference.

The direction held within both sex strata. Female paired medians were −55 s, +7 s, and −48 s for resistance-only, compliance-only, and combined; male medians were −61.5 s, +7.5 s, and −54.5 s.

## Interpretation

Within stock Pulse and this implementation, high systemic resistance reduces haemorrhage tolerance while isolated compliance reduction produces a small delay, even after using a fractional endpoint that removes the starting-pressure distance-to-threshold confound. Thus two haemodynamic mechanisms can move the acute outcome in opposite directions. This is a mechanism-sensitive engine result, not yet a clinical estimate: the bodies are selected rather than population-representative, the bleed is fixed in absolute mL/min, Pulse is deterministic, and compliance is represented by a lumped multiplier.

The optical result is now narrower but more honest: full waveform shape is numerically distinguishable above the inlet-noise floor, while the extrema-based reflection and augmentation interpretation has not been validated.
