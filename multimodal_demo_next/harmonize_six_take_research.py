from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import signal

CONDITIONS = ["rest_1", "rest_2", "rest_3", "recovery_1", "recovery_2", "recovery_3"]
FS_RGB = 30.0
FS_PPG_ECG = 25.0
WINDOW_S = 12.0
STEP_S = 4.0
SEARCH_HZ = (0.5, 3.0)
PULSE_COLUMNS = {
    "mean_r": ("camera_mean_red", "iPad8_RGB"),
    "mean_g": ("camera_mean_green", "iPad8_RGB"),
    "mean_b": ("camera_mean_blue", "iPad8_RGB"),
    "mean_y": ("camera_mean_luma", "iPad8_RGB"),
    "frame_diff_proxy": ("camera_frame_difference_proxy", "iPad8_RGB"),
}


def _records(time_s, channel, value, unit, layer, source, scenario):
    good = np.isfinite(time_s) & np.isfinite(value)
    return pd.DataFrame({
        "time_s": np.asarray(time_s)[good],
        "channel": channel,
        "value": np.asarray(value)[good],
        "unit": unit,
        "layer": layer,
        "source": source,
        "scenario": scenario,
    })


def _add_raw(records, time_s, channel, value, unit, source, scenario):
    if len(time_s):
        records.append(_records(time_s, channel, value, unit, "sensor", source, scenario))


def _uniform_bins(time_s, values, fs, start_s, stop_s):
    """Median-bin a sampled channel to a common 25/30 Hz display grid."""
    t = np.asarray(time_s, dtype=float)
    x = np.asarray(values, dtype=float)
    keep = np.isfinite(t) & np.isfinite(x) & (t >= start_s) & (t < stop_s)
    if not keep.any():
        return np.array([]), np.array([])
    bins = np.floor((t[keep] - start_s) * fs).astype(int)
    grouped = pd.DataFrame({"bin": bins, "value": x[keep]}).groupby("bin")["value"].median()
    # Keep only measured bins. No gap is filled in this raw display layer.
    return start_s + grouped.index.to_numpy(dtype=float) / fs, grouped.to_numpy(dtype=float)


