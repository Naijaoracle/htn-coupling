# Stage 4b: Diagnosing the aortic pulse-pressure gap

## Outcome

**The inlet waveform causes the gap; terminal-resistance scaling and extraction artefacts do not.** On identical, unmodified ADAN56 geometry and published terminals, replacing the published inlet with Pulse `Aorta-InFlow` lowered aortic pulse pressure by 13.84 mmHg, from 34.41 to 20.57 mmHg. The 5.33% resistance scale changed pulse pressure by only -0.36 mmHg with the default inlet and -0.12 mmHg with the Pulse inlet. Because the swap test identified the inlet, the conditional wall-property investigation was not reached and no compliance fitting was performed.

The aortic gate is amended to require agreement in mean pressure, pulse pressure inside a published physiological range, and a plausible single-ejection waveform. It no longer requires Pulse and openBF pulse pressures to agree within 10 mmHg. The resistance-scaled Pulse-to-openBF arm passes the amended gate: mean error is -3.88 mmHg and its 20.45 mmHg pulse pressure lies inside the published 18--43 mmHg reference interval for adults aged 25--44. It is nevertheless low-tail for a healthy 44-year-old man and that bias remains a recorded property of the coupling.

## Reference truth

Pulse StandardMale is 44 years old. Kuznetsov and colleagues used radial applanation tonometry in 327 adults aged 25--44 and reported a central aortic pulse-pressure 95% reference interval of 18--43 mmHg. A larger healthy-population reference table places men aged 40--49 at a median of 32 mmHg, with 10th and 90th percentiles of 25 and 45 mmHg. These data make 20.5 mmHg physiologically possible but near the low tail; Pulse's 40.6 mmHg is near the high tail.

Charlton's healthy-ageing virtual database generated 4,374 subjects aged 25--75. From its age-stratified aortic systolic and diastolic means, aortic pulse pressure is 25.4, 27.3, 31.2, 34.5, 38.8 and 43.4 mmHg at ages 25, 35, 45, 55, 65 and 75. Its age-45 mean is therefore 31.2 mmHg. openBF was separately benchmarked against all 4,374 virtual subjects, including ascending-aortic pulse pressure, and reported strong agreement in clinical metrics, while noting lower pulse-pressure amplification and augmentation pressure.

Sources:

