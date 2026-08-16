# Stage 5 waveform diagnostic

## Augmentation pressure

The original rebound index conflates its numerator with a pulse-pressure
denominator that widens under stiffening. The numerator was therefore recovered
and reported directly in `augmentation_pressure_diagnosis.csv`.

- Normotensive ECA central stiffening: rebound pressure 4.59 to 1.69 mmHg;
  pulse pressure 28.48 to 51.65 mmHg.
- Compliance-only ECA: 5.73 to 2.88 mmHg; PP 25.10 to 45.51 mmHg.
- Compliance-only ICA: 8.42 to 6.55 mmHg; PP 34.65 to 51.44 mmHg.
- Combined ECA: 0.95 to 6.44 mmHg; PP 16.95 to 32.34 mmHg.
- Combined ICA: 9.79 to 9.78 mmHg; PP 24.61 to 37.76 mmHg.

The ratio amplified the apparent declines, but did not create them: selected
rebound pressure itself fell in most cases. The combined ECA increase is the
clear exception, while combined ICA is unchanged.

This quantity remains the predeclared post-primary rebound, not clinical
augmentation pressure `P2-P1`.

## Reflection detector inspection

The annotated overlay uses filled upward triangles for the global primary peak,
filled downward triangles for the first post-primary trough, and open circles
for the subsequent maximum labelled as reflection.

Visual inspection shows silent feature substitution. Uniform-stiffening ICA
traces label late notches around phase 0.46–0.52, whereas the inlet-only traces
label early systolic features around 0.28–0.32. Their reported 0.17–0.20-cycle
delay is therefore invalid. Uniform ECA traces sometimes collapse to a single
detected maximum. In combined ECA, the baseline selector labels a late hump near
0.54 while central stiffening labels an early shoulder near 0.28; the apparent
advance is also invalid.

Where the same feature is visually preserved under central stiffening, ICA
phase movement is only about 0.00–0.01 cycle. That is effectively no resolved
timing change at the current 501-point phase representation.

Consequently, the existing reflection phase is withdrawn as a cross-arm wave-
arrival metric. The full normalised waveform remains a valid numerical shape
metric; the extrema label does not.
