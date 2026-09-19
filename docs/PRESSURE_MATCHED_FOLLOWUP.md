# Pressure-matched higher-target waveform attribution and restart diagnosis

Date: 2026-09-18. This follow-up applies the protocol's Stage 4.6 perturbation benchmark and 1.25x attribution threshold, then documents the focused low-target restart investigation. The threshold is a tested inlet-perturbation benchmark, not solver noise.

## Higher-target primary pair

Primary pair: direct inlet with direct-SVR WK3 scale versus the confirmed modifier inlet with modifier-SVR WK3 scale. Wall Young's moduli and WK3 compliance remain at ADAN56 values. The two independent OpenBF repeats reused the exact same YAML and inlet files as their original runs. Both converged, and all reported site metrics and pressure traces were identical to their original runs (zero metric deltas; phase-aligned repeat RMSE 0).

| Site | Metric | Direct minus modifier / effect | Stage 4.6 perturbation floor | Effect / floor | Clears 1.25x? |
|---|---|---:|---:|---:|---|
| Aortic arch I | Pulse pressure | 8.147 mmHg | 1.849 mmHg | 4.41x | Yes |
| Aortic arch I | Phase-aligned normalized shape RMSE | 0.0184 | 0.0265 | 0.70x | No |
| Right ECA | Pulse pressure | 8.848 mmHg | 1.013 mmHg | 8.74x | Yes |
| Right ECA | Phase-aligned normalized shape RMSE | 0.0451 | 0.0382 | 1.18x | No; below the 1.25x rule |
| Right ICA | Pulse pressure | 8.855 mmHg | 1.244 mmHg | 7.12x | Yes |
| Right ICA | Phase-aligned normalized shape RMSE | 0.0784 | 0.0411 | 1.91x | Yes |

Pulse pressure clears the criterion at all three sites. Shape clears it at the ICA; the ECA effect is above the measured perturbation floor but does not reach the predeclared 1.25x margin, and the arch effect is below the floor. Mean pressure differences are small and do not clear their floors. ICA diastolic pressure difference clears at 1.27x; ICA time-to-peak phase difference is exactly 1.25x. The withdrawn reflected-wave/augmentation detector is excluded from this attribution.

The existing 2x2 inlet-by-resistance sensitivity was also evaluated with the same shape metric. Each one-factor comparison (inlet at either resistance setting and resistance at either inlet setting) clears 1.25x at all three sites. This supports contributions from both input waveform and terminal resistance in this model. It does not change the primary route-matched result.

## Restart investigation

All four archived first/repeat cases identify Pulse revision `a04eaa690`; their modifier coordinates are identical within each target. The stock serialized starting file is shared (current SHA-256 `2f1c4416afec84b1b903988aa98833b7e672169a072c6f826a45aa90a7ef2115`). At mild (R=1.300, C=0.720), the first run is stationary at 128.705/80.404 mmHg, while two independent reruns both give 76.970/30.346 mmHg and fail stationarity. At intermediate (R=1.720, C=0.600), the first run is stationary at 139.688/89.818 mmHg, while both reruns give 85.647/36.297 mmHg and fail stationarity.

One additional mild rerun reproduced the alternate branch. An internal track captured all 600 seconds of `AdvanceUntilStable` and the first 12 seconds after it returned; a separate 12-second track sampled ICP, cerebral perfusion pressure, blood volume, brain inflow, and baroreceptor scales. During stabilization, heart-rate scale crossed below 0.5 at 14.06 s and resistance scale below 0.8 at 12.16 s, then reached their lower limits (about 0.010 and 0.400). Despite those extreme reflex settings, MAP remained about 105.8 mmHg and heart rate 72 bpm through 600 s. At 600–601 s MAP began to fall (105.83 to 104.32) and heart rate to 69.15; in the next second MAP plunged to 61.01 and systemic resistance from 1.2445 to 0.6260. MAP first crossed below 90 at 601.02 s. Heart rate crossed below 60 only at 603.84 s. This establishes that the abrupt pressure collapse begins at the stabilization-to-active-advancement boundary, after a long stable interval with reflex scales already at their limits.

In the post-stabilization 12-second window, heart rate fell from 72 to 44 bpm, brain inflow from about 1,012 to 473 mL/min (first- versus last-second medians), and cerebral perfusion pressure from about 97 to 42 mmHg. Blood volume increased by about 1.55 mL over the recorded window and increased at each sampled step, so falling blood volume does not explain this particular collapse.

The pinned Pulse controller source sets the ordinary baroreceptor and chemoreceptor feedback switches off during a non-incremental cardiovascular-modifier stabilization, then turns them on and resets pressure baselines before returning. When Stage 7 resetting is active, `NervousModel::PreProcess` continues computing baroreceptor scales while that ordinary switch is off; `CardiovascularModel` applies those scales only when the switch is on. Thus a run with Stage 7 active can accumulate extreme scales during stabilization and apply them abruptly at the boundary.

