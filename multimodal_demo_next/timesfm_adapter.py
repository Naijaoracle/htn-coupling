from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd


def regularize_bpm(frame: pd.DataFrame, series_ids: list[str], context_points: int):
    """Align selected channel/source series to one shared one-second grid."""
    selected = frame[frame["unit"] == "bpm"].copy()
    selected["series_id"] = selected["channel"].astype(str) + " | " + selected["source"].astype(str)
    selected = selected[selected["series_id"].isin(series_ids)]
    if selected.empty:
        raise ValueError("No selected bpm channels are present")

    # Use only the temporal intersection: independently zeroing or padding
    # disjoint channel ranges would manufacture false multivariate alignment.
    ranges = selected.groupby("series_id")["time_s"].agg(["min", "max"])
    common_start = float(ranges["min"].max())
    common_end = float(ranges["max"].min())
    grid_origin = float(np.floor(ranges["min"].min()))
    if common_end <= common_start:
        raise ValueError("Selected bpm series have no shared time interval")
    first_second = int(np.floor(common_start - grid_origin))
    last_second = int(np.floor(common_end - grid_origin))
    common_seconds = range(first_second, last_second + 1)
    series = []
    names = []
    for name in series_ids:
        part = selected.loc[selected["series_id"] == name, ["time_s", "value"]]
        if part.empty:
            continue
        indexed = part.assign(second=np.floor(part["time_s"] - grid_origin).astype(int))
        values = indexed.groupby("second")["value"].mean()
        full = values.reindex(common_seconds)
        # The exploratory spectral series are emitted every four seconds;
        # allow exactly the three intervening one-second grid points.
        full = full.interpolate(limit=3, limit_area="inside")
        if full.isna().any():
            raise ValueError(f"{name} has gaps larger than the supported four-second cadence")
        if len(full) < context_points:
            continue
        values_np = full.iloc[-context_points:].to_numpy(dtype=np.float32)
        mu = float(np.mean(values_np))
        sigma = float(np.std(values_np))
        if sigma < 1e-6:
            sigma = 1.0
        series.append((values_np - mu) / sigma)
        names.append((name, mu, sigma))

    if not series:
        raise ValueError("No selected channels have enough usable history")
    return np.stack(series).astype(np.float32), names, grid_origin + last_second


def shared_history_points(frame: pd.DataFrame, series_ids: list[str]) -> tuple[int, float | None]:
    """Return whole-second points available to every selected series up to its end."""
    selected = frame[frame["unit"] == "bpm"].copy()
    selected["series_id"] = selected["channel"].astype(str) + " | " + selected["source"].astype(str)
    selected = selected[selected["series_id"].isin(series_ids)]
    if selected.empty:
        return 0, None
    ranges = selected.groupby("series_id")["time_s"].agg(["min", "max"])
    common_start = float(ranges["min"].max())
    common_end = float(ranges["max"].min())
    if common_end < common_start:
        return 0, None
    grid_origin = float(np.floor(ranges["min"].min()))
    first = int(np.floor(common_start - grid_origin))
    last = int(np.floor(common_end - grid_origin))
    return max(0, last - first + 1), grid_origin + last


@lru_cache(maxsize=1)
def _load_model():
    """Load TimesFM once per local dashboard process."""
    try:
        from timesfm3 import ModelConfig, TimesFM3Evaluator
    except ImportError as exc:
        raise RuntimeError("Install the optional dependency with: pip install -e '.[cuda]'") from exc

    config = ModelConfig(
        checkpoint_path="google/timesfm-3.0-pytorch",
        per_core_batch_size=1,
        device="cuda",
    )
    return TimesFM3Evaluator(config)


def forecast_bpm(frame: pd.DataFrame, series_ids: list[str], horizon: int, context_points: int = 128):
    """Forecast selected BPM series jointly on CUDA."""
    matrix, metadata, last_t = regularize_bpm(frame, series_ids, context_points)
    model = _load_model()
    outputs = list(
        model.predict_batch(
            contexts=[matrix],
            horizon=horizon,
            return_quantiles=True,
            use_symmetric_averaging=False,
        )
    )
    output = outputs[0]
    point = np.asarray(output.forecast, dtype=np.float32)
    quantiles = np.asarray(output.quantiles, dtype=np.float32)
    if point.ndim == 1:
        point = point[None, :]
    if quantiles.ndim == 2:
        quantiles = quantiles[None, :, :]

    rows = []
    for i, (name, mu, sigma) in enumerate(metadata):
        median = point[i] * sigma + mu
        # Published model returns deciles 0.1...0.9; display central 80% interval.
        low = quantiles[i, :, 0] * sigma + mu
        high = quantiles[i, :, 8] * sigma + mu
        for step in range(horizon):
            rows.append({
                "time_s": last_t + step + 1,
                "channel": name,
                "value": float(median[step]),
                "low_80": float(low[step]),
                "high_80": float(high[step]),
                "unit": "bpm",
                "layer": "forecast",
                "source": "TimesFM-3",
                "forecast_origin_time_s": float(last_t),
            })
    return pd.DataFrame(rows)
