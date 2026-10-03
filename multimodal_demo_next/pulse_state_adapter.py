from __future__ import annotations

import numpy as np
import pandas as pd

# Reference used only to map dimensional Pulse SVR to a dimensionless visual
# multiplier. This is a declared project reference, not episode-fitted.
PULSE_NORMOTENSIVE_SVR_REFERENCE_MM_HG_S_PER_ML = 0.939706
MAX_INTERPOLATION_BRACKET_S = 0.100
CYCLE_ONSET_FRACTION_OF_P95 = 0.10
MAX_WAVEFORM_AGE_PERIODS = 1.5
WAVEFORM_PHASE_SAMPLES = 128
MAX_TRAJECTORY_SAMPLES = 100_000
MAX_OBSERVED_HR_BRACKET_S = 2.5

CHANNEL_MAP = {
    "heart_rate": ("hr_bpm", {"bpm", "beats/min", "beat/min"}),
    "heart_rate_per_min": ("hr_bpm", {"bpm", "beats/min", "beat/min"}),
    "mean_arterial_pressure": ("map_mmHg", {"mmhg"}),
    "map_mmHg": ("map_mmHg", {"mmhg"}),
    "systolic_pressure": ("systolic_mmHg", {"mmhg"}),
    "systolic_mmHg": ("systolic_mmHg", {"mmhg"}),
    "diastolic_pressure": ("diastolic_mmHg", {"mmhg"}),
    "diastolic_mmHg": ("diastolic_mmHg", {"mmhg"}),
    "cardiac_output": ("cardiac_output_L_min", {"l/min", "l min-1"}),
    "cardiac_output_L_min": ("cardiac_output_L_min", {"l/min", "l min-1"}),
    "stroke_volume": ("stroke_volume_mL", {"ml", "ml/beat"}),
    "stroke_volume_mL": ("stroke_volume_mL", {"ml", "ml/beat"}),
    "blood_volume": ("blood_volume_L", {"l", "liter", "liters", "ml", "milliliter", "milliliters"}),
    "blood_volume_mL": ("blood_volume_L", {"l", "liter", "liters", "ml", "milliliter", "milliliters"}),
    "systemic_vascular_resistance": ("svr_absolute_mmHg_s_mL", {"mmhg s/ml", "mmhg*s/ml", "mmhg·s/ml"}),
    "systemic_vascular_resistance_mmHg_s_mL": ("svr_absolute_mmHg_s_mL", {"mmhg s/ml", "mmhg*s/ml", "mmhg·s/ml"}),
    "svr_mmHg_s_mL": ("svr_absolute_mmHg_s_mL", {"mmhg s/ml", "mmhg*s/ml", "mmhg·s/ml"}),
    "aortic_inflow": ("aortic_inflow_mL_s", {"ml/s", "ml s-1"}),
    "aortic_pressure": ("aortic_pressure_mmHg", {"mmhg"}),
}
WAVEFORM_CHANNELS = {"aortic_inflow_mL_s", "aortic_pressure_mmHg"}


def _normal_unit(unit: object) -> str:
    return " ".join(str(unit).strip().lower().replace("·", " ").split())


