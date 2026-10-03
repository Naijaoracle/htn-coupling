import numpy as np
import pandas as pd
import pytest

from mechanistic_forecast import condition_pulse_ensemble


def pulse_members():
    rows = []
    for member, offset, future_level in [("fit", 0.0, 105.0), ("poor", 12.0, 130.0)]:
        for t in range(1, 61):
            rows.append({
                "episode_id": member,
                "time_s": float(t),
                "take_time_s": float(t),
                "channel": "heart_rate",
                "value": 100 + offset if t <= 30 else future_level,
                "unit": "bpm",
                "layer": "latent",
                "source": "Pulse",
                "processing_stage": "hr_constrained_pulse_ensemble_candidate_v1",
                "episode_relationship": "comparable_scenario",
                "take_id": "recovery_1",
                "conditioning_sigma_bpm": 5.0,
            })
    return pd.DataFrame(rows)


def test_context_weights_select_better_fit_without_collapsing_future_band():
    context = pd.DataFrame({"time_s": np.arange(1, 31), "value": np.full(30, 100.0)})
    result = condition_pulse_ensemble(context, pulse_members(), observation_sigma_bpm=5.0)
    assert result["member_count"] == 2
    assert result["members"].iloc[0]["candidate_episode_id"] == "fit"
    assert result["members"].iloc[0]["posterior_weight"] > 0.99
    assert result["summary"]["time_s"].tolist() == list(np.arange(31, 61, dtype=float))
    assert result["conditioning_times_s"] == [5, 10, 15, 20, 25, 30]
    assert result["conditioning_block_count"] == 6
    assert len(result["context_trajectories"]) == 60
    assert result["best_conditioning_rmse_bpm"] == 0.0


def test_untagged_pulse_trajectories_are_not_accepted_as_forecasts():
    context = pd.DataFrame({"time_s": np.arange(1, 31), "value": np.full(30, 100.0)})
    candidates = pulse_members().assign(processing_stage="latent_physiology")
    with pytest.raises(ValueError, match="explicitly tagged"):
        condition_pulse_ensemble(context, candidates, observation_sigma_bpm=5.0)


def test_conditioning_settings_must_match_predeclared_export_metadata():
    context = pd.DataFrame({"time_s": np.arange(1, 31), "value": np.full(30, 100.0)})
    with pytest.raises(ValueError, match="do not match"):
        condition_pulse_ensemble(context, pulse_members(), observation_sigma_bpm=3.0)


def test_weights_use_only_the_six_declared_block_endpoints():
    context = pd.DataFrame({"time_s": np.arange(1, 31), "value": np.full(30, 100.0)})
    candidates = pulse_members()
    baseline = condition_pulse_ensemble(context, candidates, observation_sigma_bpm=5.0)
    candidates.loc[(candidates.episode_id == "poor") & (candidates.time_s == 2), "value"] = 100.0
    changed_inside_block = condition_pulse_ensemble(context, candidates, observation_sigma_bpm=5.0)
    assert np.allclose(baseline["members"]["posterior_weight"], changed_inside_block["members"]["posterior_weight"])
    candidates.loc[(candidates.episode_id == "poor") & (candidates.time_s == 5), "value"] = 100.0
    changed_at_endpoint = condition_pulse_ensemble(context, candidates, observation_sigma_bpm=5.0)
    assert not np.allclose(baseline["members"]["posterior_weight"], changed_at_endpoint["members"]["posterior_weight"])
