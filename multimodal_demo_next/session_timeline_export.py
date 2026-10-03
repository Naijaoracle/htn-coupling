from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import signal
from scipy.io import wavfile

from data_contract import load_observations


def _records(
    times: np.ndarray,
    values: np.ndarray,
    *,
    channel: str,
    unit: str,
    layer: str,
    source: str,
    take_id: str,
    phase: str,
    clock: str,
    alignment: str,
    alignment_method: str,
    processing_stage: str,
    derived_from: str,
) -> pd.DataFrame:
    return pd.DataFrame({
        "time_s": times,
        "channel": channel,
        "value": values,
        "unit": unit,
        "layer": layer,
        "source": source,
        "scenario": "real_session_demo",
        "episode_id": "real_session_demo",
        "episode_relationship": "same_episode",
        "clock_provenance": clock,
        "alignment_status": alignment,
        "model_version": "not_applicable_recorded_signal",
        "parameterization": "not_applicable",
        "processing_stage": processing_stage,
        "derived_from": derived_from,
        "alignment_method": alignment_method,
        "take_id": take_id,
        "phase": phase,
        "take_time_s": np.nan,
        "protocol_time_s": np.nan,
    })


def _uniform_bins(times: np.ndarray, values: np.ndarray, fs: float) -> tuple[np.ndarray, np.ndarray]:
    keep = np.isfinite(times) & np.isfinite(values)
    times, values = times[keep], values[keep]
    if not len(times):
        return np.array([]), np.array([])
    bins = np.floor(times * fs).astype(np.int64)
    grouped = pd.DataFrame({"bin": bins, "value": values}).groupby("bin")["value"].median()
    return grouped.index.to_numpy(dtype=float) / fs, grouped.to_numpy(dtype=float)


def _phase_at(time_s: float, bounds: dict[str, float]) -> str:
    if time_s < bounds["rest_start"]:
        return "pre_capture"
    if time_s <= bounds["rest_end"]:
        return "rest_or_between_rest_takes"
    if time_s < bounds["recovery_start"]:
        return "exercise_and_setup_transition_exact_times_unknown"
    if time_s <= bounds["recovery_end"]:
        return "recovery_or_between_recovery_takes"
    return "post_capture"


def _h10_continuous_rate(h10: pd.DataFrame, origin_s: float) -> pd.DataFrame:
    wall_s = h10.wall_ms.to_numpy(dtype=float) / 1000.0
    polar_s = h10.polar_timestamp_ns_since_2000.to_numpy(dtype=float) / 1e9
    voltage = h10.voltage_uv.to_numpy(dtype=float)
    fs = 1.0 / float(np.median(np.diff(polar_s)))
    sos = signal.butter(3, (5.0, 25.0), btype="bandpass", fs=fs, output="sos")
    filtered = signal.sosfiltfilt(sos, voltage)
    peaks, _ = signal.find_peaks(
        filtered, distance=int(fs * 0.4), prominence=0.3 * np.std(filtered)
    )
    if len(peaks) < 3:
        return pd.DataFrame()
    rr = np.diff(polar_s[peaks])
    beat_wall_s = (wall_s[peaks][1:] + wall_s[peaks][:-1]) / 2.0
    return _records(
        beat_wall_s - origin_s, 60.0 / rr,
        channel="h10_continuous_rr_bpm", unit="bpm", layer="estimate",
        source="H10_raw_ECG_fixed_5-25Hz_RR_continuous",
        take_id="continuous_H10", phase="continuous_session",
        clock="Polar H10 ECG timestamps; row-level host wall_ms used for session mapping",
        alignment="wall_time_aligned",
        alignment_method=(
            "adjacent-RR event time uses host wall_ms values attached to the R-peak rows; "
            "wall_ms repeats across ECG sample blocks, so this supports coarse session trajectory comparison, "
            "not beat-level cross-device synchronization"
        ),
        processing_stage="fixed_raw_ECG_RR_estimator",
        derived_from="continuous H10 raw ECG; fixed 5-25 Hz bandpass and adjacent R-R intervals",
    )


