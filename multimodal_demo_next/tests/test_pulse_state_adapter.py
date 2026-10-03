import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pulse_state_adapter import renderer_state_at_cursor


def pulse_frame(duration_s: float = 3.0, step_s: float = 0.02) -> pd.DataFrame:
    times = np.arange(0.0, duration_s + step_s / 2, step_s)
    phase = np.mod(times, 0.84)
    ejection = ((phase >= 0.25) & (phase <= 0.48)).astype(float)
    # Smooth enough for a basic fixture while preserving thresholded ejection onsets.
    inflow = 400.0 * ejection * np.sin(np.clip((phase - 0.25) / 0.23, 0, 1) * np.pi)
    pressure = 95.0 + 20.0 * np.sin(2 * np.pi * times / 0.84)
    channels = {
        "heart_rate": (np.full_like(times, 60.0 / 0.84), "bpm"),
        "cardiac_output": (np.full_like(times, 5.0), "L/min"),
        "mean_arterial_pressure": (np.full_like(times, 95.0), "mmHg"),
        "aortic_inflow": (inflow, "mL/s"),
        "aortic_pressure": (pressure, "mmHg"),
        "systemic_vascular_resistance": (np.full_like(times, 0.939706), "mmHg s/mL"),
    }
    return pd.concat([
        pd.DataFrame({
            "time_s": times, "channel": channel, "value": values, "unit": unit,
            "layer": "latent", "source": "Pulse", "scenario": "test_cycle",
            "episode_id": "test_cycle",
        })
        for channel, (values, unit) in channels.items()
    ], ignore_index=True)


def test_common_time_interpolation_and_cycle_template_provenance():
    frame = pulse_frame()
    state = renderer_state_at_cursor(frame, "Pulse", 2.715)

    assert state["hr_bpm"] == pytest.approx(60.0 / 0.84)
    assert state["field_provenance"]["hr_bpm"]["sample_time_s"] == pytest.approx(2.715)
    assert state["field_provenance"]["hr_bpm"]["cursor_delta_s"] == 0.0
    assert state["field_provenance"]["hr_bpm"]["method"] == "linear_interpolation"
    assert state["field_provenance"]["aortic_pressure_mmHg"]["method"] == "linear_interpolation"
    assert "stroke_volume_mL" in state["derived_fields"]
    assert "stroke_volume_mL" not in state["provided_fields"]
    assert "svr_relative" in state["derived_fields"]

    template = state["waveform_template"]
    assert template is not None
    assert len(template["aortic_inflow_mL_s"]) == 128
    assert len(template["aortic_pressure_mmHg"]) == 128
    assert template["cycle_end_time_s"] <= 2.715
    assert template["cursor_age_after_cycle_s"] <= 1.5 * 0.84
    assert state["field_provenance"]["aortic_ejection_template"]["source_sample_range_s"] == [
        template["cycle_start_time_s"], template["cycle_end_time_s"]
    ]
    assert state["trajectory"]["available"] is True
    assert state["trajectory"]["series"]["aortic_inflow_mL_s"]["time_s"]
    assert state["trajectory"]["mechanical_phase"]["available"] is True
    assert state["trajectory"]["mechanical_phase"]["validated_cycle_count"] >= 2
    assert state["phase_cycles_at_cursor"] == pytest.approx(template["phase_cycles_at_cursor"])


def test_too_wide_hr_source_gap_fails_closed():
    frame = pulse_frame()
    hr_times = frame.loc[frame.channel == "heart_rate", "time_s"]
    remove = (frame.channel == "heart_rate") & frame.time_s.between(1.30, 1.42)
    frame = frame.loc[~remove]
    # Cursor is inside the deliberately widened bracket, so HR must not be held or extrapolated.
    with pytest.raises(ValueError, match="source bracket exceeds"):
        renderer_state_at_cursor(frame, "Pulse", 1.36)


def test_flat_inflow_is_reported_as_unavailable_waveform():
    frame = pulse_frame()
    frame.loc[frame.channel == "aortic_inflow", "value"] = 0.0
    state = renderer_state_at_cursor(frame, "Pulse", 2.72)
    assert state["waveform_template"] is None
    assert state["field_provenance"]["aortic_ejection_template"]["provenance"] == "unavailable"
    assert state["trajectory"]["mechanical_phase"]["available"] is False
