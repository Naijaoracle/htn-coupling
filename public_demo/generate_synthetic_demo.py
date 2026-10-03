#!/usr/bin/env python3
"""Generate the public, fully synthetic digital-patient demonstration bundle.

Privacy boundary: this generator has no input-dataset argument and reads no
research recording. Its only inputs are an explicit synthetic specification and
the seed it contains. The CHROM/POS/Y estimator code is the repository's real
implementation, applied to synthetic RGB traces.

    python generate_synthetic_demo.py --spec synthetic_demo_spec.json --output synthetic_demo.json
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

GENERATOR_VERSION = "1.0.0"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "multimodal_demo_next"))
from harmonize_six_take_research import _rgb_projection_peaks  # noqa: E402  (real estimator; module reads no data on import)


def _series(name, unit, source, stage, fs, values, **extra):
    return {"name": name, "unit": unit, "source": source, "processing_stage": stage,
            "sample_rate_hz": fs, "t0_s": 0.0,
            "values": [round(float(v), 4) for v in values], **extra}


def synthetic_hr(spec, rng):
    h, dur = spec["hr"], spec["duration_s"]
    t = np.arange(0, dur + 1e-9, 1.0 / h_fs(spec))
    latent = h["hr_inf_bpm"] + (h["hr0_bpm"] - h["hr_inf_bpm"]) * np.exp(-t / h["tau_s"])
    eps = np.zeros_like(t)
    innov = rng.normal(0, h["noise_sd_bpm"] * np.sqrt(1 - h["noise_ar1"] ** 2), len(t))
    for i in range(1, len(t)):
        eps[i] = h["noise_ar1"] * eps[i - 1] + innov[i]
    return t, latent, latent + eps


def h_fs(spec):
    return spec["sampling_hz"]["hr"]


def beat_times(spec, t_hr, hr, rng):
    """Beat onsets whose RR intervals follow the synthetic HR trajectory."""
    dur, jit = spec["duration_s"], spec["hr"]["rr_jitter_sd_s"]
    beats, now = [], 0.3
    while now < dur + 1.0:
        beats.append(now)
        now += 60.0 / np.interp(now, t_hr, hr) + rng.normal(0, jit)
    return np.array(beats)


def _bump(t, centre, width):
    return np.exp(-0.5 * ((t - centre) / width) ** 2)


def ecg_like(spec, beats, rng):
    fs, dur, c = spec["sampling_hz"]["ecg_like"], spec["duration_s"], spec["ecg_like"]
    t = np.arange(0, dur, 1.0 / fs)
    y = np.zeros_like(t)
    for b in beats:  # generic P-QRS-T template, display only
        for off, amp, w in ((-0.18, 0.12, 0.025), (-0.03, -0.12, 0.010), (0.0, 1.0, 0.012),
                            (0.03, -0.25, 0.010), (0.26, 0.30, 0.045)):
            y += amp * _bump(t, b + off, w)
    y += c["baseline_wander_amp"] * np.sin(2 * np.pi * c["baseline_wander_hz"] * t + rng.uniform(0, 2 * np.pi))
    return t, y + rng.normal(0, c["noise_sd"], len(t))


def pulse_wave(t, beats, delay_s):
    """Generic pulse shape: sharp systolic upstroke plus a smaller dicrotic bump."""
    p = np.zeros_like(t)
    for b in beats:
        p += _bump(t, b + delay_s + 0.12, 0.07) + 0.35 * _bump(t, b + delay_s + 0.34, 0.09)
    return p


def ppg_like(spec, beats, rng):
    fs, dur, c = spec["sampling_hz"]["ppg_like"], spec["duration_s"], spec["ppg_like"]
    t = np.arange(0, dur, 1.0 / fs)
    return t, c["amplitude"] * pulse_wave(t, beats, c["delay_s"]) + rng.normal(0, c["noise_sd"], len(t))


def rgb_display(spec, beats, rng):
    fs, dur, m = spec["sampling_hz"]["rgb"], spec["duration_s"], spec["rgb_display_model"]
    t = np.arange(0, dur, 1.0 / fs)
    p = pulse_wave(t, beats, spec["ppg_like"]["delay_s"])
    p = p - p.mean()
    drift = m["drift_amp"] * np.sin(2 * np.pi * m["drift_hz"] * t + rng.uniform(0, 2 * np.pi))
    return t, {ch: m["baseline"][ch] + m["pulse_gain"][ch] * p + drift + rng.normal(0, m["noise_sd"][ch], len(t))
               for ch in "rgb"}


def acoustic_envelope(spec, beats, t_hr, hr, rng):
    fs, dur, c = spec["sampling_hz"]["acoustic_envelope"], spec["duration_s"], spec["acoustic_envelope"]
    t = np.arange(0, dur, 1.0 / fs)
    y = np.zeros_like(t)
    for b in beats:
        rr = 60.0 / np.interp(b, t_hr, hr)
        y += _bump(t, b, c["s1_width_s"]) + 0.6 * _bump(t, b + c["s2_fraction_of_rr"] * rr, c["s2_width_s"])
    return t, np.abs(y + rng.normal(0, c["noise_sd"], len(t)))


def rppg_estimates(spec, t, rgb):
    """Run the repository's real Y/POS/CHROM estimator on the synthetic RGB traces."""
    stats = [{"wall_ms": float(ti) * 1000.0, "mean_r": rgb["r"][i], "mean_g": rgb["g"][i],
              "mean_b": rgb["b"][i], "mean_y": 0.299 * rgb["r"][i] + 0.587 * rgb["g"][i] + 0.114 * rgb["b"][i]}
             for i, ti in enumerate(t)]
    rows = _rgb_projection_peaks(stats, 0.0, spec["duration_s"] * 1000.0, spec["scenario"])
    out = {}
    for r in rows:
        name = r["channel"].replace("_blind_winner_bpm", "")
        out.setdefault(name, []).append([round(float(r["time_s"]), 3), round(float(r["value"]), 3)])
    return out


