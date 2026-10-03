from __future__ import annotations

from pathlib import Path
import pandas as pd


PCG_CHANNELS = {
    "pcg_band_rms_20_400hz_ch1": "PCG band RMS · channel 1",
    "pcg_band_rms_20_400hz_ch2": "PCG band RMS · channel 2",
}


def pcg_observation_payload(frame: pd.DataFrame, cursor_time_s: float, coordinate: str = "Real session time") -> dict:
    """Return exported audio features and explicit H10 context; never loads a WAV."""
    time_column = "session_time_s" if "session_time_s" in frame.columns else "time_s"
    audio = frame[
        frame["channel"].astype(str).isin(PCG_CHANNELS)
        & frame["layer"].astype(str).eq("sensor")
    ].copy()
    if audio.empty:
        return {"available": False}

    audio["plot_time_s"] = pd.to_numeric(audio[time_column], errors="coerce")
    audio["value"] = pd.to_numeric(audio["value"], errors="coerce")
    audio = audio.dropna(subset=["plot_time_s", "value"])
    if audio.empty:
        return {"available": False}

    session_cursor = float(cursor_time_s)
    if coordinate == "Recovery-relative protocol time" and {"protocol_time_s", "session_time_s"}.issubset(frame.columns):
        mapping = frame[["protocol_time_s", "session_time_s"]].copy()
        mapping["protocol_time_s"] = pd.to_numeric(mapping["protocol_time_s"], errors="coerce")
        mapping["session_time_s"] = pd.to_numeric(mapping["session_time_s"], errors="coerce")
        mapping = mapping.dropna().drop_duplicates("protocol_time_s")
        if not mapping.empty:
            idx = (mapping["protocol_time_s"] - float(cursor_time_s)).abs().idxmin()
            session_cursor = float(mapping.loc[idx, "session_time_s"])

    min_time, max_time = float(audio.plot_time_s.min()), float(audio.plot_time_s.max())
    session_cursor = min(max(session_cursor, min_time), max_time)
    half_window = 30.0
    lower, upper = max(min_time, session_cursor - half_window), min(max_time, session_cursor + half_window)
    window = audio[audio.plot_time_s.between(lower, upper)].copy()

    channels = []
    current_rms = []
    for channel, label in PCG_CHANNELS.items():
        full_part = audio[audio["channel"].astype(str).eq(channel)].sort_values("plot_time_s")
        part = window[window["channel"].astype(str).eq(channel)].sort_values("plot_time_s")
        if full_part.empty:
            continue
        nearest_idx = (full_part["plot_time_s"] - session_cursor).abs().idxmin()
        nearest = full_part.loc[nearest_idx]
        current_rms.append({"label": label, "value": float(nearest["value"]), "sample_time_s": float(nearest["plot_time_s"])})
        channels.append({
            "label": label,
            "time_s": part["plot_time_s"].astype(float).tolist(),
            "value": part["value"].astype(float).tolist(),
        })

    # Optional stored acoustic rate candidates; do not derive them from the
    # one-second RMS stream, which cannot resolve event timing.
    candidate_rows_all = frame[
        frame["channel"].astype(str).str.lower().str.contains("pcg|audio|acoustic", regex=True, na=False)
        & frame["layer"].astype(str).isin(["estimate", "diagnostic"])
        & frame["unit"].astype(str).str.lower().isin(["bpm", "beats/min", "beat/min", "events/min"])
    ].copy()
    acoustic_rate_features_exported = not candidate_rows_all.empty
    candidate_rows = candidate_rows_all.copy()
    candidate_rows["plot_time_s"] = pd.to_numeric(candidate_rows[time_column], errors="coerce")
    candidate_rows["value"] = pd.to_numeric(candidate_rows["value"], errors="coerce")
    candidate_rows = candidate_rows.dropna(subset=["plot_time_s", "value"])
    candidate_rows = candidate_rows[candidate_rows.plot_time_s.between(lower, upper)]
    acoustic_features = []
    for (channel, source), part in candidate_rows.groupby(["channel", "source"], sort=False):
        channel_key = str(channel).lower()
        if "cardio" in channel_key or "near" in channel_key or "candidate" in channel_key:
            label = "Cardiac-rate-near spectral candidate · H10-guided"
        elif "secondary" in channel_key or "double" in channel_key:
            label = "Second-ranked reference-blind spectral component"
        elif "dominant" in channel_key or "winner" in channel_key:
            label = "Reference-blind dominant spectral component"
        else:
            label = str(channel).replace("_", " ")
        part = part.sort_values("plot_time_s")
        nearest_idx = (part["plot_time_s"] - session_cursor).abs().idxmin()
        nearest = part.loc[nearest_idx]
        acoustic_features.append({
            "label": label, "channel": str(channel), "source": str(source),
            "time_s": part["plot_time_s"].astype(float).tolist(),
            "value": part["value"].astype(float).tolist(),
            "current_value": float(nearest["value"]),
            "unit": str(nearest["unit"]),
            "reference_informed": "H10-guided" in label,
        })

    h10 = frame[
        frame["source"].astype(str).str.contains("H10", case=False, na=False)
        & frame["unit"].astype(str).str.lower().isin(["bpm", "beats/min", "beat/min"])
    ].copy()
    h10["plot_time_s"] = pd.to_numeric(h10[time_column], errors="coerce")
    h10["value"] = pd.to_numeric(h10["value"], errors="coerce")
    h10 = h10.dropna(subset=["plot_time_s", "value"])
    h10 = h10[h10.plot_time_s.between(lower, upper)].sort_values("plot_time_s")

    h10_all = frame[
        frame["source"].astype(str).str.contains("H10", case=False, na=False)
        & frame["unit"].astype(str).str.lower().isin(["bpm", "beats/min", "beat/min"])
    ].copy()
    h10_all["plot_time_s"] = pd.to_numeric(h10_all[time_column], errors="coerce")
    h10_all["value"] = pd.to_numeric(h10_all["value"], errors="coerce")
    h10_all = h10_all.dropna(subset=["plot_time_s", "value"])
    h10_current = None
    h10_guidance_current = None
    if not h10_all.empty:
        h10_nearest_idx = (h10_all["plot_time_s"] - session_cursor).abs().idxmin()
        h10_nearest = h10_all.loc[h10_nearest_idx]
        h10_current = {
            "value": float(h10_nearest["value"]),
            "sample_time_s": float(h10_nearest["plot_time_s"]),
            "offset_s": float(h10_nearest["plot_time_s"] - session_cursor),
        }
        recent_h10 = h10_all[h10_all.plot_time_s.between(session_cursor - 30.0, session_cursor)]
        if not recent_h10.empty:
            h10_guidance_current = {
                "value": float(recent_h10["value"].median()),
                "window_start_s": float(recent_h10.plot_time_s.min()),
                "window_stop_s": float(recent_h10.plot_time_s.max()),
            }

    meta = audio.iloc[0]
    derived_source = str(meta.get("derived_from", "")).split(";", 1)[0].strip()
    source_asset = Path(derived_source).name if derived_source else "not declared in exchange file"
    expected_points = max(1, int(round(upper - lower)) + 1)
    observed_per_channel = [len(item["time_s"]) for item in channels]
    coverage_fraction = min(observed_per_channel) / expected_points if observed_per_channel else 0.0
    return {
        "available": bool(channels),
        "take_id": str(meta.get("take_id", "continuous_audio")),
        "channels": channels,
        "current_rms": current_rms,
        "acoustic_features": acoustic_features,
        "acoustic_rate_features_exported": acoustic_rate_features_exported,
        "h10_time_s": h10["plot_time_s"].astype(float).tolist(),
        "h10_rate_bpm": h10["value"].astype(float).tolist(),
        "h10_current": h10_current,
        "h10_guidance_current": h10_guidance_current,
        "cursor_session_time_s": session_cursor,
        "window_start_s": lower,
        "window_stop_s": upper,
        "sample_count": int(len(audio)),
        "window_sample_count": int(len(window)),
        "window_expected_seconds": expected_points,
        "coverage_fraction": float(min(1.0, coverage_fraction)),
        "clipping_status": "unavailable; waveform samples are not in this export",
        "waveform_available": False,
        "source": str(meta.get("source", "unspecified")),
        "source_asset": source_asset,
        "clock_provenance": str(meta.get("clock_provenance", "unspecified")),
        "alignment_status": str(meta.get("alignment_status", "unknown")),
        "processing_stage": str(meta.get("processing_stage", "unspecified")),
        "feature_description": "1 s RMS band-energy envelope, 20–400 Hz, two channels",
        "acoustic_rate_feature_description": (
            "30 s trailing 20–200 Hz amplitude-envelope Welch screen, 1 s step; "
            "48–52 Hz suppression; 500 Hz envelope; 30–300 events/min search; "
            "cardiac-near candidate is H10-guided within ±12 events/min"
        ) if acoustic_rate_features_exported else "not present in exchange file",
        "interpretation": (
            "H10 is shown as independent rate context, not as an audio-derived estimate. "
            "This export has no acoustic spectral-rate or beat-locked PCG series; S1/S2 are not identified."
        ),
    }