A deeper state-restoration defect explains why identical restarts can choose different branches. In the pinned source, `m_Stage7ResettingEnabled` is a plain `bool` with no default initializer. `NervousModel::Clear()` and `SetUp()` do not assign it. `PBPhysiology::Load(NervousData, NervousModel)` calls `Clear()`, `SetUp()`, and then restores serialized fields, but the Stage 7 enable flag is not in the protobuf serialization. The stock state has no Stage 7 patient reset parameters, so on this load path the flag can remain indeterminate. The serialized reset midpoint is zero/absent in the stock state, which is why its appearance later is a useful marker for the Stage 7 path.

The two-setting transition diagnostic first showed a strong association between state reload and branch changes. The source defect is definite: the Stage 7 enable flag is not serialized, and the pinned `Clear()`/`SetUp()` do not initialize it. However, the saved mild state has a nonzero serialized reset midpoint (80.19 mmHg), while the intermediate state has no midpoint; the saved patient itself has no Stage 7 reset parameters. A diagnostic-only patch that derives the flag from patient fields therefore loses the mild branch. A second patch restored the flag from the serialized midpoint, but neither patch produced repeatable outcomes across sequential fresh engine objects. These tests do not establish that the omitted flag is the sole cause of the low-pressure restart behavior.

In the mild failing trace, the pressure fall begins before severe bradycardia; the ICP event is only set/cleared in the searched source and is not consumed by another model, so it is a marker rather than an established trigger. The saturated-branch heart-rate sign discussed below may amplify the decline after the branch switch.

The instrumented failed trace has reflex scales at or near their bounds (heart-rate scale about 0.010 down to 0.005; resistance 0.400 to 0.402; elastance about 0.950; compliance about 1.300). A pinned-source code review found a plausible amplifier worth a targeted engine-level check: in the saturated baroreceptor branch, the heart-rate scale update has a leading negative multiplier (`-1.3 * effectiveness * (target-current)`), unlike the positive multiplier in the unsaturated branch. With the positive effectiveness branch selected when blood volume is not falling, this sign can push heart rate away from a positive sympathetic target. That is consistent with the observed reflex scales and bradycardia, but it does not yet prove what selects the failing branch or that this expression alone causes the initial pressure drop.

A source search found no direct calls to common C/C++ RNG APIs in the pinned engine/CDM source directories. This does not rule out indirect nondeterminism, but combined with the same starting file, parameters, and runtime revision it makes a nonlinear branch/feedback sensitivity more plausible than an ordinary seeded random effect.

## Diagnostic-only restart repair attempts

A separate Pulse source copy at `/tmp/pulse-stage7-diagnostic` was built and installed under `/tmp`; it did not modify the pinned engine or primary results. The first patch initialized the branch flag to false and derived it from patient reset parameters. Four reloads of each saved state did not match: reload four diverged in both cases. Four fresh processes loading the mild state once each did match bitwise, ending at 65.85/23.63 mmHg and MAP 43.18 mmHg. This is repeatable, but it remains a severe pressure collapse.

The saved state schema provides a better restoration marker: mild has a reset midpoint of 80.19 mmHg and intermediate has no midpoint. A second diagnostic patch restores the omitted flag from this serialized midpoint after loading. Four sequential engine reloads still diverged: mild MAP endpoints were 42.62 then 43.03 mmHg; intermediate endpoints alternated between 88.55 and 95.03 mmHg. Reloading four times into the same engine object was stable at approximately 88.55 mmHg.

Heap-poisoning runs (`MALLOC_PERTURB_` 17, 85, and 165) made each process internally consistent, but shifted intermediate endpoint MAP between 88.15 and 88.55 mmHg. Initializing two other state-load-only CSF rates in `Clear()` did not remove this sensitivity. An immediate load-and-resave comparison reproduced all physiological JSON fields exactly; only data-request tracking metadata differed. That points to transient engine state or construction details outside the saved physiology fields, but it does not identify the specific field.

A separate isolated test flipped the saturated baroreceptor heart-rate coefficient from -1.3 to +1.3. It did not rescue the mild collapse (MAP still ended near 42.6–43.0 mmHg) or the intermediate collapse (88.55–95.03 mmHg). This coefficient is not supported as the primary trigger. Most importantly, deterministic restoration of the Stage 7 flag alone still leaves the restart collapse.

All traces and per-run summaries are in `results/pressure_matched_routes/private/restart_transition_diagnostic/`; `repeatability_investigation_summary.json` indexes the tests and `diagnostic_engine_patch.diff` records the isolated patch. The patch is diagnostic evidence only, not ready to apply to the primary engine.

### Causal result (2026-09-19)