def forecast_block(spec, t_hr, observed, rng):
    f, h = spec["forecast"], spec["hr"]
    cut = f["context_end_s"]
    ctx = t_hr <= cut
    fut_t = t_hr[~ctx]
    last = float(observed[ctx][-1])
    win = ctx & (t_hr > cut - f["linear_fit_window_s"])
    slope, intercept = np.polyfit(t_hr[win], observed[win], 1)
    ml, mech = f["illustrative_ml_style"], f["illustrative_mechanistic_style"]
    drift = (last - h["hr_inf_bpm"]) * np.exp(-(fut_t - cut) / ml["damping_tau_s"])
    ml_curve = h["hr_inf_bpm"] + drift + rng.normal(0, ml["wiggle_sd_bpm"], len(fut_t))
    mech_curve = mech["assumed_hr_inf_bpm"] + (last - mech["assumed_hr_inf_bpm"]) * np.exp(-(fut_t - cut) / mech["assumed_tau_s"])
    r = lambda a: [round(float(x), 3) for x in a]  # noqa: E731
    return {
        "context_end_s": cut,
        "future_time_s": r(fut_t),
        "synthetic_observed_future": r(observed[~ctx]),
        "branches": [
            {"name": "persistence", "kind": "baseline_computed_from_synthetic_context", "values": r(np.full(len(fut_t), last))},
            {"name": "linear_trend", "kind": "baseline_computed_from_synthetic_context", "values": r(slope * fut_t + intercept)},
            {"name": "synthetic_ml_style", "kind": "illustrative_curve_not_model_output",
             "values": r(ml_curve), "band_bpm": ml["band_bpm"]},
            {"name": "synthetic_mechanistic_style", "kind": "illustrative_curve_not_model_output", "values": r(mech_curve)},
        ],
        "notice": "No TimesFM or Pulse model was run. The two illustrative curves exist only to demonstrate the interface and are not scored.",
    }


