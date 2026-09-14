# Pulse engine findings

This is the numbered record of engine-level limitations established by the
coupling programme. These are observations of the tested build/configuration,
not claims that every Pulse use case fails in the same way.

Numbering and categorisation follow the manuscript "Characterising and
extending the Pulse Physiology Engine for hypertensive older adults"
(`htn-coupling/paper/htn_paper.tex`), which is the canonical record. The
original repository record listed nine findings; the Aorta-InFlow morphology
limitation (formerly finding 5) was reclassified as a supplementary scope
observation because Pulse does not claim that compartment is a validated
physiological waveform. Former findings 6--9 are renumbered 5--8 accordingly,
and finding 1 was renamed to reflect that the observed behaviour is explicit
rejection, not clamping.

Statuses use the manuscript's table: addressed (defect corrected or bound
removed, in the fork); partially addressed (underlying limitation remains);
finding only; addressed but retained as a finding.

1. **Baseline pressure admissibility constraint.** Stock patient creation
   rejects many measured adult pressures outside its declared baseline
   envelope; direct hypertensive initialization is therefore coverage-limited.
   The rejection is explicit, not clamping.
   Status: addressed.

2. **Population-envelope exclusions.** Age, BMI, height/weight, pulse-pressure,
   and related patient-definition bounds exclude additional real-cohort adults;
   relaxing one bound does not make the whole population representable.
   Status: partially addressed.

3. **No native disease history or progression state.** Hypertension stage and
   duration are not represented as patient history in the stock operating-point
   definition.
   Status: partially addressed.

4. **Default baroreflex accommodation.** Stock restabilization returns the
   baroreflex scales to approximately unity, implicitly treating the new
   pressure as the normal setpoint unless stateful parameters are supplied.
   Status: partially addressed.

5. **Pressure-dependent renal fraction under open-loop adjustment.** The
   baseline-relative `RenalResistanceAdjustmentFraction` moves renal flow in the
   intended local direction at fixed systemic resistance, but it does not hold
   renal flow fraction invariant across the pressure domain. In the pressure
   grid, renal fraction rose from approximately 0.139 at MAP 93.4 mmHg to
   0.170 at MAP 114.8 mmHg. This is an open-loop controller interaction with
   systemic/baroreflex feedback, not a coding-sign failure; the parameter is
   documented as a resistance adjustment rather than a flow target.
   Status: finding only.

   Evidence for finding 5 is recorded in
   `results/stage7/p1_target_sweep_final/summary.json`,
   `results/stage7/p1_pressure_grid/summary.json`, and the runtime smoke under
   `results/stage7/p1_runtime_smoke/`.

6. **Route-dependent hypertensive haemodynamics.** At closely matched
   hypertensive pressures, direct patient creation and modifier-route creation
   produce opposite renal responses: approximately 1.30x renal flow for the
   direct route versus 0.61x for the modifier route. The modifier route agrees
   with the established-hypertension literature; direct creation produces the
   hyperkinetic early phenotype instead. The two routes are therefore not
   interchangeable representations of the same hypertensive patient.
   Status: finding only.

7. **Non-monotonic stabilisation manifold.** The engine's convergence domain has
   holes that are not monotonic in pressure or parameter magnitude: an isolated
   contractility multiplier of 0.92 fails at 150/90 while the combined preset
   succeeds; gain 2.0 produces overdrive collapse; and pressure-grid cases at
   160/90 and 170/100 fail while 180/110 converges. Calibration and preset
   searches must treat non-convergence as an observed feature of the tested
   state space, irrespective of whether its underlying cause is numerical or
   physiological.
   Status: finding only.

8. **Physiological parameter with numerical-rate semantics (P3).** Before the
   drive-only correction, the baroreflex-gain field multiplied both drive and
   decay increments. Trace audit showed that it changed adaptation rate rather
   than steady-state reflex sensitivity, producing a plausible but misdirected
   haemorrhage effect. The implementation is corrected, but the defect remains
   an engine-development finding: parameter names and literature-derived values
   cannot be treated as physiological semantics without trajectory and
   counter-test validation.
   Status: addressed; retained as a finding.

## Supplementary scope observation (reclassified from former finding 5)

**Aorta-InFlow morphology limitation.** Pulse's lumped Aorta-InFlow lacks the
brief post-ejection reverse-flow feature and lower-volume/longer-ejection
morphology seen in the distributed reference inlet, producing depressed coupled
aortic pulsatility. Pulse does not claim that this compartment-flow trace is a
validated physiological aortic waveform, so this is a scope observation rather
than a validation failure; it is recorded because any application that treats
Pulse outflow as a physiological arterial waveform inherits it.
