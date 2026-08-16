# Roadmap

## Stage 0 — Independent controls

- Run stock Pulse and reproduce a published validation scenario.
- Run openBF's unmodified adan56 example to convergence.
- Record the pressure output and immutable repository revisions.

## Stage 1 — Pulse baseline clamp

Compare Wave 1 HAALSI pressures against Pulse's admissible patient-baseline
envelope. Count and characterize people who cannot be instantiated. This uses
stock Pulse and remains distinct from the HAALSI longitudinal study outputs.

## Stage 2 — Tier 0 Pulse phenotype

Calibrate systemic resistance and arterial compliance multipliers to target
pressures using the stock engine. Tabulate the mapping and calibration error.

## Stage 3 — Facial territory gate

Completed: neither shipped network reaches a physical facial-rPPG site. Use
separate distal external- and internal-carotid outputs as upstream references,
with an explicit unmodelled cutaneous transfer. The stock Circle-of-Willis
example is anatomically closer to the ophthalmic route but fails the
normotensive resting-pressure gate. See
[the Stage 3 report](STAGE3_OPTICAL_SITE_REACHABILITY.md).

## Stage 4 — One-way bridge

Completed. Stage 4b attributed the original pulse-pressure gate failure to the
genuine Pulse inlet and replaced that gate with mean agreement plus
physiological plausibility. Distal ECA and ICA morphology passes the bounded
shape screen, and a 2x wall-stiffness perturbation exceeds the tested +/-5%
inlet-noise floor at both sites. See [the original gate report](STAGE4_PULSE_OPENBF_BRIDGE.md),
[the diagnosis](STAGE4B_PULSE_PRESSURE_DIAGNOSIS.md), and
[the completion report](STAGE4_COMPLETION.md).

## Stage 5 — Hypertension through both models

Ready. First repeat the 2x-E response from an approximately 31 mmHg
age-45-matched aortic-PP baseline and compare it with the depressed 20.45 mmHg
coupled baseline; do not assume response scaling.

Apply the Tier 0 phenotype, propagate it through the bridge, and map stiffness
and peripheral resistance to openBF E and R2. Check pulse-pressure widening and
augmentation direction against the Charlton virtual-ageing reference.

## Stage 6 — Minimal Pulse fork

Only after the clamp is quantified, parameterize the admissible envelope in the
Pulse fork with a minimal upstream-offerable diff.

## Stage 7 — Baroreflex

If physiology review supports it, expose setpoint and gain with a partial
accommodation mode.

## Stage 8 — Optical link

Perturb stiffness through the coupled pipeline and quantify waveform changes at
the Stage 3 facial or nearest-usable site.
