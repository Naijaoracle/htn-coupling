import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pcg_observation_adapter import pcg_observation_payload


def test_payload_keeps_audio_features_and_h10_reference_separate():
    rows = []
    for t in range(0, 101):
        for channel, value in [
            ("pcg_band_rms_20_400hz_ch1", 0.2 + t / 1000),
            ("pcg_band_rms_20_400hz_ch2", 0.3 + t / 1000),
        ]:
            rows.append({
                "time_s": t - 10, "session_time_s": t, "protocol_time_s": t - 60,
                "channel": channel, "value": value, "unit": "normalized_rms", "layer": "sensor",
                "source": "BOYA_BY_M1_through_stethoscope_tubing", "clock_provenance": "laptop WAV",
                "alignment_status": "derived_alignment", "processing_stage": "processed_observation_1s_band_energy_envelope",
                "derived_from": "external acoustic source WAV; waveform not included",
            })
        rows.append({
            "time_s": t - 10, "session_time_s": t, "protocol_time_s": t - 60,
            "channel": "h10_raw_ecg_rr_bpm", "value": 90, "unit": "bpm", "layer": "estimate",
            "source": "H10_raw_ECG_fixed_RR", "clock_provenance": "Android", "alignment_status": "wall_time_aligned",
        })

    result = pcg_observation_payload(pd.DataFrame(rows), 0, "Recovery-relative protocol time")
    assert result["available"] is True
    assert result["cursor_session_time_s"] == 60
    assert len(result["channels"]) == 2
    assert len(result["current_rms"]) == 2
    assert result["h10_rate_bpm"]
    assert result["h10_current"]["value"] == 90
    assert result["source_asset"] == "external acoustic source WAV"
    assert result["acoustic_features"] == []
    assert result["waveform_available"] is False
    assert "acoustic spectral-rate" in result["interpretation"]
    assert result["alignment_status"] == "derived_alignment"


def test_payload_is_unavailable_when_no_audio_features_exist():
    frame = pd.DataFrame({
        "channel": ["h10_raw_ecg_rr_bpm"], "value": [80], "unit": ["bpm"],
        "layer": ["estimate"], "source": ["H10"],
    })
    assert pcg_observation_payload(frame, 1)["available"] is False


def test_payload_passes_through_stored_acoustic_rate_features_only():
    rows = []
    for t in [0.0, 1.0, 2.0]:
        rows.append({
            "time_s": t, "channel": "pcg_dominant_event_rate", "value": 168 + t,
            "unit": "bpm", "layer": "estimate", "source": "PCG_spectral_screen",
        })
        rows.append({
            "time_s": t, "channel": "pcg_cardio_near_candidate", "value": 84 + t,
            "unit": "bpm", "layer": "diagnostic", "source": "PCG_H10_guided_candidate",
        })
    for channel in ("pcg_band_rms_20_400hz_ch1", "pcg_band_rms_20_400hz_ch2"):
        for t in [0.0, 1.0, 2.0]:
            rows.append({
                "time_s": t, "channel": channel, "value": 0.2, "unit": "normalized_rms",
                "layer": "sensor", "source": "BOYA_BY_M1", "derived_from": "test.wav",
            })
    rows.extend({
        "time_s": t, "channel": "h10_raw_ecg_rr_bpm", "value": 84,
        "unit": "bpm", "layer": "estimate", "source": "H10 RR",
    } for t in [0.0, 1.0, 2.0])
    result = pcg_observation_payload(pd.DataFrame(rows), 1.0)
    labels = {feature["label"]: feature for feature in result["acoustic_features"]}
    assert labels["Reference-blind dominant spectral component"]["current_value"] == 169
    assert labels["Cardiac-rate-near spectral candidate · H10-guided"]["reference_informed"] is True


def test_rate_export_distinguishes_stored_features_from_unavailable_window():
    rows = []
    for t in range(50):
        rows.extend([
            {"time_s": t - 10, "channel": "pcg_band_rms_20_400hz_ch1", "value": 0.2,
             "unit": "normalized_rms", "layer": "sensor", "source": "BOYA"},
            {"time_s": t - 10, "channel": "pcg_dominant_event_rate", "value": 180,
             "unit": "events/min", "layer": "estimate", "source": "PCG_Welch"},
            {"time_s": t - 10, "channel": "h10_raw_ecg_rr_bpm", "value": 90,
             "unit": "bpm", "layer": "estimate", "source": "H10"},
        ])
    result = pcg_observation_payload(pd.DataFrame(rows), 50)
    assert result["acoustic_rate_features_exported"] is True
