#!/usr/bin/env python3
"""Build the public website bundle from SYNTHETIC inputs only.

Inputs (all synthetic or model-only, never a recording):
  --session-csv        the synthetic exchange CSV (must be entirely data_class=synthetic; enforced)
  --pulse-candidates   72 real Pulse trajectories from the frozen StandardMale baseline (no participant data)
  --model-episode      Pulse/OpenBF cardiac-cycle model output (no participant data)
  --spec               synthetic_demo_spec.json (banner text, aggregate research results)

Offline models actually run here, on the synthetic 30 s context:
  * TimesFM-3 (needs the timesfm venv and a GPU)
  * Pulse ensemble conditioning (the repository's condition_pulse_ensemble)

    python build_site_bundle.py --session-csv out/synthetic_session.csv \
        --pulse-candidates out/pulse/pulse_exercise_recovery_candidates.csv \
        --model-episode model_episode_pulse_openbf.json --spec synthetic_demo_spec.json --output-dir <site>/multimodal-demo
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
APP = HERE.parent / "multimodal_demo_next"
sys.path.insert(0, str(APP))
from data_contract import is_synthetic, load_observations  # noqa: E402
from forecast_evaluation import prepare_holdout, reference_baselines, score_point_forecast  # noqa: E402
from mechanistic_forecast import condition_pulse_ensemble  # noqa: E402
from timesfm_adapter import forecast_bpm  # noqa: E402

TAKE = "recovery_1"
SERIES = "h10_raw_ecg_rr_bpm | H10_raw_ECG_fixed_5-25Hz_RR"
SCHEMA = "public_synthetic_demo_v2"


def pts(t, v, nd=3):
    return [[round(float(a), nd), round(float(b), 6)] for a, b in zip(t, v)]


def take_rows(frame, channel, source=None):
    m = frame["take_id"].astype(str).eq(TAKE) & frame["channel"].eq(channel)
    if source:
        m &= frame["source"].eq(source)
    r = frame[m].copy()
    r["t"] = pd.to_numeric(r["take_time_s"])
    return r.sort_values("t")


def audio_rows(frame, channel, start_s, dur=60.0):
    r = frame[frame["take_id"].eq("continuous_audio") & frame["channel"].eq(channel)].copy()
    r = r[(r["time_s"] >= start_s) & (r["time_s"] <= start_s + dur)]
    r["t"] = r["time_s"] - start_s
    return r.sort_values("t")


def build(args) -> dict:
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    raw = pd.read_csv(args.session_csv, low_memory=False)
    if not is_synthetic(raw):
        raise SystemExit("refusing to build: the session CSV is not entirely data_class=synthetic")
    frame = load_observations(Path(args.session_csv).read_bytes())
    start_s = float(frame[frame["take_id"].eq(TAKE)]["time_s"].sub(frame[frame["take_id"].eq(TAKE)]["take_time_s"]).median())

    # ---- synthetic session panels (same layout the page already draws)
    hr = take_rows(frame, "h10_raw_ecg_rr_bpm")
    hr = hr[hr["t"] <= 60]
    rgb = {n: take_rows(frame, f"camera_mean_{n}") for n in ("red", "green", "blue")}
    session = {
        "title": "Synthetic session · Recovery 1",
        "duration_s": 60,
        "heart_rate_reference": pts(hr["t"], hr["value"]),
        "rgb_channel_means": {**{n: pts(r["t"].iloc[::15], r["value"].iloc[::15]) for n, r in rgb.items()},
                              "normalisation": "Synthetic display-model channels; each may be viewed relative to its own take mean."},
        "estimator_rates": {
            "CHROM blind estimate": pts(*[take_rows(frame, "chrom_blind_winner_bpm")[c] for c in ("t", "value")]),
            "POS blind estimate": pts(*[take_rows(frame, "pos_blind_winner_bpm")[c] for c in ("t", "value")]),
            "Y blind estimate": pts(*[take_rows(frame, "y_blind_winner_bpm")[c] for c in ("t", "value")]),
            "Synthetic RR-derived reference": pts(hr["t"], hr["value"]),
        },
        "acoustic_features": {
            label: pts(*[audio_rows(frame, ch, start_s)[c] for c in ("t", "value")])
            for label, ch in (("Band RMS channel 1", "pcg_band_rms_20_400hz_ch1"), ("Band RMS channel 2", "pcg_band_rms_20_400hz_ch2"),
                              ("Reference-blind dominant spectral component", "pcg_dominant_event_rate"),
                              ("Second-ranked reference-blind spectral component", "pcg_secondary_event_rate"),
                              ("Reference-guided cardiac-rate-near candidate", "pcg_cardio_near_candidate"))},
        "claims": ["Every trace in this panel is generated; none is a participant recording.",
                   "RGB values are a generic channel-modulation display model, not a validated skin, camera or optical model.",
                   "The estimator rates are the repository's real CHROM/POS/Y code applied to the synthetic RGB traces.",
                   "Acoustic features come from a synthetic heart-sound envelope."],
    }

    # ---- 30 s context -> 30 s hold-out, on the synthetic series
    hold = prepare_holdout(frame, SERIES, TAKE)
    ctx = hold["context_frame"]
    tfm = forecast_bpm(ctx, [SERIES], horizon=30, context_points=30)  # real TimesFM-3 on the synthetic context
    base = reference_baselines(ctx)
    fut = hold["future_actual"].copy()
    scored = {"timesfm": score_point_forecast(tfm, fut)[1],
              "persistence": score_point_forecast(base["persistence"], fut)[1],
              "linear_trend": score_point_forecast(base["linear_trend"], fut)[1]}

    cands = pd.read_csv(args.pulse_candidates, low_memory=False)
    sigma = float(pd.to_numeric(cands["conditioning_sigma_bpm"], errors="coerce").dropna().unique()[0])
    mech = condition_pulse_ensemble(ctx, cands[cands["take_id"].astype(str).eq(TAKE)], observation_sigma_bpm=sigma)
    ms = mech["summary"]
    scored["pulse_hr_constrained_projection"] = score_point_forecast(
        ms.rename(columns={"median": "value"})[["time_s", "value"]], fut)[1]

    forecast = {
        "origin_s": 30,
        "context": pts(ctx["time_s"], ctx["value"]),
        "held_out_observation": pts(fut["plot_time_s"], fut["value"]),
        "timesfm": [[round(float(t), 3), round(float(v), 6), round(float(lo), 6), round(float(hi), 6)]
                    for t, v, lo, hi in zip(tfm["time_s"], tfm["value"], tfm["low_80"], tfm["high_80"])],
        "timesfm_status": "TimesFM-3 run offline on the synthetic 30 s context (30 one-second samples only); the held-out synthetic future was not passed to it.",
        "baselines": {k: pts(v["time_s"], v["value"]) for k, v in base.items()},
        "metrics": scored,
    }
    mechanistic = {
        "origin_s": 30,
        "forecast": [[round(float(t), 3), round(float(m), 6), round(float(lo), 6), round(float(hi), 6)]
                     for t, m, lo, hi in zip(ms["time_s"], ms["median"], ms["low_80"], ms["high_80"])],
        "candidate_count": mech["member_count"],
        "effective_sample_size": round(mech["effective_sample_size"], 3),
        "best_context_rmse_bpm": round(mech["best_conditioning_rmse_bpm"], 3),
        "conditioning_sigma_bpm": sigma,
        "conditioning_times_s": mech["conditioning_times_s"],
        "candidate_family": {"pulse_version": "4.3.2", "baseline": "StandardMale baseline parameterization; no participant-specific modifiers",
                             "exercise_intensity_fraction": [0.05, 0.1, 0.15, 0.2, 0.25, 0.3], "exercise_duration_s": [30, 45, 60],
                             "cessation_to_origin_delay_s": [0, 5, 10, 15], "additional_recovery_parameters_varied": [], "prior": "equal"},
        "label": "Pulse HR-constrained projection for the synthetic scenario; not an individualized state estimate",
        "held_out_data_used_for_conditioning": False,
    }
    model = json.loads(Path(args.model_episode).read_text(encoding="utf-8"))
    model = {k: model[k] for k in ("title", "time_basis", "state", "optical_forward_model_status")}

    return {
        "bundle_id": "synthetic-multimodal-demo-site-v2",
        "data_class": "synthetic",
        "participant_data": False,
        "badge": spec["badge"],
        "banner": spec["banner"],
        "rgb_disclaimer": spec["rgb_disclaimer"],
        "synthetic_session": session,
        "forecast_comparison": forecast,
        "mechanistic_projection": mechanistic,
        "model_episode": model,
        "research_results": spec["research_results"],
        "provenance": {
            "bundle_type": "precomputed synthetic demonstration",
            "schema": SCHEMA,
            "seed": spec["seed"],
            "time_handling": "Synthetic times in seconds from the synthetic take start; the model cycle uses its own phase coordinate.",
            "timesfm_runtime_required": False,
            "pulse_runtime_required": False,
            "forecast_model": "TimesFM-3, run offline on synthetic input",
            "mechanistic_engine": "Pulse 4.3.2 (frozen StandardMale baseline), run offline; OpenBF outputs in the separate model-cycle example",
        },
    }


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("session-csv", "pulse-candidates", "model-episode", "spec"):
        p.add_argument(f"--{name}", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    args = p.parse_args(argv)
    bundle = build(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(bundle, indent=1, allow_nan=False) + "\n"
    (args.output_dir / "demo.json").write_text(text, encoding="utf-8")
    manifest = {"bundle_id": bundle["bundle_id"], "schema": SCHEMA, "data_class": "synthetic", "participant_data": False,
                "description": "Fully synthetic session, TimesFM-3 and Pulse outputs computed offline on that synthetic input, and a separate Pulse/OpenBF model cycle.",
                "seed": bundle["provenance"]["seed"], "public_payload_sha256": hashlib.sha256(text.encode()).hexdigest()}
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output_dir / 'demo.json'} ({len(text) // 1024} KiB)")


if __name__ == "__main__":
    main()
