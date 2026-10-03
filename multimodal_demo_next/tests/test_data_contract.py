from io import BytesIO

import pandas as pd
import pytest

from data_contract import load_observations


def test_multiple_pulse_members_can_share_times_when_episode_ids_differ():
    rows = []
    for member, value in [("candidate_1", 100.0), ("candidate_2", 105.0)]:
        rows.append({
            "time_s": 1.0, "channel": "heart_rate", "value": value, "unit": "bpm",
            "layer": "latent", "source": "Pulse", "scenario": "session",
            "episode_id": member, "take_id": "recovery_1",
        })
    frame = load_observations(BytesIO(pd.DataFrame(rows).to_csv(index=False).encode()))
    assert len(frame) == 2


def test_ensemble_candidates_can_share_episode_and_times_when_candidate_ids_differ():
    rows = []
    for candidate, value in [("candidate_1", 100.0), ("candidate_2", 105.0)]:
        rows.append({
            "time_s": 1.0, "channel": "heart_rate", "value": value, "unit": "bpm",
            "layer": "latent", "source": "Pulse", "scenario": "session",
            "episode_id": "pulse_ensemble", "candidate_id": candidate,
            "take_id": "recovery_1",
        })
    frame = load_observations(BytesIO(pd.DataFrame(rows).to_csv(index=False).encode()))
    assert len(frame) == 2


def test_duplicate_timestamp_within_same_episode_is_rejected():
    row = {
        "time_s": 1.0, "channel": "heart_rate", "value": 100.0, "unit": "bpm",
        "layer": "latent", "source": "Pulse", "scenario": "session",
        "episode_id": "candidate_1", "take_id": "recovery_1",
    }
    data = pd.DataFrame([row, row]).to_csv(index=False).encode()
    with pytest.raises(ValueError, match="Duplicate time_s"):
        load_observations(BytesIO(data))
