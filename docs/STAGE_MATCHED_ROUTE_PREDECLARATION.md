> **Amendment 1 applies.** The compatible Pulse revision and Stage 0 repeatability gate are specified in [docs/STAGE_MATCHED_ROUTE_AMENDMENT_1.md](STAGE_MATCHED_ROUTE_AMENDMENT_1.md). All other predeclared analysis choices remain in force.

# Stage pressure-matched mechanism comparison: predeclaration

## Question and scope

This model-characterisation experiment asks whether direct patient
initialisation and cardiovascular-modifier calibration can reach essentially
identical systolic and diastolic arterial pressure while retaining different
internal Pulse haemodynamics. It is not a clinical validation of either route
or a fit to individual cohort participants.

For every target, the primary comparison is a direct Pulse state and a
modifier-created state. The modifier state is calibrated to the direct state's
*achieved*, rather than requested, SBP and DBP. Only accepted primary pairs are
eligible for the secondary Pulse-to-openBF comparison.

## Fixed targets, body, and model boundaries

The reference body is StandardMale. The direct targets are 130/80, 140/90,
and 150/90 mmHg. The direct construction, measurement procedure, and validity
rules are those used by Stage 6. The final-state measurement window is 12 s at
0.02 s resolution; every accepted state is independently rerun using the same
window. Stage 0 must pass before any result is admitted.

Before running, record the Pulse upstream and fork revisions, htn-coupling
revision, openBF revision, Julia and Python versions, operating system, Pulse
build configuration, Stage 0 SHA-256, and local path configuration. No change
to the model implementation after this document is fixed is permitted without
an amendment.

## Pressure match

For direct target \(k\), let \(P_k^*=(SBP_{direct}, DBP_{direct})\) be the
achieved stable pressure. Search modifier controls \(R\) (systemic resistance)
and \(C\) (arterial compliance) inside the primary physiological domain:

\[
1.0 \le R \le 2.0, \qquad 0.4 \le C \le 1.0.
\]

The objective is

\[
J(R,C)=((SBP_{modifier}-SBP_k^*)/1\ \mathrm{mmHg})^2+
((DBP_{modifier}-DBP_k^*)/1\ \mathrm{mmHg})^2.
\]

A pair is accepted only when both absolute residuals are below 0.25 mmHg and
the independent rerun also meets both limits. MAP is reported but is not a
third fitting constraint. A target outside the declared modifier domain is
reported as unmatched; the domain is not widened in the primary analysis.

## Search and failure handling

First evaluate the complete \(R=1.00,1.10,\ldots,2.00\),
\(C=1.00,0.90,\ldots,0.40\) grid. Retain every successful and failed
evaluation with its log-derived failure category. Refine successful low-J
regions at 0.02, 0.005, and, where useful, 0.001 steps. A bounded solver may
be used only inside a regular successful region; failed evaluations receive a
prohibitive objective and are never interpolated as successes.

All accepted solutions are reported. For a one-solution-per-target primary
display, select the accepted solution nearest \((R,C)=(1,1)\); break an exact
distance tie by lower \(J\), then lower \(R\), then higher \(C\). This rule is
solely presentational and does not discard the remaining roots.

A target is not matched if direct initialisation fails, no modifier state
passes both tolerances, a solution is not reproducible, or a required output
is invalid. Direct-state failure, modifier-domain reachability failure,
numerical search failure, and reproducibility failure are reported separately.

## Outcomes and interpretation

Report pressure (SBP, DBP, MAP, pulse pressure), pump function (heart rate,
cardiac output, stroke volume where available), systemic vascular resistance,
brain and bilateral renal flows, baroreflex scales, relevant tissue
resistances, aortic inflow morphology, and cardiac period. Report direct minus
modifier differences, relative differences where meaningful, and ratios for
flows. The deterministic single-body comparison uses no population-inference
p-value. No universal practical-effect threshold is imposed: results are
reported as variable-specific effect estimates and their consistency across
the predeclared targets.

Matched pressure with reproducible internal separation supports the limited
claim that, within this Pulse configuration, SBP and DBP do not uniquely
identify the simulated haemodynamic state. Collapsed separation, failures, and
unmatched cases remain reportable results.

## Secondary coupled analysis

For each accepted pair, use each state’s own cycle-averaged `Aorta-InFlow`,
period, and achieved SVR. Keep published vessel Young’s moduli and WK3
compliance unchanged. Scale WK3 R1/R2 by the existing global factor that maps
parallel terminal resistance to that state's Pulse SVR. This is the
published-wall, inlet-plus-SVR bridge; it tests the full-state effect, not an
inlet-only effect.

Evaluate the aortic reference, right ECA, and right ICA. Report systolic,
diastolic, mean and pulse pressure, peak phase, phase-aligned normalised RMSE,
and optimal phase shift. The withdrawn reflected-wave endpoint is not reused.
The established 1.25-times metric-specific Stage 4.6 perturbation threshold
is retained as an attribution threshold, not labelled as solver noise. Final
cases also receive repeat-run checks for numerical reproducibility.

After the primary coupled result is fixed, a four-case sensitivity may cross
direct/modifier inlet with direct/modifier WK3 resistance scale. It identifies
whether a state-level waveform difference is primarily associated with inlet,
terminal scale, or their combination; it does not alter the primary result.

## Reproducibility, data, and outputs

Save exact direct and modifier configurations, pressure residuals, logs,
internal-state summaries, inlets, terminal mappings, openBF configurations,
solver status, and aggregate metrics. Keep participant-linked material,
per-body parameter records, and full per-run trajectories outside the public
repository. Retain the complete search history, including failures.

Required tables cover direct targets, all modifier evaluations and accepted
solutions, internal-state differences, and coupled waveform metrics. Required
figures show pressure residuals, internal-state effects, successful/failure
geometry, and phase-normalised waveform overlays.

Any change to targets, bounds, tolerance, objective, selection rule, output
set, bridge rule, or attribution threshold requires an amendment before the
affected final search is run.