def _welch_peak_bpm(values, fs):
    y = np.asarray(values, dtype=float)
    if len(y) < int(fs * WINDOW_S * 0.9) or not np.isfinite(y).all():
        return np.nan
    f, p = signal.welch(
        y, fs=fs, nperseg=min(512, len(y)),
        noverlap=min(256, len(y) // 2), detrend="linear",
    )
    in_band = (f >= SEARCH_HZ[0]) & (f <= SEARCH_HZ[1])
    if not in_band.any():
        return np.nan
    return float(60.0 * f[in_band][np.argmax(p[in_band])])


def _rgb_projection_peaks(stats, capture_start_ms, capture_stop_ms, scenario):
    frame = pd.DataFrame(stats).sort_values("wall_ms").drop_duplicates("wall_ms")
    wall_s = frame["wall_ms"].to_numpy(dtype=float) / 1000.0
    rel_s = wall_s - capture_start_ms / 1000.0
    rgb = frame[["mean_r", "mean_g", "mean_b"]].to_numpy(dtype=float)
    y_raw = frame["mean_y"].to_numpy(dtype=float)
    rows = []
    capture_duration = float((capture_stop_ms - capture_start_ms) / 1000.0)
    window_start = 0.0
    while window_start + WINDOW_S <= capture_duration + 1e-6:
        a = window_start
        b = window_start + WINDOW_S
        grid = np.arange(a, b, 1.0 / FS_RGB)
        x = np.column_stack([np.interp(grid, rel_s, rgb[:, j]) for j in range(3)])
        z = x / np.maximum(x.mean(axis=0), 1e-9) - 1.0
        z = signal.detrend(z, axis=0, type="linear")
        r, g, blue = z.T
        c0 = 3.0 * r - 2.0 * g
        c1 = 1.5 * r + g - 1.5 * blue
        alpha = np.std(c0) / max(np.std(c1), 1e-12)
        chrom = c0 - alpha * c1
        p0 = 2.0 * g - 2.0 * blue
        p1 = 1.5 * r + g - 1.5 * blue
        alpha_pos = np.std(p0) / max(np.std(p1), 1e-12)
        pos = p0 + alpha_pos * p1
        y = np.interp(grid, rel_s, y_raw)
        y = y / max(float(np.mean(y)), 1e-9) - 1.0
        y = signal.detrend(y, type="linear")
        center = (a + b) / 2.0
        for method, trace in (("Y", y), ("POS", pos), ("CHROM", chrom)):
            bpm = _welch_peak_bpm(trace, FS_RGB)
            if np.isfinite(bpm):
                rows.append({
                    "time_s": center,
                    "channel": f"{method.lower()}_blind_winner_bpm",
                    "value": bpm,
                    "unit": "bpm",
                    "layer": "estimate",
                    "source": f"iPad8_{method}_12s_Welch_blind",
                    "scenario": scenario,
                })
        window_start += STEP_S
    return rows


def _ppg_window_peaks(time_s, red, ir, duration_s, scenario):
    rows = []
    if len(time_s) == 0:
        return rows
    start = 0.0
    while start + WINDOW_S <= duration_s + 1e-6:
        mask = (time_s >= start) & (time_s < start + WINDOW_S)
        center = start + WINDOW_S / 2.0
        for name, values in (("red", red), ("ir", ir)):
            if mask.sum() < FS_PPG_ECG * WINDOW_S * 0.9:
                continue
            bpm = _welch_peak_bpm(values[mask], FS_PPG_ECG)
            if np.isfinite(bpm):
                rows.append({
                    "time_s": center,
                    "channel": f"max_{name}_blind_winner_bpm",
                    "value": bpm,
                    "unit": "bpm",
                    "layer": "estimate",
                    "source": f"MAX30102_{name.upper()}_12s_Welch_blind",
                    "scenario": scenario,
                })
        start += STEP_S
    return rows


def _h10_rr_series(ecg: pd.DataFrame, capture_start_ms, capture_stop_ms, scenario):
    d = ecg[(ecg.wall_ms >= capture_start_ms - 2500) & (ecg.wall_ms <= capture_stop_ms + 2500)].copy()
    if len(d) < 1000:
        return pd.DataFrame(), np.nan
    t_wall = d.wall_ms.to_numpy(dtype=float) / 1000.0
    # Polar ECG timestamps provide sub-millisecond beat intervals; wall_ms maps
    # the resulting beats to the iPad's host-wall-time interval.
    t_ecg = d.polar_timestamp_ns_since_2000.to_numpy(dtype=float) / 1e9
    voltage = d.voltage_uv.to_numpy(dtype=float)
    fs = 1.0 / np.median(np.diff(t_ecg))
    sos = signal.butter(3, (5.0, 25.0), btype="bandpass", fs=fs, output="sos")
    filtered = signal.sosfiltfilt(sos, voltage)
    peaks, _ = signal.find_peaks(
        filtered, distance=int(fs * 0.4), prominence=0.3 * np.std(filtered)
    )
    if len(peaks) < 3:
        return pd.DataFrame(), fs
    rr = np.diff(t_ecg[peaks])
    beat_wall = (t_wall[peaks][1:] + t_wall[peaks][:-1]) / 2.0
    bpm = 60.0 / rr
    keep = (beat_wall * 1000.0 >= capture_start_ms) & (beat_wall * 1000.0 <= capture_stop_ms)
    frame = pd.DataFrame({
        "time_s": beat_wall[keep] - capture_start_ms / 1000.0,
        "channel": "h10_raw_ecg_rr_bpm",
        "value": bpm[keep],
        "unit": "bpm",
        "layer": "estimate",
        "source": "H10_raw_ECG_fixed_5-25Hz_RR",
        "scenario": scenario,
    })
    return frame, fs


def harmonize(research_root: Path, output: Path, manifest_path: Path) -> pd.DataFrame:
    root = Path(research_root)
    captures_dir = root / "ipad_rppg" / "captures"
    capture_paths = sorted(captures_dir.glob("ipad_rppg_*.json"))
    sensor_dir = root / "chest_audio_landmarks"
    esp_paths = list(sensor_dir.glob("*_esp32_hosttime.csv"))
    h10_paths = list(sensor_dir.glob("*/h10_ecg_*.csv"))
    if len(capture_paths) != len(CONDITIONS):
        raise FileNotFoundError(f"Expected {len(CONDITIONS)} camera capture records")
    if len(h10_paths) != 1 or len(esp_paths) != 1:
        raise FileNotFoundError("Expected one continuous H10 ECG file and one ESP32 host-time file")
    esp_path = esp_paths[0]
    h10 = pd.read_csv(h10_paths[0])
    esp = pd.read_csv(esp_path)
    esp_wall_s = esp.host_time_ns.to_numpy(dtype=float) / 1e9
    pieces = []
    manifest = {
        "source_collection": "three-rest / exercise-challenge / three-recovery capture",
        "time_master": "each iPad capture_start_wall_ms; H10 and ESP32 cropped by host wall time",
        "episode_model": "each iPad capture is a distinct episode; rows share that capture episode id",
        "clock_provenance": {
            "iPad8_*": "iPad wall-clock timestamps; capture interval is time origin",
            "H10*": "Polar H10 timestamps mapped to iPad interval by host wall time",
            "AD8232*/MAX30102*": "ESP32 monotonic device clock; host wall-time mapping to iPad interval",
        },
        "alignment_status": {
            "iPad8_*": "master_clock",
            "H10*/AD8232*/MAX30102*": "wall_time_aligned",
        },
        "episode_relationship": "same_episode within each iPad capture; distinct takes are separate episodes",
        "camera_window_analysis": {
            "window_s": WINDOW_S, "step_s": STEP_S, "fs_hz": FS_RGB,
            "welch_search_hz": list(SEARCH_HZ), "projection_peaks": "blind window dominant-bin estimates",
        },
        "contact_ppg_window_analysis": {
            "window_s": WINDOW_S, "step_s": STEP_S, "fs_hz": FS_PPG_ECG,
            "welch_search_hz": list(SEARCH_HZ), "fresh_samples": "40 ms bins from the 250 Hz ESP32 log",
        },
        "h10_rate_analysis": "fixed 5-25 Hz bandpass; sample rate measured from Polar timestamps; positive peaks; 0.4 s minimum separation; 0.3 SD prominence; adjacent-RR bpm",
        "pcg": "excluded: report states laptop audio to iPad interval mapping is approximate",
        "intervals": [],
    }

    for capture_index, (path, scenario) in enumerate(zip(capture_paths, CONDITIONS), start=1):
        d = json.loads(path.read_text())
        start_ms, stop_ms = int(d["capture_start_wall_ms"]), int(d["capture_stop_wall_ms"])
        start_s, stop_s = start_ms / 1000.0, stop_ms / 1000.0
        duration = (stop_ms - start_ms) / 1000.0
        interval_count = 0

        # iPad sensor-side summary traces, preserving camera timing and units.
        stats = pd.DataFrame(d["stats"]).sort_values("wall_ms").drop_duplicates("wall_ms")
        cam_t = stats.wall_ms.to_numpy(dtype=float) / 1000.0 - start_s
        for column, (channel, source) in PULSE_COLUMNS.items():
            _add_raw(pieces, cam_t, channel, stats[column].to_numpy(dtype=float), "a.u.", source, scenario)
            interval_count += len(cam_t)
        for row in _rgb_projection_peaks(d["stats"], start_ms, stop_ms, scenario):
            pieces.append(pd.DataFrame([row]))
            interval_count += 1

        # H10 rate from raw ECG with the already cross-checked fixed detector.
        h10_rate, fs_h10 = _h10_rr_series(h10, start_ms, stop_ms, scenario)
        if not h10_rate.empty:
            pieces.append(h10_rate)
            interval_count += len(h10_rate)

        # Include a display-only downsample of the raw H10 electrical waveform.
        h10_crop = h10[(h10.wall_ms >= start_ms) & (h10.wall_ms <= stop_ms)]
        ht = h10_crop.wall_ms.to_numpy(dtype=float) / 1000.0 - start_s
        ht, hv = _uniform_bins(ht, h10_crop.voltage_uv.to_numpy(dtype=float), FS_PPG_ECG, 0.0, duration)
        _add_raw(pieces, ht, "h10_ecg_raw", hv, "uV", "H10", scenario)
        interval_count += len(ht)

        # ESP32/PPG sample timestamps share the iPad host wall clock.
        mask = (esp_wall_s >= start_s) & (esp_wall_s <= stop_s)
        e = esp.loc[mask]
        et = e.host_time_ns.to_numpy(dtype=float) / 1e9 - start_s
        ecg_t, ecg_v = _uniform_bins(et, e.ecg_adc.to_numpy(dtype=float), FS_PPG_ECG, 0.0, duration)
        _add_raw(pieces, ecg_t, "ad8232_ecg_raw", ecg_v, "ADC counts", "AD8232_ESP32", scenario)
        interval_count += len(ecg_t)

        # MAX30102 data are held between 25 Hz sensor updates in the 250 Hz log.
        # Median aggregation into 40 ms bins yields one current value per update.
        ppg_bins = np.floor(et * FS_PPG_ECG).astype(int)
        ppg = pd.DataFrame({
            "bin": ppg_bins,
            "red": e.red.to_numpy(dtype=float),
            "ir": e.ir.to_numpy(dtype=float),
        }).groupby("bin")[["red", "ir"]].median()
        ppg_t = ppg.index.to_numpy(dtype=float) / FS_PPG_ECG
        red = ppg.red.to_numpy(dtype=float)
        ir = ppg.ir.to_numpy(dtype=float)
        _add_raw(pieces, ppg_t, "max_red_raw", red, "a.u.", "MAX30102_RED", scenario)
        _add_raw(pieces, ppg_t, "max_ir_raw", ir, "a.u.", "MAX30102_IR", scenario)
        interval_count += 2 * len(ppg_t)
        for row in _ppg_window_peaks(ppg_t, red, ir, duration, scenario):
            pieces.append(pd.DataFrame([row]))
            interval_count += 1

        manifest["intervals"].append({
            "scenario": scenario,
            "capture_index": capture_index,
            "iPad_start_wall_ms": start_ms,
            "iPad_stop_wall_ms": stop_ms,
            "duration_s": duration,
            "iPad_frames": len(stats),
            "H10_RR_samples": len(h10_rate),
            "H10_estimated_fs_hz": float(fs_h10) if np.isfinite(fs_h10) else None,
            "rows_added": interval_count,
        })

    output_frame = pd.concat(pieces, ignore_index=True)
    output_frame["episode_id"] = output_frame["scenario"].astype(str)
    output_frame["episode_relationship"] = "same_episode"
    output_frame["clock_provenance"] = output_frame["source"].map(
        lambda source: (
            "iPad wall-clock timestamps; capture interval is time origin"
            if str(source).startswith("iPad8_") else
            "Polar H10 timestamps mapped to iPad interval by host wall time"
            if str(source) == "H10" or str(source).startswith("H10_") else
            "ESP32 monotonic device clock; host wall-time mapping to iPad interval"
            if str(source).startswith("AD8232") or str(source).startswith("MAX30102") else
            "unknown clock provenance"
        )
    )
    output_frame["alignment_status"] = output_frame["source"].map(
        lambda source: "master_clock" if str(source).startswith("iPad8_") else "wall_time_aligned"
    )
    output_frame = output_frame.sort_values(["scenario", "time_s", "layer", "channel"]).reset_index(drop=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output_frame.to_csv(output, index=False)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return output_frame


def main() -> None:
    parser = argparse.ArgumentParser(description="Harmonize a six-interval recording to the dashboard exchange format.")
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    frame = harmonize(args.research_root, args.output, args.manifest)
    print(f"Wrote {len(frame)} rows across {frame.scenario.nunique()} iPad-master intervals to {args.output}")
    print("Per-scenario bpm series:")
    bpm = frame[(frame.unit == "bpm")].groupby(["scenario", "channel", "source"]).size()
    print(bpm.to_string())


if __name__ == "__main__":
    main()
