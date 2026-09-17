# Pressure-matched route predeclaration amendment 1

## Reason for amendment

The initial predeclaration pinned Pulse revision `e8a36497b8ba78e788dc201a6baf74e1c297c56f` and the Stage 0 reference hash `462c43248785ce45771b056b53443252414ec066ae50bee0d3b276a42fcfab0a`. That revision does not recognize the Stage 6 patient envelope fields used by the declared direct-patient construction (`SystolicArterialPressureBaselineMinimum/Maximum`, `DiastolicArterialPressureBaselineMinimum/Maximum`, and `DiastolicToSystolicPressureRatioMaximum`). All three predeclared direct targets therefore fail initialization at that revision.

Pulse revision `a04eaa690c9f8535eaf3ca8cdd8bfe8ee091fa1f` supports those fields and is the engine implementation used by the Stage 6 bounds construction. Its Stage 0 output differs bytewise from the older archived reference, so the old gate cannot validate this implementation. This amendment pins the compatible revision and replaces the inherited Stage 0 comparison with a repeatability gate at the amended revision.

## Amended fixed implementation and Stage 0 gate

Use exactly Pulse revision `a04eaa690c9f8535eaf3ca8cdd8bfe8ee091fa1f`. The built engine revision must report the same Git hash. Do not mix binaries, Python bindings, runtime data, or source from another revision.

Before any direct or modifier search evaluation, perform two independent clean `HemorrhageToShock` StandardMale scenario runs with that same build and environment. Save each result CSV and log under `results/pressure_matched_routes/private/stage0_repeats/`. Each run starts from a new engine process and regenerates the scenario output; neither run may reuse the other run's output. The Stage 0 amendment gate passes only when both CSVs have identical byte counts and identical SHA-256 hashes. Record the common hash, both paths, and Pulse revision in `results/pressure_matched_routes/stage0_regression_gate.json`; record build configuration and environment in the run manifest before any search evaluation.

The original Stage 0 gate remains preserved as the historical gate for revision `e8a36497`; it is not silently rewritten. A failed or non-repeatable amended gate stops the pressure-matched experiment.

## Scope retained

All target pressures, direct patient payload, modifier bounds, grid spacing, objective, acceptance tolerances, rerun rule, outcome list, selection rule, and coupled-analysis declaration from the original predeclaration remain unchanged. This amendment changes only the engine revision required by the direct patient schema and the corresponding Stage 0 baseline validation procedure. Results must identify this amendment.

No final search evaluation is admitted until this amendment is recorded and the amended Stage 0 gate passes.
