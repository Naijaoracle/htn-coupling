import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rppg_observation_adapter import rppg_observation_payload


def test_payload_uses_recorded_rgb_and_labels_rate_sources():
    rows = []
    times = np.arange(5, dtype=float)
    for channel, base, source in [
        ("camera_mean_red", 100.0, "iPad8_RGB"),
        ("camera_mean_green", 80.0, "iPad8_RGB"),
        ("camera_mean_blue", 60.0, "iPad8_RGB"),
    ]:
        for t, value in zip(times, base + np.array([0, 1, -1, 2, 0])):
            rows.append({"time_s": 100 + t, "take_time_s": t, "take_id": "rest_1", "scenario": "pilot",
                         "episode_id": "pilot", "channel": channel, "value": value, "unit": "a.u.",
                         "layer": "sensor", "source": source, "clock_provenance": "iPad clock",
                         "alignment_status": "master_clock"})
    for channel, source, values in [
        ("h10_raw_ecg_rr_bpm", "H10_raw_ECG_fixed", [80, 81, 82]),
        ("chrom_blind_winner_bpm", "iPad8_CHROM_blind", [45, 80, 79]),
    ]:
        for t, value in zip([0.0, 2.0, 4.0], values):
            rows.append({"time_s": 100 + t, "take_time_s": t, "take_id": "rest_1", "scenario": "pilot",
                         "episode_id": "pilot", "channel": channel, "value": value, "unit": "bpm",
                         "layer": "estimate", "source": source, "clock_provenance": "source clock",
                         "alignment_status": "wall_time_aligned"})
    payload = rppg_observation_payload(pd.DataFrame(rows), "rest_1", 102.0)
    assert payload["mode"] == "real_observation"
    assert payload["cursor_inside_take"] is True
    assert set(payload["rgb"]) == {"red", "green", "blue"}
    assert payload["rgb"]["red"]["nearest_raw"] == 99.0
    assert payload["input_samples"]
    assert set(payload["input_samples"][0]) == {"time_s", "red", "green", "blue"}
    assert any(row["label"] == "H10 reference rate" for row in payload["rates"])
    assert any(row["label"] == "CHROM blind winner" for row in payload["rates"])
    assert payload["rgb_plot_svg"].count("<path") == 3
    assert payload["rate_plot_svg"].count("<path") == 2
    assert "H10 reference rate" in payload["rate_legend_html"]
    assert "fractional change" in payload["rgb_transform"]


def test_renderer_static_plot_markers_match_app_injection_points():
    root = Path(__file__).resolve().parents[1]
    renderer = (root / "assets" / "rppg-observation-renderer.html").read_text()
    app = (root / "app.py").read_text()
    for marker in (
        "<!--__INPUT_ROWS__-->",
        "<!--__RGB_PLOT_SVG__-->",
        "<!--__RATE_PLOT_SVG__-->",
        "<!--__RATE_LEGEND__-->",
    ):
        assert marker in renderer
        assert marker in app


def test_payload_does_not_claim_cursor_is_inside_another_take():
    rows = pd.DataFrame({
        "time_s": [10.0, 10.0, 10.0], "take_time_s": [0.0, 0.0, 0.0], "take_id": ["rest_1"] * 3,
        "scenario": ["pilot"] * 3, "episode_id": ["pilot"] * 3,
        "channel": ["camera_mean_red", "camera_mean_green", "camera_mean_blue"],
        "value": [100.0, 80.0, 60.0], "unit": ["a.u."] * 3, "layer": ["sensor"] * 3,
        "source": ["iPad8_RGB"] * 3, "clock_provenance": ["iPad"] * 3,
        "alignment_status": ["master_clock"] * 3,
    })
    payload = rppg_observation_payload(rows, "rest_1", 30.0)
    assert payload["cursor_inside_take"] is False
    assert payload["cursor_local_time_s"] is None
