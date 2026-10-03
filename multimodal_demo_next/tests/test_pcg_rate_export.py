import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import wavfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pcg_rate_export import derive_pcg_rate_rows


def test_offline_export_writes_blind_and_reference_guided_numeric_features(tmp_path):
    fs = 2000
    duration_s = 40
    time = np.arange(fs * duration_s) / fs
    # An amplitude-modulated acoustic carrier with clear 90 and 180 events/min.
    envelope = 0.5 + 0.3 * np.sin(2 * np.pi * 1.5 * time) + 0.7 * np.sin(2 * np.pi * 3.0 * time)
    waveform = np.asarray(12000 * envelope * np.sin(2 * np.pi * 90 * time), dtype=np.int16)
    wav_path = tmp_path / "synthetic_audio.wav"
    wavfile.write(wav_path, fs, waveform)

    timeline = pd.DataFrame([
        {"time_s": t - 20, "channel": "pcg_band_rms_20_400hz_ch1", "value": 0.2,
         "unit": "normalized_rms", "layer": "sensor", "source": "BOYA"}
        for t in range(duration_s)
    ] + [
        {"time_s": t - 20, "channel": "h10_raw_ecg_rr_bpm", "value": 90,
         "unit": "bpm", "layer": "estimate", "source": "H10"}
        for t in range(duration_s)
    ])

    features = derive_pcg_rate_rows(wav_path, timeline)
    assert set(features.channel) == {
        "pcg_dominant_event_rate", "pcg_secondary_event_rate", "pcg_cardio_near_candidate"
    }
    assert set(features.layer) == {"estimate"}
    assert "diagnostic" in features.loc[features.channel.eq("pcg_cardio_near_candidate"), "source"].iloc[0]
    assert "external acoustic source WAV" in features.derived_from.iloc[0]
    assert not any("waveform" in column.lower() or "samples" in column.lower() for column in features.columns)
    dominant = features[features.channel.eq("pcg_dominant_event_rate")].value.median()
    guided = features[features.channel.eq("pcg_cardio_near_candidate")].value.median()
    assert abs(dominant - 180) < 8
    assert abs(guided - 90) < 8
