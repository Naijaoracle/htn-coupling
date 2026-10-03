#!/usr/bin/env python3
"""Generate a fully synthetic dashboard exchange CSV that mirrors the research-session schema.

The column set, take structure, channel names, units, sampling rates and estimator
windows follow the structure of the research exchange table, so every dashboard panel
can be exercised. No value is read from or derived from any recording: the only input
is a synthetic specification (with its seed).

Honest labelling on disk: every row has data_class="synthetic", sources carry the
"SYNTH:" prefix, sensor-domain rows use layer="synthetic_observation", and the
Pulse-role latent rows are illustrative curves, not Pulse output.

    python generate_synthetic_session_csv.py --spec synthetic_session_spec.json --output synthetic_session.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
from scipy import signal

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "multimodal_demo_next"))
from generate_synthetic_demo import _bump, pulse_wave  # noqa: E402
from harmonize_six_take_research import _ppg_window_peaks, _rgb_projection_peaks, _welch_peak_bpm, WINDOW_S  # noqa: E402

COLUMNS = ["time_s", "channel", "value", "unit", "layer", "source", "scenario", "episode_id", "episode_relationship",
           "clock_provenance", "alignment_status", "take_id", "take_time_s", "protocol_time_s", "phase", "alignment_method",
           "model_version", "parameterization", "processing_stage", "derived_from", "candidate_id", "exercise_intensity",
           "exercise_duration_s", "cessation_to_recovery_origin_delay_s", "conditioning_sigma_bpm", "data_class"]
GEN_VERSION = "synthetic_session_generator_1.0.0"


class Rows:
    def __init__(self, spec):
        self.spec, self.rows = spec, []

    def add(self, **kw):
        row = {c: "" for c in COLUMNS}
        row.update(scenario=self.spec["scenario"], model_version="synthetic_generator", parameterization="not_applicable",
                   derived_from="synthetic generator specification; no recorded data", data_class="synthetic",
                   episode_relationship="same_episode", alignment_status="master_clock",
                   clock_provenance="synthetic generator clock; seconds from session start", alignment_method="not_applicable_synthetic")
        row.update(kw)
        row["source"] = self.spec["source_prefix"] + row["source"]
        if not row["episode_id"]:
            row["episode_id"] = row["take_id"] or self.spec["scenario"]
        self.rows.append(row)


def session_hr(spec, t, rng):
    """Latent session HR: baseline plus ramp-and-decay contributions of three synthetic bouts."""
    hr = np.full_like(t, spec["baseline_hr_bpm"], dtype=float)
    for b in spec["bouts"]:
        amp, T, ramp = b["peak_bpm"] - spec["baseline_hr_bpm"], b["cessation_s"], spec["ramp_s"]
        up = (t >= T - ramp) & (t < T)
        hr[up] += amp * (t[up] - (T - ramp)) / ramp
        after = t >= T
        hr[after] += amp * np.exp(-(t[after] - T) / b["tau_s"])
    eps = np.zeros_like(t)
    innov = rng.normal(0, spec["hr_noise_sd_bpm"] * np.sqrt(1 - spec["hr_noise_ar1"] ** 2), len(t))
    for i in range(1, len(t)):
        eps[i] = spec["hr_noise_ar1"] * eps[i - 1] + innov[i]
    return hr + eps


def beat_times(spec, rng, grid_t, grid_hr):
    lo, hi = spec["session_span_s"]["h10_beats"]
    beats, now = [], lo + 0.3
    while now < hi:
        beats.append(now)
        now += 60.0 / np.interp(now, grid_t, grid_hr) + rng.normal(0, spec["rr_jitter_sd_s"])
    return np.array(beats)


def ecg_trace(t, beats):
    y = np.zeros_like(t)
    for b in beats[(beats > t[0] - 1) & (beats < t[-1] + 1)]:
        m = np.abs(t - b) < 0.6
        for off, amp, w in ((-0.18, 0.12, 0.025), (-0.03, -0.12, 0.010), (0.0, 1.0, 0.012), (0.03, -0.25, 0.010), (0.26, 0.30, 0.045)):
            y[m] += amp * _bump(t[m], b + off, w)
    return y


def phase_at(t, spec):
    first_bout = min(b["cessation_s"] for b in spec["bouts"]) - spec["ramp_s"]
    rec1 = spec["takes"]["recovery_1"]["start_s"]
    if t < spec["session_span_s"]["continuous"][0] + 14.0 and t < 0:
        return "pre_capture"
    if t > spec["takes"]["recovery_3"]["start_s"] + spec["take_duration_s"]:
        return "post_capture"
    if t < first_bout:
        return "rest_or_between_rest_takes"
    if t < rec1:
        return "exercise_and_setup_transition_exact_times_unknown"
    return "recovery_or_between_recovery_takes"


def build(spec: dict) -> list[dict]:
    rng = np.random.default_rng(spec["seed"])
    out, proto = Rows(spec), spec["protocol_origin_s"]
    lo, hi = spec["session_span_s"]["h10_beats"]
    grid_t = np.arange(lo - 2, hi + 2, 0.5)
    grid_hr = session_hr(spec, grid_t, rng)
    beats = beat_times(spec, rng, grid_t, grid_hr)
    rates = spec["rates_hz"]

    # ---- continuous 25 Hz channels (ESP32-role stream)
    c0, c1 = spec["session_span_s"]["continuous"]
    n = int(round((c1 - c0) * rates["continuous"]))
    tc = c0 + np.arange(n) / rates["continuous"]
    hi_t = c0 + np.arange(int((c1 - c0) * rates["ecg_internal"])) / rates["ecg_internal"]
    ecg = ecg_trace(hi_t, beats)[:: rates["ecg_internal"] // rates["continuous"]][:n]
    ecg_adc = spec["ecg"]["adc_baseline"] + spec["ecg"]["adc_gain"] * ecg + rng.normal(0, spec["ecg"]["noise_sd"] * spec["ecg"]["adc_gain"], n)
    m = spec["max30102"]
    pw = pulse_wave(tc, beats, m["delay_s"])
    ir = m["ir_baseline"] + m["ir_gain"] * pw + rng.normal(0, m["noise_sd"], n)
    red = m["red_baseline"] + m["red_gain"] * pw + rng.normal(0, m["noise_sd"], n)
    cont = dict(take_id="continuous_ESP32", alignment_status="shared_clock")
    for name, src, unit, vals, stage in (
            ("ad8232_ecg_raw_continuous_25hz", "AD8232_ESP32", "ADC counts", ecg_adc, "raw_acquisition_display_downsampled_25Hz"),
            ("max_ir_raw_continuous", "MAX30102_IR", "a.u.", ir, "sensor_fifo_sample_median_binned_25Hz"),
            ("max_red_raw_continuous", "MAX30102_RED", "a.u.", red, "sensor_fifo_sample_median_binned_25Hz")):
        for t, v in zip(tc, vals):
            out.add(time_s=round(float(t), 4), channel=name, value=round(float(v), 3), unit=unit, layer="synthetic_observation",
                    source=src, protocol_time_s=round(float(t - proto), 4), phase=phase_at(t, spec), processing_stage=stage,
                    model_version="not_applicable_synthetic_display_signal", **cont)

    # ---- acoustic channels (audio-role stream)
    ta = c0 + np.arange(int((c1 - c0) * rates["acoustic_internal"])) / rates["acoustic_internal"]
    aco = np.zeros_like(ta)
    for b in beats[(beats > c0 - 1) & (beats < c1 + 1)]:
        rr = 60.0 / np.interp(b, grid_t, grid_hr)
        mk = np.abs(ta - b) < 0.8
        aco[mk] += _bump(ta[mk], b, 0.03) + 0.6 * _bump(ta[mk], b + 0.35 * rr, 0.025)
    aco = np.abs(aco + rng.normal(0, 0.02, len(ta)))
    k = rates["acoustic_internal"]
    secs = len(ta) // k
    rms = np.sqrt((aco[: secs * k].reshape(secs, k) ** 2).mean(axis=1))
    rms = rms / rms.max()
    t_rms = -13.0 + np.arange(secs)
    aud = dict(take_id="continuous_audio", alignment_status="derived_alignment")
    for ch, gain in (("pcg_band_rms_20_400hz_ch1", 1.0), ("pcg_band_rms_20_400hz_ch2", spec["pcg"]["ch2_gain"])):
        vals = gain * rms + rng.normal(0, 0.01, secs)
        for t, v in zip(t_rms, vals):
            out.add(time_s=round(float(t), 4), channel=ch, value=round(float(v), 5), unit="normalized_rms", layer="synthetic_observation",
                    source="BOYA_BY_M1_through_stethoscope_tubing", protocol_time_s=round(float(t - proto), 4), phase=phase_at(t, spec),
                    processing_stage="processed_observation_1s_band_energy_envelope", **aud)
    # trailing 30 s Welch on the synthetic envelope: dominant, second-ranked, and nearest-to-latent-HR peaks
    w = int(spec["pcg"]["window_s"] * k)
    for end in np.arange(spec["pcg"]["start_s"], spec["pcg"]["stop_s"] + 1e-6, 1.0):
        i1 = int((end - c0) * k)
        if i1 - w < 0 or i1 > len(aco):
            continue
        f, p = signal.welch(aco[i1 - w:i1], fs=k, nperseg=min(w, 512), detrend="linear")
        band = (f >= 0.5) & (f <= 3.5)
        pk, _ = signal.find_peaks(p[band])
        if len(pk) < 2:
            continue
        order = pk[np.argsort(p[band][pk])[::-1]]
        rates_bpm = 60.0 * f[band]
        hr_now = float(np.interp(end, grid_t, grid_hr))
        near = pk[np.argmin(np.abs(rates_bpm[pk] - hr_now))]
        for ch, idx, src, stage in (
                ("pcg_dominant_event_rate", order[0], "PCG_reference_blind_20-200Hz_envelope_Welch_30s", "offline_derived_acoustic_rate_feature"),
                ("pcg_secondary_event_rate", order[1], "PCG_reference_blind_20-200Hz_envelope_Welch_30s", "offline_derived_acoustic_rate_feature"),
                ("pcg_cardio_near_candidate", near, "PCG_H10_guided_diagnostic_20-200Hz_envelope_Welch_30s", "offline_derived_acoustic_rate_feature")):
            out.add(time_s=round(float(end), 4), channel=ch, value=round(float(rates_bpm[idx]), 3), unit="events/min", layer="estimate",
                    source=src, protocol_time_s=round(float(end - proto), 4), phase=phase_at(end, spec), processing_stage=stage,
                    model_version="synthetic_rate_screen", **aud)

    # ---- H10-role beat-to-beat rate estimates
    def rr_rows(b, take, start, label_src, channel, stage, relative):
        rr = np.diff(b)
        for t, r in zip(b[1:], rr):
            kw = dict(take_id=take, protocol_time_s=round(float(t - proto), 4), phase=phase_at(t, spec),
                      alignment_status="wall_time_aligned")
            if relative:
                kw["take_time_s"] = round(float(t - start), 4)
                kw["phase"] = spec["takes"][take]["phase"]
            out.add(time_s=round(float(t), 4), channel=channel, value=round(float(60.0 / r), 3), unit="bpm", layer="estimate",
                    source=label_src, processing_stage=stage, model_version="not_applicable_synthetic_display_signal", **kw)
    rr_rows(beats, "continuous_H10", 0.0, "H10_raw_ECG_fixed_5-25Hz_RR_continuous", "h10_continuous_rr_bpm", "fixed_raw_ECG_RR_estimator", False)
    for take, tk in spec["takes"].items():
        s = tk["start_s"]
        b = beats[(beats >= s) & (beats <= s + spec["take_duration_s"])]
        rr_rows(b, take, s, "H10_raw_ECG_fixed_5-25Hz_RR", "h10_raw_ecg_rr_bpm", "fixed_raw_ECG_RR_estimator", True)

    # ---- per-take iPad-role RGB, with the repository's real Y/POS/CHROM and MAX Welch estimators
    nrgb = int(spec["take_duration_s"] * rates["rgb"])
    g = spec["rgb"]
    for take, tk in spec["takes"].items():
        s = tk["start_s"]
        tt = 0.2 + np.arange(nrgb) / rates["rgb"]
        p = pulse_wave(tt + s, beats, spec["max30102"]["delay_s"])
        p = p - p.mean()
        drift = g["drift_amp"] * np.sin(2 * np.pi * g["drift_hz"] * tt + rng.uniform(0, 2 * np.pi))
        rgb = {c: g["baseline"][c] + g["pulse_gain"][c] * p + drift + rng.normal(0, g["noise_sd"], nrgb) for c in "rgb"}
        luma = 0.299 * rgb["r"] + 0.587 * rgb["g"] + 0.114 * rgb["b"]
        mot = g["motion_recovery"] if tk["phase"] == "recovery" else g["motion_rest"]
        proxy = np.abs(np.diff(luma, prepend=luma[0])) + np.abs(rng.normal(0, mot, nrgb))
        kw = dict(take_id=take, phase=tk["phase"], protocol_time_s=0.0, processing_stage="synthetic_rgb_display_model",
                  model_version="not_applicable_synthetic_display_signal", alignment_status="master_clock")
        for ch, vals in (("camera_mean_red", rgb["r"]), ("camera_mean_green", rgb["g"]), ("camera_mean_blue", rgb["b"]),
                         ("camera_mean_luma", luma), ("camera_frame_difference_proxy", proxy)):
            for t, v in zip(tt, vals):
                kw["protocol_time_s"] = round(float(s + t - proto), 4)
                out.add(time_s=round(float(s + t), 4), channel=ch, value=round(float(v), 4), unit="a.u.", layer="synthetic_observation",
                        source="iPad8_RGB", take_time_s=round(float(t), 4), **kw)
        stats = [{"wall_ms": float(t) * 1000.0, "mean_r": rgb["r"][i], "mean_g": rgb["g"][i], "mean_b": rgb["b"][i], "mean_y": luma[i]}
                 for i, t in enumerate(tt)]
        est = _rgb_projection_peaks(stats, 0.0, spec["take_duration_s"] * 1000.0, spec["scenario"])
        sel = (tc >= s) & (tc < s + spec["take_duration_s"])
        est += _ppg_window_peaks(tc[sel] - s, red[sel], ir[sel], spec["take_duration_s"], spec["scenario"])
        for e in est:
            c = float(e["time_s"])
            out.add(time_s=round(s + c, 4), channel=e["channel"], value=round(float(e["value"]), 3), unit="bpm", layer="estimate",
                    source=e["source"], take_id=take, take_time_s=round(c, 4), protocol_time_s=round(s + c - proto, 4),
                    phase=tk["phase"], processing_stage="estimate_from_synthetic_signal",
                    model_version="not_applicable_synthetic_display_signal", alignment_status="master_clock")

    # ---- Pulse-role latent ensemble (illustrative curves, not Pulse output)
    ens = spec["ensemble"]
    for take in (t for t, v in spec["takes"].items() if v["phase"] == "recovery"):
        for inten in ens["intensities"]:
            for dur in ens["durations_s"]:
                for delay in ens["delays_s"]:
                    cid = f"pulse_exercise_i{int(round(inten * 100)):02d}_d{int(dur)}_delay{int(delay):02d}"
                    pk = spec["baseline_hr_bpm"] + ens["peak_per_intensity_bpm"] * inten * (1 + ens["peak_duration_factor_per_s"] * dur)
                    tau = ens["tau_base_s"] + ens["tau_per_duration_s"] * dur
                    for t in range(1, 61):
                        v = spec["baseline_hr_bpm"] + (pk - spec["baseline_hr_bpm"]) * np.exp(-(t + delay) / tau)
                        out.add(time_s=float(t), channel="heart_rate", value=round(float(v), 4), unit="bpm", layer="latent",
                                source="Pulse", episode_id=cid, episode_relationship="comparable_scenario",
                                clock_provenance="synthetic simulation-relative clock", alignment_status="derived_alignment",
                                take_id=take, take_time_s=float(t), phase="recovery",
                                alignment_method="protocol-relative: synthetic illustrative curve; not wall-time or same-episode alignment",
                                model_version="synthetic_illustrative_curve",
                                parameterization="synthetic illustrative parameters; no physiological model was run",
                                processing_stage="synthetic_ensemble_candidate_v1",
                                derived_from="synthetic exponential-relaxation curve; Pulse was not run", candidate_id=cid,
                                exercise_intensity=inten, exercise_duration_s=dur,
                                cessation_to_recovery_origin_delay_s=delay, conditioning_sigma_bpm=ens["conditioning_sigma_bpm"])
    return out.rows


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--spec", type=Path, required=True, help="synthetic session specification JSON")
    parser.add_argument("--output", type=Path, required=True, help="output exchange-format CSV")
    args = parser.parse_args(argv)
    rows = build(json.loads(args.spec.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {args.output} ({len(rows):,} rows)")


if __name__ == "__main__":
    main()
