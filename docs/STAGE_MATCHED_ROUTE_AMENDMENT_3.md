# Pressure-matched route predeclaration amendment 3

Date: 2026-09-19

## Reason for amendment

The restart investigation established that a nonincremental cardiovascular mechanics modification affected the live Pulse engine but was not preserved when a checkpoint was loaded into a new engine. This invalidated the prior mild and intermediate restart results as reproducible pressure matches. Those results remain historical evidence for Pulse revision `a04eaa690c9f8535eaf3ca8cdd8bfe8ee091fa1f`; they are not pooled with results from the corrected engine.

## Fixed Pulse implementation

The amended experiment pins Pulse commit `99e2d50cb7d0e0893690bf113d2f7924bb933f56`, based on `a04eaa690c9f8535eaf3ca8cdd8bfe8ee091fa1f`. The change persists cardiovascular mechanics modifiers and Stage 7 reset state in checkpoints. It also gives deterministic initialization to the intrinsic contractility modifier, Stage 7 state members, and the two state-loaded CSF rates that were found uninitialized in the diagnostic build.

Validation on the committed implementation:

* `Pulse`, `PulseTests`, `PulseScenarioDriver`, `PulseTestsDriver`, and the Pulse Python extension built successfully.
* Three independent Pulse test-driver processes passed `SerializationTest`. Each process exercised the historical mild `(R=1.300, C=0.720)` and intermediate `(R=1.720, C=0.600)` cases, comparing uninterrupted continuation with checkpoint reload and a second reload. SBP, DBP, heart rate, and cardiac output were required to agree within `1e-9` for each continuation step.
* The serialization regression also passed loading the older StandardMale baseline state, the existing repeated save/load file comparison, explicit Stage 7 checkpoint round-tripping, and the legacy nonzero-midpoint fallback.
* Pulse's 75-case `SetupPatientTest` passed.
* This offline build registered no CTest tests; the full Pulse test catalogue was not run.

New checkpoints retain the active cardiovascular mechanics modifiers and Stage 7 reset state. A pre-fix checkpoint that omitted cardiovascular mechanics modifiers cannot recover their historical values; it must not be treated as a checkpoint of a known modified state. Legacy Stage 7 restoration keeps the patient-derived setup state and infers enabled state from a nonzero serialized reset midpoint.

## Amended search admission and result namespace

All outputs from the corrected engine go under `results/pressure_matched_routes_v2/`. The original results remain unchanged and identify the pre-fix engine revision.

The direct state for each target must pass the Amendment 2 stationarity gate before any modifier evaluations are admitted. Refinement seeds are restricted to successful, stationarity-passing evaluations; nonstationary low-objective points cannot seed a local refinement. The search runner includes a targeted historical panel that runs each of the three coordinates below in three separate worker processes after direct-target stationarity passes:

Coarse-grid batches are checkpointed to `search_evaluations.csv` as they complete. A resumed run skips parameter coordinates already recorded as completed, avoiding lost work after interruption.

| Target | Resistance multiplier | Arterial compliance multiplier |
|---|---:|---:|
| Mild | 1.300 | 0.720 |
| Intermediate | 1.720 | 0.600 |
| Higher | 1.995 | 0.465 |

Each replicate starts a fresh Pulse engine process and uses the amended Pulse build, the same StandardMale baseline state, and the declared 12-second measurement and stationarity procedure. Direct target measurements and each modifier replicate are saved as aggregate CSV results. Full traces and run logs remain in the private case directory.

The run manifest records the Pulse source revision, CMake build directory, and runtime data directory. `PULSE_BUILD_DIR` and `PULSE_BIN` may point to isolated build and install locations; these path settings do not change the engine or data.

When `PULSE_ROOT` is explicitly set, the pressure-matching runner checks the embedded hash in the loaded `PyPulse` extension against the checked-out Pulse commit before creating an engine. A source/build/binding mismatch stops the evaluation.

The amended Stage 0 gate must pass before the targeted panel or search: two independent new Pulse processes run the clean `HemorrhageToShock` StandardMale scenario. Their CSV byte counts and SHA-256 hashes must match. Save their CSVs and logs privately under `results/pressure_matched_routes_v2/private/stage0_repeats/` and record their hashes and Pulse revision in the v2 Stage 0 gate and run manifest.

## Scope and search resolution

Targets, route definitions, modifier domain, coarse spacing, objective, pressure residual tolerances, stationarity limits, measured outcomes, selection rule, and downstream coupled analysis remain unchanged. The fresh search proceeds through the declared coarse grid and `0.02` and `0.005` refinement levels. The `0.001` refinement level is deferred until the targeted panel and `0.005` results have been reviewed; it is not part of this amended run.

No corrected-engine search evaluation is admitted until the amended Stage 0 gate passes. All results must identify this amendment and the pinned Pulse commit.
