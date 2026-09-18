# Pressure matched route experiment: results and next-step record

Date: 2026-09-18. All per-case Pulse traces and logs remain under `private/cases/`; compact result tables and the downstream OpenBF comparison are saved alongside this report.

## Search and confirmation

- Coarse search: 231 evaluations.
- Refinement at 0.02: 539 completed rows.
- Refinement at 0.005: 6,980 unique parameter rows, including 26 interrupted cases without a saved trace. The 0.001 refinement was not run.
- Reconstruction found 7,787 case folders and 7,761 saved traces: 209 mild, 3,003 intermediate plus 26 without traces, and 4,549 higher-target cases.
- Nine independent reruns are recorded in `confirmation_evaluations.csv`. Three higher-target solutions passed both the stationarity gate and independent rerun requirement. The provisional nearest-confirmed setting remains R=1.995, C=0.465; it is explicitly provisional because the 0.001 search was not completed.

Two exact reruns each were made at the apparent mild and intermediate matches. Their first saved runs were 128.705/80.404 mmHg (R=1.300, C=0.720) and 139.688/89.818 mmHg (R=1.720, C=0.600). Both repeats at each setting returned the same alternate trajectory: 76.970/30.346 and 85.647/36.297 mmHg, respectively. Each failed pressure matching and the stationarity gate; the repeats within each pair were identical. This is strong evidence that the apparent low-target matches are not reproducible under the current restart procedure. The saved logs show intracranial hypotension, baroreceptor saturation, and bradycardia during the alternate trajectories; temporal coincidence is observed, but the causal mechanism is not established.

## Four-case OpenBF factorial comparison

The 2x2 comparison crossed direct versus modifier flow inlet with direct versus modifier global WK3 resistance. Wall stiffness and terminal compliance remained at ADAN56 values. Each case converged. The source Pulse traces passed the 1% flow-integral check (0.829% direct; 0.842% modifier), and each inlet averaged eight cycles with 0.84 s period. The compact source traces do not contain aortic pressure; the run uses flow-only inlet data, and the unused pressure placeholder in extraction is documented in the script and manifest.

In the diagonal, route-matched cases:

| Site | Direct route mean / pulse pressure (mmHg) | Modifier route mean / pulse pressure (mmHg) |
|---|---:|---:|
| Aortic arch I | 114.99 / 22.11 | 114.30 / 13.96 |
| External carotid R | 114.73 / 26.63 | 114.18 / 17.78 |
| Internal carotid R | 114.57 / 34.52 | 114.08 / 25.66 |

Thus, matched mean pressure in this vascular model coexists with markedly different pulse pressure: the modifier route is lower by about 8.1 mmHg at the aortic arch and 8.85 mmHg at each carotid site. The two saved Pulse routes had similar higher-target systemic SBP/DBP, but substantially different cardiac output (about 6.42 vs 3.84 L/min) and SVR (1.070 vs 1.836 mmHg·s/mL).

Across all four cases, the averaged direct-minus-modifier inlet effect on mean pressure was +58.1 mmHg at the aortic arch and +58.2 mmHg at both carotids. The averaged direct-minus-modifier resistance effect was -57.4 to -57.7 mmHg. These large, opposing effects nearly cancel in the diagonal route-matched cases. This indicates strong dependence on both inlet flow and downstream resistance; it does not establish that either route is physiologically superior. The crossed cases are sensitivity attribution checks, not additional pressure-matched phenotypes.

## Saved artifacts

- Search/reconstruction tables: `coarse_search_evaluations.csv`, `search_checkpoint_refine_0.02.csv`, `search_checkpoint_refine_0.005.csv`, `search_evaluations.csv`, and `reconstructed_completed_cases.csv`.
- Repeat and accepted-solution tables: `confirmation_evaluations.csv`, `confirmed_solutions.csv`, `provisional_primary_confirmed.csv`.
- Four-case downstream run: `coupled_openbf/run_manifest.json`, `coupled_openbf/run_status.csv`, `coupled_openbf/waveform_metrics.csv`, and `coupled_openbf/factorial_contrasts.csv`; configs, flow inlets, convergence files, and runner logs are saved by case under `coupled_openbf/`.

## Validation performed

- Python compilation passed for the route-search, reconstruction, and OpenBF runner scripts.
- Reconstruction rerun completed and regenerated the tables above.
- All four OpenBF jobs returned code 0 and converged.
- The direct and modifier inlet flow integrals were within 1% of reported Pulse cardiac output.
- `git diff --check` passed for tracked source changes.

## Recommendation

Do not spend another long run on a dense mild/intermediate grid until the alternate-trajectory behavior is understood. The 0.001 higher-target refinement can be considered later only if a tighter nearest-to-stock setting is necessary; the current high-target evidence already supports three reproducible pressure matches and the downstream factorial shows the intended route-dependent waveform difference.
