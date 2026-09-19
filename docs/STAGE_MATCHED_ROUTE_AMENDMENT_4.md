# Pressure-matched route predeclaration amendment 4

Date: 2026-09-19

## Reason for amendment

During the amended fresh search, the `0.02` refinement produced a completed surface, but the first `0.005` run exposed a search-runner defect. The runner selected minima from the combined coarse and refined table while comparing neighbors at `0.02` spacing. Coarse points outside a refined patch have no `0.02` neighbors, and the old logic treated an empty neighbor set as a local minimum. This caused unrelated higher-target neighborhoods to be evaluated in the exploratory `0.005` run.

The exploratory fine run was stopped before it produced an aggregate checkpoint. Its private logs and traces are retained under `results/pressure_matched_routes_v2/private/exploratory_refinement_seed_filter_bug/`. These runs are excluded from the pressure-matching results and from any selection or confirmation. The completed coarse grid and the completed `0.02` refinement checkpoint remain valid.

## Corrected refinement rule

Each refinement level will take seeds only from successful, stationary points evaluated on the immediately preceding completed grid:

* `0.02` seeds come from the completed coarse grid.
* `0.005` seeds come from the completed `0.02` grid.

A point with no adjacent evaluations at the preceding grid spacing is not a minimum. Refinement candidates must remain inside the predeclared neighborhood around these minima. The runner now saves aggregate results after each batch, and a resumed stage skips recorded parameter coordinates.

## Scope

The pinned Pulse implementation remains `99e2d50cb7d0e0893690bf113d2f7924bb933f56`. Targets, route definitions, modifier domain, coarse spacing, objective, pressure residual tolerances, stationarity limits, measured outcomes, selection rule, and downstream coupled analysis remain unchanged. The `0.02` completed results are retained. The `0.005` step will be rerun with the corrected seed rule before independent confirmations.

No `0.001` refinement is authorized by this amendment.
