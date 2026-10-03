from __future__ import annotations

import numpy as np
import pandas as pd

from forecast_evaluation import CONTEXT_SECONDS, HORIZON_SECONDS, MAX_INTERPOLATION_GAP_S


def _sample_on_grid(rows: pd.DataFrame, grid: np.ndarray) -> np.ndarray | None:
    time_column = "take_time_s" if "take_time_s" in rows else "time_s"
    times = pd.to_numeric(rows[time_column], errors="coerce").to_numpy(dtype=float)
    values = pd.to_numeric(rows["value"], errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(times) & np.isfinite(values)
    times, values = times[valid], values[valid]
    order = np.argsort(times)
    times, values = times[order], values[order]
    times, unique = np.unique(times, return_index=True)
    values = values[unique]
    if len(times) < 2 or grid.min() < times.min() or grid.max() > times.max():
        return None
    right = np.searchsorted(times, grid, side="left")
    exact = (right < len(times)) & np.isclose(times[np.minimum(right, len(times) - 1)], grid, atol=1e-8)
    sampled = np.interp(grid, times, values)
    gaps = np.diff(times)
    left_idx = np.clip(right - 1, 0, len(times) - 2)
    if np.any((~exact) & (gaps[left_idx] > MAX_INTERPOLATION_GAP_S)):
        return None
    return sampled


def condition_pulse_ensemble(
    h10_context: pd.DataFrame,
    pulse_candidates: pd.DataFrame,
    *,
    observation_sigma_bpm: float,
) -> dict:
    """Weight predeclared Pulse HR trajectories from H10 context only.

    Candidate rows must be tagged by the exporter as
    `hr_constrained_pulse_ensemble_candidate_v1` and each candidate must have
    a unique `episode_id`. Equal prior weights and independent Gaussian errors
    at the fixed five-second context blocks are assumed.
    """
    if observation_sigma_bpm <= 0:
        raise ValueError("observation_sigma_bpm must be positive")
    required = {
        "episode_id", "channel", "value", "unit", "source", "layer", "processing_stage",
        "episode_relationship", "take_id", "conditioning_sigma_bpm",
    }
    if not required.issubset(pulse_candidates.columns):
        raise ValueError("Pulse candidate rows lack required provenance fields")
    candidates = pulse_candidates[
        pulse_candidates["source"].astype(str).eq("Pulse")
        & pulse_candidates["channel"].astype(str).eq("heart_rate")
        & pulse_candidates["unit"].astype(str).str.lower().eq("bpm")
        & pulse_candidates["layer"].astype(str).eq("latent")
        & pulse_candidates["processing_stage"].astype(str).eq("hr_constrained_pulse_ensemble_candidate_v1")
        & pulse_candidates["episode_relationship"].astype(str).eq("comparable_scenario")
    ].copy()
    if candidates.empty:
        raise ValueError("No explicitly tagged HR-constrained Pulse candidate trajectories are present")
    declared_sigma = pd.to_numeric(candidates["conditioning_sigma_bpm"], errors="coerce").dropna().unique()
    if len(declared_sigma) != 1:
        raise ValueError("Pulse rows must carry one predeclared conditioning sigma")
    if not np.isclose(declared_sigma[0], observation_sigma_bpm):
        raise ValueError("Conditioning settings do not match the values declared on the Pulse rows")

    context_grid = np.arange(1, CONTEXT_SECONDS + 1, dtype=float)
    future_grid = np.arange(CONTEXT_SECONDS + 1, CONTEXT_SECONDS + HORIZON_SECONDS + 1, dtype=float)
    observed = h10_context.sort_values("time_s")
    if len(observed) != CONTEXT_SECONDS or not np.allclose(observed["time_s"], context_grid):
        raise ValueError("H10 context must contain exactly the regular 1–30 s conditioning grid")
    observed_values = pd.to_numeric(observed["value"], errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(observed_values).all():
        raise ValueError("H10 context contains non-finite values")

    trajectories = []
    ids = []
    for member, rows in candidates.groupby("episode_id", sort=False):
        context_values = _sample_on_grid(rows, context_grid)
        future_values = _sample_on_grid(rows, future_grid)
        if context_values is None or future_values is None:
            continue
        ids.append(str(member))
        trajectories.append((context_values, future_values))
    if len(trajectories) < 2:
        raise ValueError("At least two complete Pulse candidate trajectories are required for an ensemble")

    residuals = np.stack([context - observed_values for context, _ in trajectories])
    block_times = np.arange(5, CONTEXT_SECONDS + 1, 5, dtype=int)
    block_residuals = residuals[:, block_times - 1]
    log_weight = -0.5 * np.sum(block_residuals**2, axis=1) / observation_sigma_bpm**2
    log_weight -= np.max(log_weight)
    weights = np.exp(log_weight)
    weights /= weights.sum()
    future = np.stack([trajectory[1] for trajectory in trajectories])
    context = np.stack([trajectory[0] for trajectory in trajectories])

    def weighted_quantile(values: np.ndarray, quantile: float) -> np.ndarray:
        result = np.empty(values.shape[1], dtype=float)
        for col in range(values.shape[1]):
            order = np.argsort(values[:, col])
            sorted_values = values[order, col]
            cumulative = np.cumsum(weights[order])
            result[col] = np.interp(quantile, cumulative, sorted_values)
        return result

    summary = pd.DataFrame({
        "time_s": future_grid,
        "low_80": weighted_quantile(future, 0.10),
        "median": weighted_quantile(future, 0.50),
        "high_80": weighted_quantile(future, 0.90),
    })
    member_scores = pd.DataFrame({
        "candidate_episode_id": ids,
        "conditioning_block_rmse_bpm": np.sqrt(np.mean(block_residuals**2, axis=1)),
        "posterior_weight": weights,
    }).sort_values("posterior_weight", ascending=False, ignore_index=True)
    context_trajectories = pd.DataFrame([
        {
            "candidate_episode_id": member,
            "time_s": float(time_s),
            "value": float(value),
        }
        for member, values in zip(ids, context)
        for time_s, value in zip(context_grid, values)
    ])
    return {
        "summary": summary,
        "members": member_scores,
        "context_trajectories": context_trajectories,
        "member_count": len(trajectories),
        "effective_sample_size": float(1.0 / np.sum(weights**2)),
        "best_conditioning_rmse_bpm": float(np.min(np.sqrt(np.mean(block_residuals**2, axis=1)))),
        "observation_sigma_bpm": float(observation_sigma_bpm),
        "conditioning_times_s": block_times.tolist(),
        "conditioning_block_count": int(len(block_times)),
    }