def _continuous_sensor_rows(h10_path: Path | None, esp_path: Path | None, origin_s: float) -> list[pd.DataFrame]:
    rows: list[pd.DataFrame] = []
    if h10_path is not None:
        h10 = pd.read_csv(h10_path)
        rate = _h10_continuous_rate(h10, origin_s)
        if not rate.empty:
            rows.append(rate)
    if esp_path is not None:
        esp = pd.read_csv(esp_path)
        wall_s = esp.host_time_ns.to_numpy(dtype=float) / 1e9
        rel_s = wall_s - origin_s
        ecg_t, ecg_v = _uniform_bins(rel_s, esp.ecg_adc.to_numpy(dtype=float), 25.0)
        rows.append(_records(
            ecg_t, ecg_v, channel="ad8232_ecg_raw_continuous_25hz", unit="ADC counts",
            layer="sensor", source="AD8232_ESP32", take_id="continuous_ESP32",
            phase="continuous_session", clock="ESP32 host_time_ns mapped to iPad master wall clock",
            alignment="wall_time_aligned",
            alignment_method="host_time_ns rebased to first iPad capture; 40 ms median bins",
            processing_stage="raw_acquisition_display_downsampled_25Hz",
            derived_from="continuous ESP32 acquisition export",
        ))
        for signal_name, channel in (("red", "max_red_raw_continuous"), ("ir", "max_ir_raw_continuous")):
            t, v = _uniform_bins(rel_s, esp[signal_name].to_numpy(dtype=float), 25.0)
            rows.append(_records(
                t, v, channel=channel, unit="a.u.", layer="sensor",
                source=f"MAX30102_{signal_name.upper()}", take_id="continuous_ESP32",
                phase="continuous_session", clock="ESP32 host_time_ns mapped to iPad master wall clock",
                alignment="wall_time_aligned",
                alignment_method="host_time_ns rebased to first iPad capture; 40 ms median bins",
                processing_stage="sensor_fifo_sample_median_binned_25Hz",
                derived_from="continuous ESP32 acquisition export",
            ))
    return rows


def _pcg_envelope_rows(wav_path: Path | None, origin_s: float, audio_offset_to_esp_stop_s: float | None) -> list[pd.DataFrame]:
    if wav_path is None:
        return []
    fs, audio = wavfile.read(wav_path, mmap=True)
    if audio.ndim == 1:
        audio = audio[:, None]
    duration_s = audio.shape[0] / float(fs)
    audio_end_wall_s = Path(wav_path).stat().st_mtime
    audio_start_wall_s = audio_end_wall_s - duration_s
    start_s = audio_start_wall_s - origin_s
    sos = signal.butter(4, (20.0, 400.0), btype="bandpass", fs=fs, output="sos")
    output: list[pd.DataFrame] = []
    samples_per_second = int(fs)
    if audio.shape[0] < samples_per_second:
        return output
    full_seconds = audio.shape[0] // samples_per_second
    for channel_idx in range(audio.shape[1]):
        raw = np.asarray(audio[:full_seconds * samples_per_second, channel_idx], dtype=np.float64)
        if np.issubdtype(audio.dtype, np.integer):
            raw /= float(max(abs(np.iinfo(audio.dtype).min), np.iinfo(audio.dtype).max + 1))
        filtered = signal.sosfiltfilt(sos, raw)
        windows = filtered.reshape(full_seconds, samples_per_second)
        rms = np.sqrt(np.mean(np.square(windows), axis=1))
        centers = start_s + np.arange(full_seconds, dtype=float) + 0.5
        alignment_method = (
            "audio start estimated as WAV filesystem mtime minus sample-count duration; "
            "WAV endpoint is 0.111 s after the final ESP32 host timestamp; no shared hardware marker; "
            "second-scale envelope only, not beat-level ECG-PCG timing"
        )
        if audio_offset_to_esp_stop_s is not None:
            alignment_method = alignment_method.replace("0.111 s", f"{audio_offset_to_esp_stop_s:.3f} s")
        output.append(_records(
            centers, rms,
            channel=f"pcg_band_rms_20_400hz_ch{channel_idx + 1}",
            unit="normalized_rms", layer="sensor",
            source="BOYA_BY_M1_through_stethoscope_tubing",
            take_id="continuous_audio", phase="continuous_session",
            clock="Laptop WAV sample clock; audio start estimated from filesystem modification time",
            alignment="derived_alignment", alignment_method=alignment_method,
            processing_stage="processed_observation_1s_band_energy_envelope",
            derived_from="external acoustic source WAV; raw audio is not included in exchange output",
        ))
    return output


