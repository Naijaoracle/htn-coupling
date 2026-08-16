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

Gate failed at the aorta. Resistance scaling matched mean pressure within the
predeclared tolerance, but both arms underestimated Pulse pulse pressure by
about 20 mmHg. Carotid and sensitivity work is blocked pending an explicit
compliance/waveform-resolution experiment. See
[the Stage 4 report](STAGE4_PULSE_OPENBF_BRIDGE.md).

## Stage 5 — Hypertension through both models

Blocked by the Stage 4 aortic gate.

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
