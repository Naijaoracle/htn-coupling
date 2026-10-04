# Roadmap

> **Optical thread:** the stages deliberately excluded from the published
> manuscript (3, 4, 4b, 5 waveform work, 7b, 8) are documented individually in
> the stage reports linked below. A consolidated narrative of that thread is
> kept outside this repository.

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

Completed. Hypertension phenotypes were propagated through the coupled models
and evaluated for arterial waveform effects. See the
[Stage 5 report](STAGE5_HYPERTENSION_COUPLED_PIPELINE.md) and
[follow-up results](STAGE5_FOLLOWUP.md) for completed analyses and limitations.

## Stage 6 — Minimal Pulse fork

Completed. The fork parameterizes the patient-file baseline-pressure envelope
with unchanged defaults and provenance warnings. Pressure-only coverage rises
to 98.61% in HAALSI and 99.85% in ELSA, but the direct initialization grid has
two non-monotonic tuning failures and direct patients are not physiologically
equivalent to modifier-created patients at matched pressure. See
[the Stage 6 report](STAGE6_BOUNDS_PARAMETERISATION.md).

## Stage 7 — Autonomic control

Further model investigation is documented in the
[Stage 7 status report](STAGE7_IMPLEMENTATION_STATUS.md). No individual
physiological inference or clinical validation is claimed.

## Stage 8 — Optical observation boundary

A validated link from arterial haemodynamics to facial optical measurement
remains unavailable. See the [Stage 3 report](STAGE3_OPTICAL_SITE_REACHABILITY.md)
for the established anatomical boundary.
