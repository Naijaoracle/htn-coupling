import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import wavfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from session_timeline_export import _pcg_envelope_rows, combine_take_intervals


def test_combines_iPad_master_takes_without_filling_gaps(tmp_path):
    source = tmp_path / "takes.csv"
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "session.csv"
    output_manifest = tmp_path / "session_manifest.json"
    pd.DataFrame({
        "time_s": [0.0, 1.0, 0.0, 1.0],
        "channel": ["rgb", "rgb", "h10", "h10"],
        "value": [0.1, 0.2, 70.0, 71.0],
        "unit": ["a.u.", "a.u.", "bpm", "bpm"],
        "layer": ["sensor", "sensor", "estimate", "estimate"],
        "source": ["iPad8_RGB", "iPad8_RGB", "H10", "H10"],
        "scenario": ["rest_1", "rest_1", "recovery_1", "recovery_1"],
        "episode_id": ["rest_1", "rest_1", "recovery_1", "recovery_1"],
        "clock_provenance": ["iPad", "iPad", "H10", "H10"],
        "alignment_status": ["master_clock", "master_clock", "wall_time_aligned", "wall_time_aligned"],
        "episode_relationship": ["same_episode"] * 4,
    }).to_csv(source, index=False)
    manifest.write_text(json.dumps({"intervals": [
        {"scenario": "rest_1", "iPad_start_wall_ms": 10000, "duration_s": 2.0},
        {"scenario": "recovery_1", "iPad_start_wall_ms": 20000, "duration_s": 2.0},
    ]}))

    frame = combine_take_intervals(source, manifest, output, output_manifest)
    assert set(frame.scenario) == {"real_session_demo"}
    assert set(frame.episode_id) == {"real_session_demo"}
    assert set(frame.take_id) == {"rest_1", "recovery_1"}
    assert set(frame.take_time_s) == {0.0, 1.0}
    recovery = frame[frame.take_id == "recovery_1"]
    assert recovery.time_s.min() == 10.0
    assert recovery.time_s.max() == 11.0
    assert frame.time_s.max() - frame.time_s.min() == 11.0
    saved_manifest = json.loads(output_manifest.read_text())
    assert "No iPad samples are invented" in saved_manifest["session_timeline"]["gaps"]


def test_pcg_export_is_feature_only_and_marks_derived_alignment(tmp_path):
    path = tmp_path / "synthetic_audio.wav"
    fs = 2000
    t = np.arange(2 * fs, dtype=float) / fs
    audio = (1000 * np.sin(2 * np.pi * 100 * t)).astype("int16")
    wavfile.write(path, fs, np.column_stack((audio, audio)))
    os.utime(path, (102.5, 102.5))

    rows = _pcg_envelope_rows(path, origin_s=100.0, audio_offset_to_esp_stop_s=0.11)
    frame = pd.concat(rows, ignore_index=True)
    assert len(frame) == 4
    assert set(frame.layer) == {"sensor"}
    assert set(frame.alignment_status) == {"derived_alignment"}
    assert set(frame.processing_stage) == {"processed_observation_1s_band_energy_envelope"}
    assert not any("raw_audio" in str(value) for value in frame.channel)
