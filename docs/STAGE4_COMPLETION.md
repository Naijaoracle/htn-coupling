# Stage 4 completion: carotid plausibility, sensitivity, and cost

## Outcome

**Stage 4 is complete under the amended aortic gate.** The resistance-scaled Pulse inlet produces plausible distal external- and internal-carotid pressure morphology, all four inlet perturbations and the isolated wall-stiffness perturbation converge, and the 2x stiffness response exceeds the tested inlet-noise floor at both reference sites.

This does not resolve the depressed-baseline question. The coupled aortic pulse pressure remains 20.45 mmHg, below the healthy male 40--49 tenth percentile and approximately 11 mmHg below Charlton's virtual age-45 mean. Stage 5 must repeat the same stiffness perturbation from an approximately age-45-matched 31 mmHg aortic-pulse-pressure baseline before claiming that the compliance response scales correctly.

## 4.5 Distal carotid plausibility

All carotid values use the last spatial column of the openBF vessel output, matching the Stage 3 distal-site definition. The previously blocked analysis script used the first spatial column generically; no result from that path is used here.

| distal site | Stage 3 MAP / PP | Pulse MAP / PP | Stage 3 / Pulse mean flow | primary peak phase, Stage 3 / Pulse |
|---|---:|---:|---:|---:|
| right ECA | 103.04 / 37.78 mmHg | 91.14 / 28.50 mmHg | 175.70 / 147.65 mL/min | 0.182 / 0.162 |
| right ICA | 102.87 / 45.58 mmHg | 90.96 / 39.29 mmHg | 285.99 / 240.29 mL/min | 0.162 / 0.140 |

Both Pulse-driven traces retain three identifiable pressure features. Raw phase-normalised shape correlation is 0.894 at ECA and 0.864 at ICA; normalised RMSE is 0.141 and 0.157. These raw comparisons combine morphology with a 0.020--0.022-cycle earlier primary peak.

For the morphology screen, alignment was bounded to at most 5% of a cycle and the selected shift was retained as a result. Optimal shifts were 0.026 at ECA and 0.022 at ICA. Aligned correlations were 0.955 and 0.934, and aligned normalised RMSE values were 0.098 and 0.126. Both meet the encoded plausibility thresholds of correlation at least 0.90 and RMSE at most 0.20. This is a shape screen, not agreement: the lower pressure and flow amplitudes and earlier feature timing remain explicit.

ICA mean flow remains greater than ECA mean flow under the Pulse inlet. The low-pulsatility inlet is amplified distally rather than erased: aortic PP is 20.45 mmHg, distal ECA PP 28.50, and distal ICA PP 39.29.

## Fourth engine finding

Pulse's `Aorta-InFlow` is a real engine output but lacks the brief post-ejection reverse-flow feature present in the ADAN56 inlet and in physiological aortic flow around valve closure. It is lower-peaked and lower-volume with longer relative ejection. When it drives the distributed model, it produces an aortic pulse pressure below the healthy tenth percentile for StandardMale's age and sex. Pulse does not claim that this compartment-flow trace is a validated physiological aortic waveform, so this is a scope finding rather than a validation failure. It joins the baseline clamp, population-coverage limit, and default baroreflex accommodation as an engine property that constrains the programme.

## 4.6 Inlet and stiffness sensitivity

The selected baseline is the resistance-scaled Stage 4 arm. Four inlet perturbations change flow amplitude or cycle length by +/-5%. The added stiffness case doubles every ADAN56 vessel Young's modulus, an approximate halving of conduit-wall compliance under the model's tube law. Terminal Cc is unchanged, so this isolates distributed arterial stiffness rather than fitting total compliance.

| distal site | maximum inlet waveform RMSE | 2x-E waveform RMSE | ratio | maximum inlet absolute delta PP | 2x-E absolute delta PP | ratio |
|---|---:|---:|---:|---:|---:|---:|
| right ECA | 4.75 mmHg | 7.61 mmHg | 1.60 | 1.02 mmHg | 14.78 mmHg | 14.44 |
| right ICA | 4.76 mmHg | 8.40 mmHg | 1.76 | 1.21 mmHg | 5.54 mmHg | 4.58 |

The full-pressure waveform RMSE is the primary movement metric after resampling each result to cardiac-cycle phase. The worst tested inlet movement is dominated by the +/-5% flow-amplitude cases, which shift mean pressure by approximately +/-4.6--4.75 mmHg. Cycle-length perturbations produce smaller waveform RMSE values of 0.85--1.34 mmHg.

At this depressed baseline, the isolated stiffness signal clears the tested inlet-noise floor at both carotid references. That makes Stage 5 attribution feasible for an E change of this size. It does not establish the response to smaller stiffness changes, nor whether the response magnitude is preserved from an age-matched rather than depressed baseline.

## 4.7 Runtime

All five completion cases converged in four to six cardiac cycles. End-to-end wall time, including Julia/openBF startup, ranged from 53.5 to 66.9 s; solver time ranged from 18.2 to 30.2 s. The earlier two base arms took 54.4 and 59.3 s. A Stage 5 operating-point sweep is therefore a roughly one-minute-per-cell CPU workload before orchestration overhead.

## Acceptance criteria

1. Stage 0 byte identity: pass; both regression files retain SHA-256 `462c43248785ce45771b056b53443252414ec066ae50bee0d3b276a42fcfab0a`.
2. Stage 2 extended sweep: complete.
3. Versioned interface and isolated unit conversion: pass.
4. Stable periodic inlet and flow integral: pass.
5. Both resistance arms: complete.
6. Aortic gate: original Pulse-agreement gate failed; amended mean-plus-physiological-plausibility gate passed for the scaled arm.
7. Distal carotid morphology: pass at ECA and ICA, with amplitude and timing differences retained.
8. Inlet sensitivity: quantified; 2x wall-stiffness response exceeds tested +/-5% inlet movement at both sites.
9. Runtime: recorded.

Stage 5 may proceed. Its first sensitivity obligation is to repeat the 2x-E response from an approximately 31 mmHg aortic-PP baseline and compare response scaling with the present 20.45 mmHg baseline.

## Reproducibility artefacts

- `scripts/finish_stage4.py` and `scripts/run_stage4_completion.sh`
- `config/stage4_completion_v1.json`
- `results/stage4_completion/carotid_plausibility.csv`
- `results/stage4_completion/carotid_sensitivity.csv`
- `results/stage4_completion/stage5_noise_floor.csv`
- `results/stage4_completion/stage4_completion_summary.json`
- `results/stage4_completion/carotid_shape_plausibility.png`
- `results/stage4_completion/carotid_sensitivity.png`
- exact generated inputs and YAML under `results/stage4_completion/configs`
