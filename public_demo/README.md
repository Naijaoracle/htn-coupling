# Public synthetic demonstration

This directory generates the data behind the public digital-patient demonstrator. It produces **one generic, fully synthetic 60-second exercise-recovery episode**. It does not read, anonymise or perturb any research recording.

```bash
python public_demo/generate_synthetic_demo.py \
    --spec public_demo/synthetic_demo_spec.json \
    --output <site>/public/data/digital-patient/synthetic_demo.json
```

A `manifest.json` (spec and payload hashes, seed, generator version) is written beside the output. The run is deterministic for a given spec and seed.

## Structure-preserving exchange CSV (for the Streamlit dashboard)

`generate_synthetic_session_csv.py` writes a synthetic file with the research exchange table's 25 columns (plus `data_class`), the same nine logical take IDs, the same 21 channel/unit/source series, sampling rates and 12 s estimator windows, and a 72-candidate latent ensemble. It runs the repo's real Y/POS/CHROM and MAX30102 Welch estimators on the synthetic signals.

```bash
python public_demo/generate_synthetic_session_csv.py \
    --spec public_demo/synthetic_session_spec.json --output public_demo/out/synthetic_session.csv
```

On disk the labels stay honest: every row has `data_class=synthetic`, sources carry a `SYNTH:` prefix, sensor-domain rows use `layer=synthetic_observation`, and the dashboard-compatibility latent rows occupying the Pulse-role slots are illustrative exponential curves; Pulse is not run for this exchange CSV. The dashboard's panels match the research names exactly, so `data_contract.load_observations` restores those names **in memory only** for a file that is entirely `data_class=synthetic`, and `app.py` shows a persistent SYNTHETIC DATA banner. Real files are unaffected.

## Website bundle (TimesFM-3 and Pulse on the synthetic input)

`build_site_bundle.py` writes the static `demo.json` and `manifest.json` used by the multimodal demo page on daviddasa.com. It refuses any session CSV that is not entirely `data_class=synthetic`, then actually runs, on the synthetic 30 s context:

- **TimesFM-3**, through `multimodal_demo_next/timesfm_adapter.py` (needs a GPU and the optional `timesfm` dependency; use a separate venv, e.g. `python -m venv public_demo/.venv-timesfm && pip install "timesfm[torch]>=3.0.2" numpy pandas scipy`);
- the repository's **Pulse ensemble conditioning**, over 72 real Pulse trajectories generated from the frozen StandardMale baseline (`multimodal_demo_next/generate_exercise_recovery_ensemble.py`; no participant data is involved).

```bash
python multimodal_demo_next/generate_exercise_recovery_ensemble.py --scenario synthetic_session_demo \
    --take-id recovery_1 --output public_demo/out/pulse/pulse_exercise_recovery_candidates.csv
public_demo/.venv-timesfm/bin/python public_demo/build_site_bundle.py \
    --session-csv public_demo/out/synthetic_session.csv \
    --pulse-candidates public_demo/out/pulse/pulse_exercise_recovery_candidates.csv \
    --model-episode public_demo/model_episode_pulse_openbf.json \
    --spec public_demo/synthetic_demo_spec.json --output-dir <daviddasa>/src/research-artefacts/digital-twin/multimodal-demo
```

The page's "Research results" tab shows the aggregate Recovery 1/2/3 findings from the spec, kept apart from the synthetic traces. `model_episode_pulse_openbf.json` is a Pulse/OpenBF cardiac-cycle model output, not a recording.

## Privacy boundary

- `generate_synthetic_demo.py` and `generate_synthetic_session_csv.py` have no private-data input. Their observation signals are generated from declared specifications and deterministic seeds; they have no argument for an input dataset, and a test fails if one is added.
- `build_site_bundle.py` consumes only those synthetic outputs plus non-participant Pulse/OpenBF model outputs, and **rejects any session CSV that is not entirely `data_class=synthetic`**.
- The bundle carries `data_class: "synthetic"` and `participant_data: false`, uses time from 0 s, and has no absolute timestamps, paths, device or session identifiers, or raw ECG/PPG/audio/video fields. Tests enforce these.
- Parameters are chosen so the display works, not to reproduce any recording.

## What is real and what is synthetic

| Item | Status |
|---|---|
| HR trajectory, ECG-like, PPG-like, RGB, acoustic envelope | Fully synthetic display data. Not participant recordings and not validated sensor forward models; RGB is not a skin, camera or optical model. |
| Y / POS / CHROM rate estimates | The repository's real estimator code, run on the synthetic RGB. |
| Persistence and linear-trend forecasts | Computed from the synthetic context. |
| TimesFM-3 forecast | Actual TimesFM-3 output, generated offline by `build_site_bundle.py` from the synthetic HR context. |
| Pulse HR-constrained projection | Actual weighting of 72 Pulse exercise-recovery trajectories against the synthetic HR context. Not an individualised state estimate. |
| Pulse/OpenBF model episode | Actual mechanistic model output, separate from the synthetic observation episode. Not a recording. |
| `research_results` | Aggregate findings from the private session, entered by the author in the spec. Kept apart from the synthetic signals and not computed here. |

Do not label any curve as TimesFM or Pulse output unless those systems were actually run offline on the synthetic input.

## Tests

`pytest test/test_synthetic_public_demo.py`
