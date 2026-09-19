# Pressure-matched route experiment, restart-safe results

Date: 2026-09-19. Protocol and implementation changes are recorded in Amendments 1–4. Full Pulse traces, scenario logs, and OpenBF run output remain private; compact result tables, run manifests, generated OpenBF configurations, and flow inlets are tracked separately.

## Engine and search validation

The search used Pulse commit `99e2d50cb7d0e0893690bf113d2f7924bb933f56`. The amended Stage 0 gate passed two independent clean `HemorrhageToShock` runs with byte-identical CSV output (SHA-256 `c22dd3e5153ab19d18a9efef8c6e52a4a3a8575e43b317020181983c5e3fb932`). The historical mild and intermediate modifier coordinates were each run in three independent Pulse processes; every replicate was stationary and produced identical endpoint pressures across processes. Their old low-pressure restart collapse did not recur.

The corrected search contains 750 successful, stationary modifier evaluations:

| Resolution | Mild | Intermediate | Higher | Total |
|---|---:|---:|---:|---:|
| Coarse, 0.1 | 77 | 77 | 77 | 231 |
| Refine, 0.02 | 112 | 112 | 112 | 336 |
| Refine, 0.005 | 72 | 72 | 39 | 183 |

The 0.005 higher-target neighborhood was clipped at the declared resistance-domain upper bound. All listed evaluations passed the Amendment 2 stationarity test.

Amendment 4 documents and corrects the mixed-grid refinement-seed defect found during the first 0.005 attempt. That attempt produced 228 complete higher-target traces and 16 interrupted cases. Its private traces and logs are archived, and its compact table labels every row as exploratory and excluded. None of those runs enters the 750-evaluation search, candidate selection, or confirmation.

## Independent pressure-match confirmations

Eighteen candidates met both ±0.25 mmHg residual limits and the stationarity gate, then passed independent reruns: five mild, nine intermediate, and four higher. The primary for each target is the accepted solution nearest to stock `(R=1,C=1)`.

| Target | Primary R | Primary C | SBP / DBP (mmHg) | Independent rerun residual SBP / DBP (mmHg) | CO (L/min) | SVR (mmHg·s/mL) |
|---|---:|---:|---:|---:|---:|---:|
| Mild | 1.300 | 0.715 | 128.850 / 80.252 | −0.163 / +0.066 | 5.030 | 1.213 |
| Intermediate | 1.715 | 0.595 | 139.795 / 89.568 | −0.158 / −0.194 | 4.229 | 1.594 |
| Higher | 1.985 | 0.460 | 148.680 / 90.705 | +0.075 / −0.002 | 3.823 | 1.847 |

All independent reruns passed. Direct-target states were 129.013/80.186, 139.954/89.763, and 148.605/90.707 mmHg for mild, intermediate, and higher targets respectively.

## Corrected-engine OpenBF factorial

The four 15-cycle OpenBF simulations all converged. The design crossed the direct or confirmed modifier flow inlet with direct or modifier global WK3 resistance scaling; wall stiffness and terminal compliance remained at the ADAN56 values. Both inlet cycles averaged eight Pulse cycles with 0.84 s period. Flow-integral cardiac output differed from Pulse-reported cardiac output by 0.829% for the direct inlet and 0.850% for the modifier inlet.

In the route-matched diagonal, mean pressures remain close while pulse pressures separate:

| Site | Direct mean / PP (mmHg) | Modifier mean / PP (mmHg) | Direct-minus-modifier PP | PP effect / Stage 4.6 perturbation benchmark |
|---|---:|---:|---:|---:|
| Aortic arch I | 114.995 / 22.107 | 114.322 / 13.902 | 8.205 | 4.44× |
| External carotid R | 114.729 / 26.632 | 114.203 / 17.666 | 8.966 | 8.85× |
| Internal carotid R | 114.571 / 34.519 | 114.109 / 25.478 | 9.041 | 7.27× |

All three pulse-pressure separations clear the pre-existing 1.25× inlet-perturbation attribution threshold. Phase-aligned normalized shape RMSE is 0.0187 at the aortic arch (0.71× benchmark), 0.0447 at the external carotid (1.17×), and 0.0776 at the internal carotid (1.89×). Only the internal-carotid shape comparison clears the threshold.

Across the four factorial cases, the direct-minus-modifier inlet effect on mean pressure is +58.73 to +58.76 mmHg across the three sites; the direct-minus-modifier resistance effect is −58.06 to −58.30 mmHg. The mean-pressure interaction is about −31.5 mmHg at each site. All twelve single-factor shape contrasts clear the 1.25× benchmark. These are model sensitivity and attribution results; they do not establish that either route is physiologically superior.

## Reproducibility artifacts

- `results/pressure_matched_routes_v2/run_manifest.json` records the engine, protocol, Stage 0, build, and software revisions.
- Search and candidate summaries: `search_evaluations.csv`, both `search_checkpoint_refine_*.csv` files, `confirmation_evaluations.csv`, `accepted_solutions.csv`, and `primary_solutions.csv`.
- Restart-safe targeted panel and excluded exploratory audit: `targeted_historical_panel.csv`, `exploratory_refinement_seed_filter_bug.csv`, and `refinement_seed_filter_audit.json`.
- OpenBF results: `coupled_openbf/run_manifest.json`, `run_status.csv`, `waveform_metrics.csv`, `factorial_contrasts.csv`, `primary_noise_attribution.csv`, and `factorial_shape_attribution.csv`. Generated case configurations and compact inlets accompany these summaries; solver outputs and logs remain private.
