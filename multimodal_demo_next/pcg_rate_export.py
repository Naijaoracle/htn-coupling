"""Offline extraction of acoustic envelope rate features for the exchange CSV.

The WAV is read by this batch utility only. It is never embedded or served by
the dashboard; the output contains numeric rate features and provenance only.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import wavfile
from scipy.signal import butter, find_peaks, hilbert, resample_poly, sosfiltfilt, welch


RATE_WINDOW_S = 30.0
ENVELOPE_FS_HZ = 500.0
WELCH_NPERSEG = 8192
RATE_BAND_BPM = (30.0, 300.0)
H10_NEAR_TOLERANCE_BPM = 12.0
MIN_PEAK_SEPARATION_BPM = 8.0


def _read_wav_as_float(path: str | Path) -> tuple[int, np.ndarray]:
    fs, samples = wavfile.read(path)
    x = np.asarray(samples)
    if x.ndim == 1:
        x = x[:, None]
    if np.issubdtype(x.dtype, np.integer):
        info = np.iinfo(x.dtype)
        scale = float(max(abs(info.min), info.max))
        x = x.astype(np.float64) / scale
    else:
        x = x.astype(np.float64)
    if x.shape[0] < int(fs * RATE_WINDOW_S):
        raise ValueError("WAV is shorter than the 30-second rate-analysis window")
    return int(fs), x


def _envelope_500hz(signal: np.ndarray, fs: int) -> np.ndarray:
    x = signal - np.mean(signal)
    band = butter(4, [20.0, 200.0], btype="bandpass", fs=fs, output="sos")
    notch = butter(4, [48.0, 52.0], btype="bandstop", fs=fs, output="sos")
    filtered = sosfiltfilt(notch, sosfiltfilt(band, x))
    envelope = np.abs(hilbert(filtered))
    # Rational resampling keeps the rate-band Welch computation manageable.
    from fractions import Fraction

    ratio = Fraction(ENVELOPE_FS_HZ / fs).limit_denominator(10000)
    return resample_poly(envelope, ratio.numerator, ratio.denominator)


def _ranked_rate_peaks(envelope: np.ndarray) -> list[tuple[float, float]]:
    f, power = welch(
        envelope,
        fs=ENVELOPE_FS_HZ,
        window="hann",
        nperseg=min(WELCH_NPERSEG, len(envelope)),
        noverlap=min(WELCH_NPERSEG // 2, len(envelope) // 2),
        detrend="constant",
    )
    band = (f >= RATE_BAND_BPM[0] / 60.0) & (f <= RATE_BAND_BPM[1] / 60.0)
    indices = np.flatnonzero(band)
    if len(indices) < 3:
        return []
    local, _ = find_peaks(power[band])
    ranked = sorted(local, key=lambda i: power[indices[i]], reverse=True)
    chosen: list[tuple[float, float]] = []
    for peak_idx in ranked:
        rate = float(f[indices[peak_idx]] * 60.0)
        if any(abs(rate - prior[0]) < MIN_PEAK_SEPARATION_BPM for prior in chosen):
            continue
        chosen.append((rate, float(power[indices[peak_idx]])))
        if len(chosen) >= 8:
            break
    return chosen


def _h10_local_median(h10: pd.DataFrame, time_s: float) -> float | None:
    if h10.empty:
        return None
    # Match the trailing acoustic window; do not use future H10 samples.
    local = h10[h10["time_s"].between(time_s - RATE_WINDOW_S, time_s)]
    if local.empty:
        return None
    return float(local["value"].median())


def derive_pcg_rate_rows(wav_path: str | Path, timeline: pd.DataFrame) -> pd.DataFrame:
    """Create blind dominant/secondary and H10-guided diagnostic rate rows.

    The 30-second trailing windows are stepped once per second. The acoustic
    candidate near H10 is reference-informed and stored as a diagnostic field.
    """
    time_col = "time_s"
    audio = timeline[
        timeline["channel"].astype(str).eq("pcg_band_rms_20_400hz_ch1")
    ].copy()
    if audio.empty:
        raise ValueError("Timeline CSV has no channel-1 PCG RMS timestamps for alignment")
    audio[time_col] = pd.to_numeric(audio[time_col], errors="coerce")
    audio = audio.dropna(subset=[time_col]).sort_values(time_col)
    audio_origin = float(audio.iloc[0][time_col])

    fs, samples = _read_wav_as_float(wav_path)
    # The stereo channels are highly concordant in the supplied recording;
    # averaging preserves the shared acoustic signal and avoids duplicate rows.
    mono = samples.mean(axis=1)
    envelope = _envelope_500hz(mono, fs)
    samples_per_sec = int(round(ENVELOPE_FS_HZ))
    window_n = int(round(RATE_WINDOW_S * ENVELOPE_FS_HZ))

    h10 = timeline[
        timeline["source"].astype(str).str.contains("H10", case=False, na=False)
        & timeline["unit"].astype(str).str.lower().isin(["bpm", "beats/min", "beat/min"])
    ][["time_s", "value"]].copy()
    h10["time_s"] = pd.to_numeric(h10["time_s"], errors="coerce")
    h10["value"] = pd.to_numeric(h10["value"], errors="coerce")
    h10 = h10.dropna().sort_values("time_s")

    template = audio.iloc[0].to_dict()
    rows: list[dict] = []
    first_end_s = int(np.ceil(RATE_WINDOW_S))
    last_end_s = min(int(len(envelope) // samples_per_sec), int(np.floor(len(samples) / fs)))
    for end_s in range(first_end_s, last_end_s + 1):
        end_idx = min(len(envelope), end_s * samples_per_sec)
        start_idx = end_idx - window_n
        if start_idx < 0 or end_idx > len(envelope):
            continue
        segment = envelope[start_idx:end_idx]
        if len(segment) < window_n:
            continue
        time_s = audio_origin + end_s
        peaks = _ranked_rate_peaks(segment)
        if not peaks:
            continue
        h10_rate = _h10_local_median(h10, time_s)
        dominant = peaks[0]
        secondary = peaks[1] if len(peaks) > 1 else None
        near = None
        if h10_rate is not None:
            eligible = [p for p in peaks if abs(p[0] - h10_rate) <= H10_NEAR_TOLERANCE_BPM]
            if eligible:
                near = max(eligible, key=lambda p: p[1])

        common = dict(template)
        common.update({
            "time_s": time_s,
            "unit": "events/min",
            "source": "PCG_20-200Hz_envelope_Welch_30s",
            "take_id": "continuous_audio",
            "take_time_s": np.nan,
            "protocol_time_s": time_s - 319.277,
            "phase": "continuous_audio",
            "alignment_status": "derived_alignment",
            "alignment_method": (
                "30 s trailing envelope Welch window, 1 s step; time origin inherited from "
                "audio RMS export; WAV start based on file metadata; no shared hardware marker"
            ),
            "model_version": "PCG_rate_screen_v1",
            "processing_stage": "offline_derived_acoustic_rate_feature",
            "derived_from": "external acoustic source WAV; audio samples not included in exchange output",
        })
        for channel, source, value in (
            ("pcg_dominant_event_rate", "PCG_reference_blind_20-200Hz_envelope_Welch_30s", dominant[0]),
            ("pcg_secondary_event_rate", "PCG_reference_blind_20-200Hz_envelope_Welch_30s", secondary[0] if secondary else np.nan),
            ("pcg_cardio_near_candidate", "PCG_H10_guided_diagnostic_20-200Hz_envelope_Welch_30s", near[0] if near else np.nan),
        ):
            if pd.isna(value):
                continue
            row = dict(common)
            row.update({"channel": channel, "source": source, "layer": "estimate", "value": float(value)})
            rows.append(row)
    return pd.DataFrame(rows)


def augment_timeline(wav_path: str | Path, timeline_path: str | Path, output_path: str | Path) -> int:
    timeline = pd.read_csv(timeline_path)
    added = derive_pcg_rate_rows(wav_path, timeline)
    combined = pd.concat([timeline, added], ignore_index=True)
    combined.to_csv(output_path, index=False)
    return len(added)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wav", required=True, type=Path, help="Local WAV source; not copied to output")
    parser.add_argument("--timeline", required=True, type=Path, help="Existing exchange-format CSV")
    parser.add_argument("--output", required=True, type=Path, help="Augmented exchange CSV with derived rates")
    args = parser.parse_args()
    count = augment_timeline(args.wav, args.timeline, args.output)
    print(f"Wrote {args.output} with {count} derived PCG rate rows; raw WAV was not copied.")


if __name__ == "__main__":
    main()