def _series_arrays(part: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    ordered = part.sort_values("time_s")
    return ordered["time_s"].to_numpy(dtype=float), ordered["value"].to_numpy(dtype=float)


def _convert_channel_value(output_key: str, value: float, unit: str) -> float:
    if output_key == "blood_volume_L" and unit in {"ml", "milliliter", "milliliters"}:
        return value / 1000.0
    return value


def _interpolate_at(part: pd.DataFrame, target_s: float) -> tuple[float | None, dict]:
    """Interpolate only inside a sufficiently close pair of source samples."""
    times, values = _series_arrays(part)
    right = int(np.searchsorted(times, target_s, side="left"))
    if right < len(times) and abs(times[right] - target_s) <= 1e-9:
        t = float(times[right])
        return float(values[right]), {
            "sample_time_s": target_s, "cursor_delta_s": 0.0,
            "source_sample_times_s": [t], "method": "source_sample",
            "bracket_width_s": 0.0, "status": "supplied",
        }
    if right == len(times) and abs(times[-1] - target_s) <= 1e-9:
        t = float(times[-1])
        return float(values[-1]), {
            "sample_time_s": target_s, "cursor_delta_s": 0.0,
            "source_sample_times_s": [t], "method": "source_sample",
            "bracket_width_s": 0.0, "status": "supplied",
        }
    if right == 0 or right == len(times):
        nearest = float(times[0] if right == 0 else times[-1])
        return None, {
            "sample_time_s": None, "cursor_delta_s": None,
            "source_sample_times_s": [nearest], "method": "none",
            "bracket_width_s": None, "status": "unavailable",
            "reason": "cursor is outside the source time range; extrapolation is disabled",
        }
    t0, t1 = float(times[right - 1]), float(times[right])
    width = t1 - t0
    if width <= 0 or width > MAX_INTERPOLATION_BRACKET_S:
        return None, {
            "sample_time_s": None, "cursor_delta_s": None,
            "source_sample_times_s": [t0, t1], "method": "none",
            "bracket_width_s": width, "status": "unavailable",
            "reason": f"source bracket exceeds {MAX_INTERPOLATION_BRACKET_S:.3f} s freshness limit",
        }
    fraction = (target_s - t0) / width
    value = values[right - 1] + fraction * (values[right] - values[right - 1])
    return float(value), {
        "sample_time_s": target_s, "cursor_delta_s": 0.0,
        "source_sample_times_s": [t0, t1], "method": "linear_interpolation",
        "bracket_width_s": width, "status": "supplied",
    }


def _integrated_hr_phase(hr_part: pd.DataFrame, cursor_s: float) -> float | None:
    """Return accumulated HR cycles from the first HR sample to the cursor."""
    times, values = _series_arrays(hr_part)
    if cursor_s < times[0] - 1e-9 or cursor_s > times[-1] + 1e-9:
        return None
    cursor_s = min(max(cursor_s, float(times[0])), float(times[-1]))
    inner = times[(times > times[0]) & (times < cursor_s)]
    sample_t = np.concatenate(([times[0]], inner, [cursor_s]))
    if len(sample_t) > 1 and float(np.diff(sample_t).max()) > MAX_INTERPOLATION_BRACKET_S:
        return None
    sample_hr = np.interp(sample_t, times, values)
    cycles = float(np.sum((sample_hr[:-1] + sample_hr[1:]) * 0.5 * np.diff(sample_t) / 60.0))
    return cycles % 1.0


def _mechanical_phase_metadata(
    flow_part: pd.DataFrame | None,
    hr_part: pd.DataFrame,
) -> dict:
    """Describe whether the episode has a continuous, HR-consistent inflow cycle."""
    if flow_part is None or len(flow_part) < 4:
        return {"available": False, "reason": "aortic inflow is unavailable"}
    if hr_part is None or len(hr_part) < 2:
        return {"available": False, "reason": "HR trajectory is unavailable"}
    flow_t, flow = _series_arrays(flow_part)
    if float(np.nanmax(flow)) <= 0:
        return {"available": False, "reason": "aortic inflow has no positive ejection"}
    baseline = float(np.nanpercentile(flow, 5))
    p95 = float(np.nanpercentile(flow, 95))
    threshold = baseline + CYCLE_ONSET_FRACTION_OF_P95 * (p95 - baseline)
    above = flow > threshold
    onset_idx = np.flatnonzero(above & ~np.r_[False, above[:-1]])
    onset_times = flow_t[onset_idx]
    if len(onset_times) < 2:
        return {
            "available": False,
            "reason": "fewer than two aortic-inflow onset crossings",
            "onset_threshold_mL_s": threshold,
        }

    hr_t, hr = _series_arrays(hr_part)
    valid_periods = []
    for start_s, end_s in zip(onset_times[:-1], onset_times[1:]):
        period = float(end_s - start_s)
        midpoint = (float(start_s) + float(end_s)) * 0.5
        right = int(np.searchsorted(hr_t, midpoint, side="left"))
        if right == 0 or right == len(hr_t):
            return {
                "available": False,
                "reason": "inflow cycle is outside the fresh HR trajectory",
                "onset_threshold_mL_s": threshold,
            }
        if float(hr_t[right] - hr_t[right - 1]) > MAX_INTERPOLATION_BRACKET_S:
            return {
                "available": False,
                "reason": "HR has a gap while validating inflow cycle periods",
                "onset_threshold_mL_s": threshold,
            }
        hr_mid = float(np.interp(midpoint, hr_t, hr))
        expected = 60.0 / hr_mid if hr_mid > 0 else 0.0
        if expected <= 0 or not (0.5 * expected <= period <= 1.5 * expected):
            return {
                "available": False,
                "reason": "inflow onset spacing is inconsistent with the HR trajectory",
                "onset_threshold_mL_s": threshold,
            }
        valid_periods.append(period)

    return {
        "available": True,
        "onset_times_s": onset_times.astype(float).tolist(),
        "onset_threshold_mL_s": threshold,
        "onset_rule": "up-crossing of the 5th-percentile baseline plus 10% of the episode inflow P95 range",
        "period_validation": "each onset interval is 0.5–1.5 times the HR-derived period at its midpoint",
        "validated_cycle_count": len(valid_periods),
    }


def _complete_ejection_cycle(
    inflow_part: pd.DataFrame,
    pressure_part: pd.DataFrame | None,
    hr_part: pd.DataFrame,
    cursor_s: float,
) -> dict | None:
    """Find the latest complete flow-onset-to-flow-onset beat before cursor."""
    flow_t, flow = _series_arrays(inflow_part)
    eligible = flow_t <= cursor_s
    flow_t, flow = flow_t[eligible], flow[eligible]
    if len(flow_t) < 4 or float(np.nanmax(flow)) <= 0:
        return None
    baseline = float(np.nanpercentile(flow, 5))
    p95 = float(np.nanpercentile(flow, 95))
    threshold = baseline + CYCLE_ONSET_FRACTION_OF_P95 * (p95 - baseline)
    above = flow > threshold
    onset_idx = np.flatnonzero(above & ~np.r_[False, above[:-1]])
    if len(onset_idx) < 2:
        return None
    onsets = flow_t[onset_idx]
    hr_now, _ = _interpolate_at(hr_part, cursor_s)
    expected_period = 60.0 / hr_now if hr_now and hr_now > 0 else None
    choices = []
    for left, right in zip(onsets[:-1], onsets[1:]):
        period = float(right - left)
        if expected_period and not (0.5 * expected_period <= period <= 1.5 * expected_period):
            continue
        if cursor_s - right <= MAX_WAVEFORM_AGE_PERIODS * (expected_period or period):
            choices.append((float(left), float(right), period))
    if not choices:
        return None
    start_s, end_s, period_s = choices[-1]
    flow_brackets = np.concatenate((
        [start_s], flow_t[(flow_t > start_s) & (flow_t < end_s)], [end_s]
    ))
    if len(flow_brackets) < 2 or float(np.diff(flow_brackets).max()) > MAX_INTERPOLATION_BRACKET_S:
        return None
    phase = np.arange(WAVEFORM_PHASE_SAMPLES, dtype=float) / WAVEFORM_PHASE_SAMPLES
    sample_times = start_s + phase * period_s
    flow_values = np.interp(sample_times, flow_t, flow)
    peak = float(np.max(flow_values))
    if peak <= 0:
        return None
    pressure_values = None
    if pressure_part is not None:
        pressure_t, pressure = _series_arrays(pressure_part)
        if start_s < pressure_t[0] or end_s > pressure_t[-1]:
            return None
        bracketing = np.concatenate((
            [start_s], pressure_t[(pressure_t > start_s) & (pressure_t < end_s)], [end_s]
        ))
        if len(bracketing) < 2 or float(np.diff(bracketing).max()) > MAX_INTERPOLATION_BRACKET_S:
            return None
        pressure_values = np.interp(sample_times, pressure_t, pressure)
    # Phase is anchored to the actual detected Pulse inflow onset, not reset to
    # zero at the inspection cursor. The selected source beat supplies its own
    # period; HR is a consistency check and fallback cadence when no beat exists.
    phase_cycles = ((cursor_s - start_s) / period_s) % 1.0
    return {
        "phase": phase.tolist(),
        "aortic_inflow_mL_s": flow_values.tolist(),
        "aortic_inflow_peak_mL_s": peak,
        "aortic_pressure_mmHg": pressure_values.tolist() if pressure_values is not None else None,
        "cycle_start_time_s": start_s,
        "cycle_end_time_s": end_s,
        "cycle_period_s": period_s,
        "cursor_age_after_cycle_s": cursor_s - end_s,
        "phase_cycles_at_cursor": phase_cycles,
        "source_sample_range_s": [start_s, end_s],
        "flow_onset_rule": "up-crossing of 10% of the 95th-percentile available inflow history above its 5th-percentile baseline",
        "status": "available",
    }


def renderer_state_at_cursor(
    frame: pd.DataFrame,
    source: str,
    cursor_time_s: float,
) -> dict:
    """Build a common-time, provenance-carrying Pulse renderer snapshot."""
    if str(source).lower() != "pulse":
        raise ValueError("The current renderer interface is calibrated for Pulse state exports only")
    latent = frame[(frame["layer"] == "latent") & (frame["source"].astype(str) == str(source))].copy()
    if latent.empty:
        raise ValueError(f"No latent state rows are available from source {source!r}")

    target = float(cursor_time_s)
    values: dict[str, float] = {}
    field_provenance: dict[str, dict] = {}
    supplied_fields: list[str] = []
    derived_fields: list[str] = []
    parts: dict[str, pd.DataFrame] = {}
    max_source_offset = 0.0
    for channel, part in latent.groupby("channel", sort=False):
        mapping = CHANNEL_MAP.get(str(channel))
        if mapping is None:
            continue
        output_key, allowed_units = mapping
        part = part.sort_values("time_s")
        unit = _normal_unit(part["unit"].iloc[0])
        if unit in allowed_units:
            parts[output_key] = part
        field_name = output_key
        value, provenance = _interpolate_at(part, target)
        provenance.update({"channel": str(channel), "source": str(source), "unit": str(part["unit"].iloc[0])})
        if unit not in allowed_units:
            value = None
            provenance.update({"status": "unavailable", "reason": f"unsupported unit {unit!r}"})
        if value is not None:
            value = _convert_channel_value(output_key, value, unit)
        if value is not None and output_key == "blood_volume_L" and unit in {"ml", "milliliter", "milliliters"}:
            provenance["conversion"] = "mL to L"
        if value is None:
            field_provenance[field_name] = {"value": None, "provenance": "unavailable", **provenance}
            continue
        values[field_name] = float(value)
        supplied_fields.append(field_name)
        field_provenance[field_name] = {"value": float(value), "provenance": "supplied", **provenance}
        for t in provenance.get("source_sample_times_s", []):
            max_source_offset = max(max_source_offset, abs(float(t) - target))

    if "hr_bpm" not in values:
        detail = field_provenance.get("hr_bpm", {})
        raise ValueError(f"Pulse heart rate is unavailable at {target:.3f} s: {detail.get('reason', 'no recognized HR series')}")

    if "stroke_volume_mL" not in values and "cardiac_output_L_min" in values:
        value = values["cardiac_output_L_min"] * 1000.0 / values["hr_bpm"]
        values["stroke_volume_mL"] = value
        derived_fields.append("stroke_volume_mL")
        field_provenance["stroke_volume_mL"] = {
            "value": value, "provenance": "arithmetic_derived", "inputs": ["cardiac_output_L_min", "hr_bpm"],
            "sample_time_s": target, "cursor_delta_s": 0.0,
        }

    if "svr_absolute_mmHg_s_mL" in values:
        value = values["svr_absolute_mmHg_s_mL"] / PULSE_NORMOTENSIVE_SVR_REFERENCE_MM_HG_S_PER_ML
        values["svr_relative"] = value
        derived_fields.append("svr_relative")
        field_provenance["svr_relative"] = {
            "value": value, "provenance": "reference_normalized", "inputs": ["svr_absolute_mmHg_s_mL"],
            "sample_time_s": target, "cursor_delta_s": 0.0,
            "reference_mmHg_s_mL": PULSE_NORMOTENSIVE_SVR_REFERENCE_MM_HG_S_PER_ML,
        }

    waveform = None
    inflow_part = parts.get("aortic_inflow_mL_s")
    pressure_part = parts.get("aortic_pressure_mmHg")
    hr_part = parts.get("hr_bpm")
    if inflow_part is not None and hr_part is not None:
        waveform = _complete_ejection_cycle(inflow_part, pressure_part, hr_part, target)
    if waveform is None:
        field_provenance["aortic_ejection_template"] = {
            "value": None, "provenance": "unavailable", "sample_time_s": None,
            "cursor_delta_s": None, "reason": "no fresh complete inflow cycle with valid pressure coverage",
        }
    else:
        field_provenance["aortic_ejection_template"] = {
            "value": "cycle_template", "provenance": "Pulse waveform segment",
            "sample_time_s": waveform["cycle_end_time_s"],
            "cursor_delta_s": waveform["cycle_end_time_s"] - target,
            "source_sample_range_s": waveform["source_sample_range_s"],
            "cycle_period_s": waveform["cycle_period_s"],
            "method": waveform["flow_onset_rule"],
        }
    phase_at_cursor = (
        waveform["phase_cycles_at_cursor"] if waveform is not None
        else _integrated_hr_phase(hr_part, target)
    )
    if phase_at_cursor is None:
        phase_at_cursor = 0.0
        phase_provenance = "fallback_zero_unavailable_HR_history"
    elif waveform is not None:
        phase_provenance = "Pulse aortic inflow cycle onset and measured cycle period"
    else:
        phase_provenance = "HR trajectory integration from first HR sample"
    field_provenance["visual_phase_cycles"] = {
        "value": phase_at_cursor, "provenance": phase_provenance,
        "sample_time_s": target, "cursor_delta_s": 0.0,
    }

    # Playback carries exact source timestamps per channel. The browser samples
    # each one at a shared render time and applies the same 0.1 s bracket rule.
    trajectory_series: dict[str, dict] = {}
    trajectory_sample_count = 0
    for output_key, part in parts.items():
        ordered = part.sort_values("time_s")
        unit = _normal_unit(ordered["unit"].iloc[0])
        sample_t, raw_values = _series_arrays(ordered)
        converted = [_convert_channel_value(output_key, float(v), unit) for v in raw_values]
        trajectory_sample_count += len(sample_t)
        trajectory_series[output_key] = {
            "time_s": sample_t.tolist(),
            "values": converted,
            "unit": "L" if output_key == "blood_volume_L" else str(ordered["unit"].iloc[0]),
            "source": str(source),
            "channel": str(ordered["channel"].iloc[0]),
        }
    hr_series = trajectory_series.get("hr_bpm")
    mechanical_phase = _mechanical_phase_metadata(parts.get("aortic_inflow_mL_s"), parts.get("hr_bpm"))
    if hr_series is None:
        trajectory = {"available": False, "reason": "Pulse HR trajectory is unavailable", "series": {}}
    elif trajectory_sample_count > MAX_TRAJECTORY_SAMPLES:
        trajectory = {
            "available": False,
            "reason": f"trajectory has {trajectory_sample_count} samples; playback limit is {MAX_TRAJECTORY_SAMPLES}",
            "series": {},
        }
    else:
        flow_series = trajectory_series.get("aortic_inflow_mL_s")
        positive_flow = [v for v in flow_series["values"] if v > 0] if flow_series else []
        flow_display_scale = float(np.percentile(positive_flow, 95)) if positive_flow else None
        trajectory = {
            "available": True,
            "start_time_s": float(hr_series["time_s"][0]),
            "end_time_s": float(hr_series["time_s"][-1]),
            "sample_count": trajectory_sample_count,
            "series": trajectory_series,
            "aortic_inflow_display_scale_mL_s": flow_display_scale,
            "flow_scale_method": "95th percentile of positive Pulse inflow over this episode; visual normalization only",
            "mechanical_phase": mechanical_phase,
        }

    if "hr_bpm" not in values:
        raise ValueError("The selected latent source has no recognized heart_rate in bpm")
    if values["hr_bpm"] <= 0:
        raise ValueError("Pulse heart rate must be positive to drive the renderer")
    episode_id = str(latent["episode_id"].iloc[0]) if "episode_id" in latent else str(latent["scenario"].iloc[0])
    return {
        **values,
        "time_s": target,
        "cursor_time_s": target,
        "sample_time_s": target,
        "max_field_sample_offset_s": max_source_offset,
        "freshness_limit_s": MAX_INTERPOLATION_BRACKET_S,
        "episode_id": episode_id,
        "source": str(source),
        "provided_fields": sorted(set(supplied_fields)),
        "derived_fields": sorted(set(derived_fields)),
        "field_provenance": field_provenance,
        "waveform_template": waveform,
        "phase_cycles_at_cursor": phase_at_cursor,
        "trajectory": trajectory,
        "renderer_mode": "external_state_snapshot",
        "visual_mapping": {
            "aortic_pressure_reference_mmHg": 95.0,
            "aortic_pressure_display_gain_per_mmHg": 0.00025,
            "pressure_mapping": "relative arterial distension encoding; schematic display gain, no anatomical compliance claim",
            "inflow_mapping": "relative ejection and flow-motion encoding; not local vessel velocity",
            "svr_mapping": "relative resistance/calibre encoding; not anatomical vessel radius",
        },
    }


def observed_hr_state_at_cursor(
    frame: pd.DataFrame,
    source: str,
    channel: str,
    cursor_time_s: float,
    segment: str | None = None,
) -> dict:
    """Build an observation-only renderer input; measured HR drives cadence only."""
    rows = frame[
        frame["layer"].isin(["sensor", "estimate"])
        & (frame["source"].astype(str) == str(source))
        & (frame["channel"].astype(str) == str(channel))
        & (frame["unit"].astype(str).str.lower().isin({"bpm", "beats/min", "beat/min"}))
    ].copy()
    if segment is not None and "take_id" in rows:
        rows = rows[rows["take_id"].astype(str) == str(segment)]
    if rows.empty:
        raise ValueError("No bpm observations are available for this source, channel, and segment")
    rows = rows.sort_values("time_s")
    target = float(cursor_time_s)
    times, values = _series_arrays(rows)
    right = int(np.searchsorted(times, target, side="left"))
    if right < len(times) and abs(float(times[right]) - target) <= 1e-9:
        hr = float(values[right])
        source_times = [float(times[right])]
        method = "source_sample"
        width = 0.0
    elif right == 0 or right == len(times):
        raise ValueError("Selected HR series does not cover the cursor; extrapolation is disabled")
    else:
        t0, t1 = float(times[right - 1]), float(times[right])
        width = t1 - t0
        if width <= 0 or width > MAX_OBSERVED_HR_BRACKET_S:
            raise ValueError(
                f"Selected HR samples bracket the cursor by {width:.3f} s; "
                f"the observation-mode limit is {MAX_OBSERVED_HR_BRACKET_S:.1f} s"
            )
        hr = float(np.interp(target, [t0, t1], [values[right - 1], values[right]]))
        source_times = [t0, t1]
        method = "linear_interpolation"
    if not np.isfinite(hr) or hr <= 0:
        raise ValueError("Selected observed heart rate must be finite and positive")

    episode_id = str(rows["episode_id"].iloc[0]) if "episode_id" in rows else str(rows["scenario"].iloc[0])
    series = {
        "time_s": times.tolist(),
        "values": values.tolist(),
        "unit": str(rows["unit"].iloc[0]),
        "source": str(source),
        "channel": str(channel),
    }
    return {
        "hr_bpm": hr,
        "time_s": target,
        "cursor_time_s": target,
        "sample_time_s": target,
        "max_field_sample_offset_s": 0.0,
        "freshness_limit_s": MAX_OBSERVED_HR_BRACKET_S,
        "episode_id": episode_id,
        "source": str(source),
        "provided_fields": ["hr_bpm"],
        "derived_fields": [],
        "field_provenance": {
            "hr_bpm": {
                "value": hr,
                "provenance": "observed_or_estimated_rate",
                "source": str(source),
                "channel": str(channel),
                "unit": str(rows["unit"].iloc[0]),
                "sample_time_s": target,
                "cursor_delta_s": 0.0,
                "source_sample_times_s": source_times,
                "bracket_width_s": width,
                "method": method,
                "clock_provenance": str(rows["clock_provenance"].iloc[0]) if "clock_provenance" in rows else "unspecified",
                "alignment_status": str(rows["alignment_status"].iloc[0]) if "alignment_status" in rows else "unknown",
                "processing_stage": str(rows["processing_stage"].iloc[0]) if "processing_stage" in rows else "unspecified",
            }
        },
        "waveform_template": None,
        "phase_cycles_at_cursor": 0.0,
        "trajectory": {
            "available": True,
            "start_time_s": float(times[0]),
            "end_time_s": float(times[-1]),
            "sample_count": len(times),
            "series": {"hr_bpm": series},
            "mechanical_phase": {"available": False, "reason": "no ECG phase or mechanical waveform supplied"},
        },
        "renderer_mode": "observed_hr_cadence",
        "visual_mapping": {},
        "observation_segment": str(segment) if segment is not None else None,
    }