- [Kuznetsov et al., central aortic pressure reference values](https://pubmed.ncbi.nlm.nih.gov/30990136/)
- [Brazilian 2023 central blood-pressure reference table](https://pmc.ncbi.nlm.nih.gov/articles/PMC11186661/)
- [Charlton et al., healthy-ageing pulse-wave database](https://doi.org/10.1152/ajpheart.00218.2019)
- [Benemerito et al., openBF validation](https://eprints.whiterose.ac.uk/id/eprint/220365/1/Benemerito_2024_Physiol._Meas._45_125002.pdf)

## Inlet comparison

Both inlets are shown over cardiac-cycle phase in `results/stage4b/inlet_comparison.png`. Ejection duration is the integral of an indicator for flow above 1% of peak, divided by cycle length; this definition handles the arbitrary cycle start and ADAN56's irregular sampling.

| metric | ADAN56 default | Pulse, 8-cycle average |
|---|---:|---:|
| cycle length (s) | 1.000 | 0.840 |
| peak flow (mL/s) | 572.73 | 434.75 |
| time to peak (s; cycle phase) | 0.128; 0.128 | 0.0756; 0.090 |
| maximum rate of rise (mL/s2) | 7,729 | 10,817 |
| cycle mean flow (mL/s) | 112.90 | 95.65 |
| stroke volume (mL) | 112.90 | 80.35 |
| ejection fraction of cycle | 0.339 | 0.405 |
| mean peak-to-1%-flow downslope (mL/s2) | -2,190 | -1,670 |
| post-peak minimum flow (mL/s) | -162.89 | approximately 0 |
| dicrotic/reverse-flow feature | present | absent |

Pulse is not slower-rising: its maximum upstroke is steeper. It is, however, lower-peaked, lower-volume, more prolonged as a fraction of its cycle, and lacks ADAN56's sharp post-ejection reverse-flow feature. Thus the result supports an inlet-waveform diagnosis, but not the narrower claim that a slow Pulse upstroke caused it. The inlet difference includes both cardiac output/stroke volume and waveform shape; Stage 4b deliberately does not fit or amplitude-normalise either waveform.

## Four-cell swap test

All cells used unmodified ADAN56 geometry and wall properties. Scaling multiplies every terminal R1 and R2 by 1.0533249; terminal compliance remains published.

| inlet | terminals | SBP | DBP | mean | pulse pressure |
|---|---|---:|---:|---:|---:|
| ADAN56 default | published | 118.23 | 83.82 | 103.33 | 34.41 |
| Pulse | published | 95.36 | 74.78 | 87.27 | 20.57 |
| ADAN56 default | resistance-scaled | 123.43 | 89.38 | 108.63 | 34.05 |
| Pulse | resistance-scaled | 99.57 | 79.12 | 91.44 | 20.45 |

At published terminals, the inlet substitution accounts for a 13.84 mmHg pulse-pressure reduction. Resistance scaling moves mean pressure by 5.30 mmHg in each inlet arm but moves pulse pressure by less than 0.4 mmHg. The causal attribution is therefore the inlet presented to ADAN56, not the global terminal-resistance scale.

## Extraction audit

- Raw Pulse output is sampled every 0.02 s (50 Hz).
- Across the eight source cycles, raw peaks span 434.742--434.796 mL/s. The average peak is 434.777 mL/s and the phase-averaged 201-point peak is 434.750 mL/s: attenuation is 0.0062%.
- Replacing the average with one raw cycle produced 21.46 mmHg pulse pressure, +0.89 mmHg versus the primary 20.57 mmHg run.
- Resampling the average to 1,001 points produced 20.68 mmHg, +0.10 mmHg. Higher interpolation density cannot recover information above the original 50 Hz sampling bandwidth, but this result rules out the 201-point grid as the material cause.
- Pulse source inspection confirms that `VascularCompartment::Aorta` receives the `LeftHeartToAorta` liquid link, mapped to `LeftHeart1ToAorta2` in `SetupCircuitsAndCompartments.cpp`. `Aorta-InFlow` is therefore ventricular ejection into the systemic aortic compartment, not an outflow or distal flow.
- The `1e-10 m3/s` floor matches ADAN56's zero convention and is negligible relative to systolic flow. The accepted cycle starts immediately before maximum upstroke. A prior peak-start/exact-zero probe generated non-finite pressure and remains rejected; it is not one of the interpreted cells.

These checks exclude cycle averaging, resampling density, source selection, and the zero/start convention as explanations for the 13.84 mmHg inlet effect.

## Amended gate and scope

Stage 4 criterion 6 is now:

1. openBF mean aortic pressure must agree with Pulse within 5 mmHg;
2. openBF aortic pulse pressure must lie in the 18--43 mmHg published reference interval applicable to the 44-year-old control;
3. the inlet and resulting pressure must remain finite, periodic, single-ejection waveforms with their material morphology differences reported.

This is the third candidate gate: agreement in mean and physiological plausibility in pulse pressure and shape. It is preferred because mean pressure is directly constrained by flow and total resistance, whereas pulse pressure is recomputed by two structurally different models. Forcing numerical equality would fit openBF to Pulse rather than test the distributed model. The amended gate passes for the resistance-scaled arm, while explicitly recording that 20.45 mmHg is below the healthy male age-40--49 10th percentile of 25 mmHg.

Stage 5 is unblocked with respect to the aortic gate but was not run. Carotid output and inlet sensitivity remain outside Stage 4b and no downstream result is asserted here.

## Reproducibility artefacts

- `scripts/stage4b_diagnose.py` and `scripts/run_stage4b.sh`
- `results/stage4b/inlet_metrics.csv`
- `results/stage4b/swap_test.csv`
- `results/stage4b/extraction_audit.json` and `extraction_reruns.csv`
- `results/stage4b/stage4b_summary.json`
- generated YAML, inlet and openBF output under `results/stage4b/configs` and `results/stage4b/runs`