The restart pressure collapse is explained by cardiovascular mechanics action modifiers missing from the checkpoint reload path. The saved checkpoint has an empty `ActiveActions` map, while the live model retains the nonincremental mechanics action’s systemic resistance and compliance multipliers. On fresh-engine load, the transient modifier object starts at its default multipliers of 1.0. At the first cardiovascular preprocessing step, it recomputes circuit parameters using those defaults. In the mild case, aortic compliance changes from the action-scaled 0.833703 to the baseline 1.15792; systemic resistance is also reset. The pressure divergence begins before the baroreflex response changes, so reflex saturation is downstream.

This was tested against the original archived mild and intermediate checkpoints. A diagnostic-only reload control that reapplied the saved resistance and compliance action multipliers reproduced every field of the uninterrupted 12-second continuation exactly (maximum absolute difference 0.0). Four sequential fresh-engine reloads for each case also matched exactly. The same result held under `MALLOC_PERTURB_` values 17, 85, and 165. These runs support a deterministic missing-state cause, rather than heap-sensitive numerical instability.

The diagnostic environment-variable hook and trace instrumentation remain confined to `/tmp/pulse-stage7-diagnostic`. A clean candidate patch is now prepared at `patches/pulse-checkpoint-restart-state.patch`. It adds all ten cardiovascular mechanics multipliers to serialized cardiovascular state, restores them after model setup, initializes the Stage 7 state members, and persists the Stage 7 enable flag. Older checkpoints without the new modifier message remain readable and use normal default multipliers; their lost action coordinates cannot be inferred generically. The archived test states predate this schema, so the regression injects their known action coordinates before testing save/reload.

The candidate compiled in the isolated diagnostic build after protobuf regeneration. The new regression passed for mild and intermediate: each first reload and second save/reload continuation matched its archived uninterrupted trace exactly (maximum absolute difference 0.0). This proves the serialization path for the known cases. The engine source at `/tmp/pulse-htn-a04` remains untouched; the candidate patch still needs to be applied and checked in the intended upstream writable checkout before treating it as the production engine fix.

There is also a separate missing-state defect: `m_Stage7ResettingEnabled` and its reset midpoint/offset members lacked safe initial values, and the flag was not serialized. The candidate initializes those state members, persists the flag, and uses a nonzero midpoint as a compatibility fallback for older states. This is a separate issue from the mechanics modifier loss. Fine search remains paused until the patch is applied to the production engine checkout and the same regressions pass there. No production engine source has been modified and no commit has been made.

## Conclusion and next diagnostic

The higher-target waveform difference is robust to an independent OpenBF repeat and exceeds the Stage 4.6 perturbation benchmark for pulse pressure at all three sites and normalized shape at the ICA. The route-matched ECA shape result is inconclusive under the predeclared 1.25x margin.

The restart collapse has a causal explanation: nonincremental cardiovascular mechanics action modifiers are absent after checkpoint reload, so the first cardiovascular preprocessing step resets systemic resistance and aortic compliance to baseline. The isolated candidate now serializes/restores the modifier set and Stage 7 flag; both archived cases match their uninterrupted continuation exactly through a first load and a second save/reload. The regression is recorded in `scripts/test_pressure_matched_restart_serialization.py` and `PRESSURE_MATCHED_RESTART_REGRESSION.json`. The candidate diff is reviewable in `patches/pulse-checkpoint-restart-state.patch`. Apply and validate it in the writable production Pulse checkout before resuming fine search. Keep the pinned model and primary results unchanged.

## Reproducibility files

- `scripts/finish_pressure_matched_comparison.py`
- `results/pressure_matched_routes/coupled_openbf/primary_noise_attribution.csv`
- `results/pressure_matched_routes/coupled_openbf/factorial_shape_attribution.csv`
- `results/pressure_matched_routes/coupled_openbf/repeat_run_status.csv`
- `results/pressure_matched_routes/coupled_openbf/repeatability_metrics.csv`
- `results/pressure_matched_routes/coupled_openbf/primary_waveform_noise_attribution.png`
- `results/pressure_matched_routes/restart_instability_diagnostics.csv`
- `results/pressure_matched_routes/restart_instability_diagnosis.json`
- `results/pressure_matched_routes/private/restart_instrumentation/mild_R1.300_C0.720/`
- `scripts/diagnose_pressure_matched_restart_transition.py`
- `results/pressure_matched_routes/private/restart_transition_diagnostic/`

- `results/pressure_matched_routes/private/restart_transition_diagnostic/repeatability_investigation_summary.json`
- `results/pressure_matched_routes/private/restart_transition_diagnostic/diagnostic_engine_patch.diff`

- `scripts/test_pressure_matched_restart_serialization.py`
- `PRESSURE_MATCHED_RESTART_REGRESSION.json`
- `patches/pulse-checkpoint-restart-state.patch`
