from __future__ import annotations

import numpy as np
import pandas as pd


CONTEXT_SECONDS = 30
HORIZON_SECONDS = 30
MAX_INTERPOLATION_GAP_S = 4.1
TREND_LOOKBACK_SECONDS = 10


def reference_baselines(context_frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Persistence and fixed 10 s least-squares trend baselines for 31–60 s."""
    context = context_frame.sort_values("time_s")
    expected = np.arange(1, CONTEXT_SECONDS + 1, dtype=float)
    if len(context) != CONTEXT_SECONDS or not np.allclose(context["time_s"], expected):
        raise ValueError("Baseline context must be the regular 1–30 s grid")
    values = pd.to_numeric(context["value"], errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Baseline context contains non-finite values")
    future_time = np.arange(CONTEXT_SECONDS + 1, CONTEXT_SECONDS + HORIZON_SECONDS + 1, dtype=float)
    persistence = np.full(HORIZON_SECONDS, values[-1], dtype=float)
    trend_times = expected[-TREND_LOOKBACK_SECONDS:]
    slope, intercept = np.polyfit(trend_times, values[-TREND_LOOKBACK_SECONDS:], 1)
    trend = intercept + slope * future_time
    return {
        "persistence": pd.DataFrame({"time_s": future_time, "value": persistence}),
        "linear_trend": pd.DataFrame({"time_s": future_time, "value": trend}),
    }


def prepare_holdout(frame: pd.DataFrame, series_id: str, take_id: str) -> dict:
    """Prepare one take as 30 s TimesFM context plus a separate 30 s truth set.

    Only the `context_frame` returned here may be passed to a forecaster. The
    held-out observations are returned separately for plotting and scoring.
    """
    eligible = frame[
        frame["unit"].astype(str).str.lower().eq("bpm")
        & frame["layer"].astype(str).isin(["sensor", "estimate"])
        & frame["take_id"].astype(str).eq(str(take_id))
        & (frame["channel"].astype(str) + " | " + frame["source"].astype(str)).eq(series_id)
    ].copy()
    descriptor = (eligible["channel"].astype(str) + " " + eligible["source"].astype(str)).str.lower()
    eligible = eligible[~descriptor.str.contains("diagnostic|candidate|guided|surrogate", regex=True)]
    if eligible.empty:
        raise ValueError("No reference-blind sensor/estimate bpm series exists for this take")

    if "take_time_s" in eligible.columns and pd.to_numeric(eligible["take_time_s"], errors="coerce").notna().all():
        eligible["take_relative_s"] = pd.to_numeric(eligible["take_time_s"], errors="coerce")
    else:
        eligible["take_relative_s"] = pd.to_numeric(eligible["time_s"], errors="coerce")
        eligible["take_relative_s"] -= eligible["take_relative_s"].min()
    eligible["value"] = pd.to_numeric(eligible["value"], errors="coerce")
    eligible = eligible.dropna(subset=["take_relative_s", "value"]).sort_values("take_relative_s")
    eligible = eligible.drop_duplicates("take_relative_s", keep="last")

    grid = np.arange(1, CONTEXT_SECONDS + 1, dtype=float)
    times = eligible["take_relative_s"].to_numpy(dtype=float)
    values = eligible["value"].to_numpy(dtype=float)
    context_values = np.full(len(grid), np.nan, dtype=float)
    for i, point in enumerate(grid):
        right = int(np.searchsorted(times, point, side="left"))
        if right < len(times) and np.isclose(times[right], point, atol=1e-8):
            context_values[i] = values[right]
            continue
        if right == 0 or right == len(times):
            continue
        left = right - 1
        gap = times[right] - times[left]
        if gap <= MAX_INTERPOLATION_GAP_S:
            fraction = (point - times[left]) / gap
            context_values[i] = values[left] + fraction * (values[right] - values[left])

    if not np.isfinite(context_values).all():
        missing = int((~np.isfinite(context_values)).sum())
        raise ValueError(
            f"Only {CONTEXT_SECONDS - missing}/{CONTEXT_SECONDS} one-second context points can be formed "
            f"without extrapolation or bridging a gap over {MAX_INTERPOLATION_GAP_S:.1f} s"
        )

    origin = float(CONTEXT_SECONDS)
    stop = float(CONTEXT_SECONDS + HORIZON_SECONDS)
    context_frame = pd.DataFrame({
        "time_s": grid,
        "channel": str(eligible["channel"].iloc[0]),
        "value": context_values,
        "unit": "bpm",
        "layer": str(eligible["layer"].iloc[0]),
        "source": str(eligible["source"].iloc[0]),
    })
    all_actual = eligible[eligible["take_relative_s"].between(0.0, stop)].copy()
    all_actual["plot_time_s"] = all_actual["take_relative_s"]
    context_actual = all_actual[all_actual["plot_time_s"] <= origin].copy()
    # Evaluation starts at second 31; samples between 30 and 31 are visible on
    # the full measurement trace but precede the forecast horizon.
    future_actual = all_actual[all_actual["plot_time_s"].between(origin + 1.0, stop, inclusive="both")].copy()
    return {
        "context_frame": context_frame,
        "context_actual": context_actual,
        "future_actual": future_actual,
        "all_actual": all_actual,
        "forecast_origin_s": origin,
        "target_end_s": stop,
        "context_points": int(len(context_frame)),
        "heldout_observations": int(len(future_actual)),
        "target_channel": str(eligible["channel"].iloc[0]),
        "target_source": str(eligible["source"].iloc[0]),
    }


def score_forecast(forecast: pd.DataFrame, future_actual: pd.DataFrame) -> tuple[pd.DataFrame, dict | None]:
    """Score forecasts only at measured held-out timestamps; never extrapolate truth."""
    if forecast.empty or future_actual.empty:
        return pd.DataFrame(), None
    fx = pd.to_numeric(forecast["time_s"], errors="coerce").to_numpy(dtype=float)
    fy = pd.to_numeric(forecast["value"], errors="coerce").to_numpy(dtype=float)
    low = pd.to_numeric(forecast["low_80"], errors="coerce").to_numpy(dtype=float)
    high = pd.to_numeric(forecast["high_80"], errors="coerce").to_numpy(dtype=float)
    obs = future_actual[["plot_time_s", "value"]].copy()
    obs = obs.sort_values("plot_time_s")
    obs = obs[obs["plot_time_s"].between(float(np.min(fx)), float(np.max(fx)))]
    if obs.empty:
        return pd.DataFrame(), None
    tx = obs["plot_time_s"].to_numpy(dtype=float)
    actual = obs["value"].to_numpy(dtype=float)
    predicted = np.interp(tx, fx, fy)
    frame = pd.DataFrame({
        "time_s": tx,
        "observed": actual,
        "forecast": predicted,
        "low_80": np.interp(tx, fx, low),
        "high_80": np.interp(tx, fx, high),
        "error": predicted - actual,
    })
    error = frame["error"].to_numpy(dtype=float)
    metrics = {
        "n": int(len(frame)),
        "mae_bpm": float(np.mean(np.abs(error))),
        "rmse_bpm": float(np.sqrt(np.mean(error**2))),
        "coverage_80_pct": float(np.mean(frame["observed"].between(frame["low_80"], frame["high_80"])) * 100.0),
        "forecast_change_bpm": float(frame["forecast"].iloc[-1] - frame["forecast"].iloc[0]),
        "observed_change_bpm": float(frame["observed"].iloc[-1] - frame["observed"].iloc[0]),
        "change_error_bpm": float((frame["forecast"].iloc[-1] - frame["forecast"].iloc[0]) - (frame["observed"].iloc[-1] - frame["observed"].iloc[0])),
    }
    return frame, metrics


def score_point_forecast(forecast: pd.DataFrame, future_actual: pd.DataFrame) -> tuple[pd.DataFrame, dict | None]:
    """Score a point forecast only at measured held-out timestamps."""
    if forecast.empty or future_actual.empty:
        return pd.DataFrame(), None
    fx = pd.to_numeric(forecast["time_s"], errors="coerce").to_numpy(dtype=float)
    fy = pd.to_numeric(forecast["value"], errors="coerce").to_numpy(dtype=float)
    obs = future_actual[["plot_time_s", "value"]].sort_values("plot_time_s")
    obs = obs[obs["plot_time_s"].between(float(np.min(fx)), float(np.max(fx)))]
    if obs.empty:
        return pd.DataFrame(), None
    tx = obs["plot_time_s"].to_numpy(dtype=float)
    actual = obs["value"].to_numpy(dtype=float)
    predicted = np.interp(tx, fx, fy)
    error = predicted - actual
    result = pd.DataFrame({"time_s": tx, "observed": actual, "forecast": predicted, "error": error})
    return result, {
        "n": int(len(result)),
        "mae_bpm": float(np.mean(np.abs(error))),
        "rmse_bpm": float(np.sqrt(np.mean(error**2))),
        "forecast_change_bpm": float(predicted[-1] - predicted[0]),
        "observed_change_bpm": float(actual[-1] - actual[0]),
        "change_error_bpm": float((predicted[-1] - predicted[0]) - (actual[-1] - actual[0])),
    }