def combine_take_intervals(
    source_csv: Path,
    source_manifest: Path,
    output_csv: Path,
    output_manifest: Path,
    h10_ecg_path: Path | None = None,
    esp32_path: Path | None = None,
    pcg_wav_path: Path | None = None,
) -> pd.DataFrame:
    """Place iPad-master take exports on their shared real-session wall-time axis.

    The original per-take time is retained as ``take_time_s`` and the take name
    as ``take_id``. Session ``time_s`` is relative to the first iPad capture.
    Gaps between captures remain gaps; no interpolation or data fabrication is
    performed.
    """
    frame = pd.read_csv(source_csv)
    manifest = json.loads(Path(source_manifest).read_text())
    intervals = manifest.get("intervals", [])
    starts = {
        str(item["scenario"]): int(item["iPad_start_wall_ms"])
        for item in intervals
    }
    durations = {
        str(item["scenario"]): float(item["duration_s"])
        for item in intervals
    }
    if not starts:
        raise ValueError("Manifest has no iPad capture intervals")
    if "scenario" not in frame or not set(frame.scenario.astype(str)).issubset(starts):
        raise ValueError("CSV scenarios do not match the capture intervals in the manifest")
    origin_ms = min(starts.values())
    origin_s = origin_ms / 1000.0
    rest_takes = [take for take in starts if take.startswith("rest_")]
    recovery_takes = [take for take in starts if take.startswith("recovery_")]
    if not rest_takes or not recovery_takes:
        raise ValueError("Session manifest must contain at least one rest and one recovery interval")
    phase_bounds = {
        "rest_start": min((starts[take] - origin_ms) / 1000.0 for take in rest_takes),
        "rest_end": max((starts[take] - origin_ms) / 1000.0 + durations[take] for take in rest_takes),
        "recovery_start": min((starts[take] - origin_ms) / 1000.0 for take in recovery_takes),
        "recovery_end": max((starts[take] - origin_ms) / 1000.0 + durations[take] for take in recovery_takes),
    }
    frame["take_id"] = frame["scenario"].astype(str)
    frame["take_time_s"] = pd.to_numeric(frame["time_s"], errors="raise")
    frame["time_s"] = frame.apply(
        lambda row: row["take_time_s"] + (starts[str(row["take_id"])] - origin_ms) / 1000.0,
        axis=1,
    )
    # Replace interval-cropped electrical/PPG waveforms with the continuous
    # device recordings where those source files were supplied.
    if h10_ecg_path is not None:
        frame = frame[~((frame.source == "H10") & (frame.channel == "h10_ecg_raw"))]
    if esp32_path is not None:
        frame = frame[~frame.source.astype(str).isin(["AD8232_ESP32", "MAX30102_RED", "MAX30102_IR"])]
    session_id = "real_session_demo"
    frame["scenario"] = session_id
    frame["episode_id"] = session_id
    frame["episode_relationship"] = "same_episode"
    frame["protocol_time_s"] = frame["time_s"] - (
        starts.get("recovery_1", origin_ms) - origin_ms
    ) / 1000.0
    frame["phase"] = frame["take_id"].map(
        lambda take: "rest" if str(take).startswith("rest_") else "recovery"
    )
    frame.loc[frame.take_id.astype(str).str.startswith("rest_"), "phase"] = "rest"
    frame.loc[frame.take_id.astype(str).str.startswith("recovery_"), "phase"] = "recovery"
    frame["alignment_method"] = frame.get("alignment_method", pd.Series("unspecified", index=frame.index))
    extra_rows = _continuous_sensor_rows(h10_ecg_path, esp32_path, origin_s)
    esp_last_wall_s = None
    if esp32_path is not None:
        esp_last_wall_s = pd.read_csv(esp32_path, usecols=["host_time_ns"]).host_time_ns.max() / 1e9
    audio_offset = None
    if pcg_wav_path is not None and esp_last_wall_s is not None:
        fs, audio_header = wavfile.read(pcg_wav_path, mmap=True)
        audio_end_wall_s = Path(pcg_wav_path).stat().st_mtime
        audio_offset = audio_end_wall_s - esp_last_wall_s
        extra_rows.extend(_pcg_envelope_rows(pcg_wav_path, origin_s, audio_offset))
    if extra_rows:
        extra = pd.concat(extra_rows, ignore_index=True)
        extra["scenario"] = session_id
        extra["episode_id"] = session_id
        extra["protocol_time_s"] = extra["time_s"] - (
            starts.get("recovery_1", origin_ms) - origin_ms
        ) / 1000.0
        extra["phase"] = extra["time_s"].map(lambda t: _phase_at(float(t), phase_bounds))
        frame = pd.concat([frame, extra], ignore_index=True, sort=False)
    frame = frame.sort_values(["time_s", "layer", "channel", "source"]).reset_index(drop=True)

    # Re-run the public exchange validation after transformation.
    validated = load_observations(frame.to_csv(index=False).encode())
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    validated.to_csv(output_csv, index=False)

    enriched = {key: value for key, value in manifest.items() if key != "intervals"}
    enriched["session_timeline"] = {
        "scenario": session_id,
        "episode_id": session_id,
        "time_origin": "first capture start represented as session time zero",
        "mapping": "session_time_s = take_time_s + relative capture-start offset",
        "take_id_field": "take_id preserves the original rest/recovery interval label",
        "take_time_field": "take_time_s preserves the original interval-relative time",
        "gaps": "No iPad samples are invented between capture windows. Continuous H10/ESP32/audio features, when supplied, retain their measured coverage through those intervals.",
        "protocol_time_origin": "time_s=0 at Rest 1 capture start; protocol_time_s=0 at Recovery 1 capture start, used as a proxy because exact exercise-end time is not timestamped",
        "events": [
            *[
                {
                    "name": f"{item['scenario']}_capture_interval",
                    "start_s": (int(item["iPad_start_wall_ms"]) - origin_ms) / 1000.0,
                    "end_s": (int(item["iPad_start_wall_ms"]) - origin_ms) / 1000.0 + float(item["duration_s"]),
                }
                for item in intervals
            ],
            {
                "name": "exercise_and_setup_transition_window",
                "start_s": phase_bounds["rest_end"],
                "end_s": phase_bounds["recovery_start"],
                "exact_exercise_start_end_known": False,
            },
            {
                "name": "recovery_capture_start_proxy",
                "time_s": phase_bounds["recovery_start"],
                "meaning": "first recovery iPad capture start; exact exercise-end time unavailable",
            },
        ],
        "continuous_h10_included": h10_ecg_path is not None,
        "continuous_esp32_included": esp32_path is not None,
        "audio_features_included": pcg_wav_path is not None,
        "audio_wav_copied": False,
        "audio_end_offset_from_esp_host_s": audio_offset,
        "time_range_s": [float(validated.time_s.min()), float(validated.time_s.max())],
        "duration_from_iPad_origin_s": float(validated.time_s.max()),
        "audio": "excluded because laptop audio-to-iPad interval mapping is approximate",
    }
    enriched["intervals"] = [
        {
            "scenario": str(item["scenario"]),
            "session_start_s": (int(item["iPad_start_wall_ms"]) - origin_ms) / 1000.0,
            "session_stop_s": (int(item["iPad_start_wall_ms"]) - origin_ms) / 1000.0
            + float(item["duration_s"]),
            "duration_s": float(item["duration_s"]),
        }
        for item in intervals
    ]
    output_manifest = Path(output_manifest)
    output_manifest.parent.mkdir(parents=True, exist_ok=True)
    output_manifest.write_text(json.dumps(enriched, indent=2) + "\n")
    return validated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Per-take harmonized exchange CSV")
    parser.add_argument("--manifest", type=Path, required=True, help="Sidecar from harmonize_six_take_research.py")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-manifest", type=Path, required=True)
    parser.add_argument("--continuous-h10-ecg", type=Path)
    parser.add_argument("--continuous-esp32", type=Path)
    parser.add_argument("--pcg-wav", type=Path)
    args = parser.parse_args()
    frame = combine_take_intervals(
        args.input, args.manifest, args.output, args.output_manifest,
        h10_ecg_path=args.continuous_h10_ecg,
        esp32_path=args.continuous_esp32,
        pcg_wav_path=args.pcg_wav,
    )
    print(
        f"Wrote {len(frame)} rows for {frame.take_id.nunique()} takes on a shared "
        f"{frame.time_s.max():.1f} s session timeline to {args.output}"
    )


if __name__ == "__main__":
    main()