def build(spec: dict) -> dict:
    rng = np.random.default_rng(spec["seed"])
    t_hr, latent, observed = synthetic_hr(spec, rng)
    beats = beat_times(spec, t_hr, observed, rng)
    sg, disp = "synthetic_generator", "synthetic_observation"
    _, ecg = ecg_like(spec, beats, rng)
    _, ppg = ppg_like(spec, beats, rng)
    t_rgb, rgb = rgb_display(spec, beats, rng)
    _, aco = acoustic_envelope(spec, beats, t_hr, observed, rng)
    fs = spec["sampling_hz"]
    signals = [
        _series("synthetic_latent_hr", "bpm", sg, "synthetic_latent_state", fs["hr"], latent),
        _series("synthetic_hr", "bpm", sg, disp, fs["hr"], observed),
        _series("ecg_like", "a.u.", "generic_ecg_template_display_model", disp, fs["ecg_like"], ecg,
                validated_forward_model=False),
        _series("ppg_like", "a.u.", "generic_pulse_shape_display_model", disp, fs["ppg_like"], ppg,
                validated_forward_model=False),
        *[_series(f"rgb_{n}", "8-bit counts", "generic_rgb_display_model", disp, fs["rgb"], rgb[c],
                  validated_forward_model=False) for c, n in (("r", "red"), ("g", "green"), ("b", "blue"))],
        _series("acoustic_envelope", "a.u.", "generic_heart_sound_envelope_display_model", disp,
                fs["acoustic_envelope"], aco, validated_forward_model=False),
    ]
    return {
        "dataset_id": spec["dataset_id"],
        "data_class": "synthetic",
        "participant_data": False,
        "generator_version": GENERATOR_VERSION,
        "seed": spec["seed"],
        "scenario": spec["scenario"],
        "duration_s": spec["duration_s"],
        "badge": spec["badge"],
        "banner": spec["banner"],
        "rgb_disclaimer": spec["rgb_disclaimer"],
        "signals": signals,
        "rppg_estimates": {
            "source": "repository_real_estimator_on_synthetic_rgb",
            "method_window_s": 12.0,
            "series_bpm": rppg_estimates(spec, t_rgb, rgb),
        },
        "forecast": forecast_block(spec, t_hr, observed, rng),
        "research_results": spec["research_results"],
    }


EXCHANGE_COLUMNS = ["time_s", "channel", "value", "unit", "layer", "source", "scenario", "episode_id",
                    "episode_relationship", "clock_provenance", "alignment_status", "processing_stage",
                    "model_version", "validated_forward_model"]


def exchange_rows(bundle: dict) -> list[dict]:
    """Flatten the synthetic bundle into the dashboard's long-form exchange table.

    Layers stay honest: display-model signals are `synthetic_observation`, never
    `sensor`; estimator outputs are `estimate`; the illustrative curves are
    `forecast` rows whose source says they are not model output.
    """
    scen = bundle["scenario"]
    common = {"scenario": scen, "episode_id": scen, "episode_relationship": "same_episode",
              "clock_provenance": "synthetic generator clock; seconds from episode start", "alignment_status": "master_clock",
              "model_version": f"synthetic_generator_{bundle['generator_version']}"}
    rows = []
    for s in bundle["signals"]:
        layer = "latent" if s["processing_stage"] == "synthetic_latent_state" else "synthetic_observation"
        for i, v in enumerate(s["values"]):
            rows.append({**common, "time_s": round(i / s["sample_rate_hz"], 4), "channel": s["name"], "value": v,
                         "unit": s["unit"], "layer": layer, "source": s["source"],
                         "processing_stage": s["processing_stage"],
                         "validated_forward_model": s.get("validated_forward_model", "")})
    for method, pts in bundle["rppg_estimates"]["series_bpm"].items():
        for t, v in pts:
            rows.append({**common, "time_s": t, "channel": f"{method}_blind_winner_bpm", "value": v, "unit": "bpm",
                         "layer": "estimate", "source": f"synthetic_rgb_{method.upper()}_12s_Welch_blind",
                         "processing_stage": "estimate_from_synthetic_rgb", "validated_forward_model": False})
    fc = bundle["forecast"]
    for b in fc["branches"]:
        for t, v in zip(fc["future_time_s"], b["values"]):
            rows.append({**common, "time_s": t, "channel": f"{b['name']}_hr", "value": v, "unit": "bpm",
                         "layer": "forecast", "source": f"synthetic_{b['kind']}",
                         "processing_stage": "forecast_synthetic_input", "validated_forward_model": False})
    return rows


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--spec", type=Path, required=True, help="synthetic specification JSON")
    parser.add_argument("--output", type=Path, required=True, help="output synthetic_demo.json")
    parser.add_argument("--exchange-csv", type=Path, help="optional output: dashboard exchange-format CSV of the same synthetic bundle")
    args = parser.parse_args(argv)
    payload = build(json.loads(args.spec.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=1, allow_nan=False) + "\n"
    args.output.write_text(text, encoding="utf-8")
    if args.exchange_csv:
        args.exchange_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.exchange_csv.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=EXCHANGE_COLUMNS)
            w.writeheader()
            w.writerows(exchange_rows(payload))
        print(f"wrote {args.exchange_csv}")
    manifest = {
        "dataset_id": payload["dataset_id"], "data_class": "synthetic", "participant_data": False,
        "generator_version": GENERATOR_VERSION, "seed": payload["seed"],
        "spec_sha256": hashlib.sha256(args.spec.read_bytes()).hexdigest(),
        "payload_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }
    (args.output.parent / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output} ({len(text) // 1024} KiB)")


if __name__ == "__main__":
    main()
