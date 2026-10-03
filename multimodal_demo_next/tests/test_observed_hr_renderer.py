import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pulse_state_adapter import observed_hr_state_at_cursor


def observed_frame() -> pd.DataFrame:
    times = np.arange(0.0, 10.0, 1.0)
    return pd.DataFrame({
        "time_s": times,
        "channel": "h10_raw_ecg_rr_bpm",
        "value": 120.0 - times,
        "unit": "bpm",
        "layer": "estimate",
        "source": "H10_raw_ECG_fixed_5-25Hz_RR",
        "scenario": "real_recovery",
        "episode_id": "real_recovery",
        "take_id": "continuous_H10",
        "clock_provenance": "H10 Android wall time",
        "alignment_status": "wall_time_aligned",
        "processing_stage": "derived_estimate",
    })


def test_observed_hr_payload_drives_only_cadence_and_carries_provenance():
    state = observed_hr_state_at_cursor(
        observed_frame(), "H10_raw_ECG_fixed_5-25Hz_RR", "h10_raw_ecg_rr_bpm", 4.5, "continuous_H10"
    )
    assert state["hr_bpm"] == pytest.approx(115.5)
    assert state["renderer_mode"] == "observed_hr_cadence"
    assert state["provided_fields"] == ["hr_bpm"]
    assert state["derived_fields"] == []
    assert set(state["trajectory"]["series"]) == {"hr_bpm"}
    assert state["trajectory"]["mechanical_phase"]["available"] is False
    assert state["field_provenance"]["hr_bpm"]["alignment_status"] == "wall_time_aligned"


def test_observed_hr_renderer_rejects_gaps_and_extrapolation():
    frame = observed_frame()
    frame = frame[~frame["time_s"].between(4, 6)]
    with pytest.raises(ValueError, match="bracket"):
        observed_hr_state_at_cursor(frame, "H10_raw_ECG_fixed_5-25Hz_RR", "h10_raw_ecg_rr_bpm", 5.0, "continuous_H10")
    with pytest.raises(ValueError, match="does not cover"):
        observed_hr_state_at_cursor(observed_frame(), "H10_raw_ECG_fixed_5-25Hz_RR", "h10_raw_ecg_rr_bpm", 12.0, "continuous_H10")
