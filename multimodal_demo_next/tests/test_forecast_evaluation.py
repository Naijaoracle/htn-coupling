import numpy as np
import pandas as pd

from forecast_evaluation import prepare_holdout, reference_baselines, score_forecast, score_point_forecast


def sample_frame():
    times = np.arange(0.25, 60.0, 0.5)
    return pd.DataFrame({
        "time_s": times + 100,
        "take_time_s": times,
        "channel": "h10_raw_ecg_rr_bpm",
        "value": 90 + times / 10,
        "unit": "bpm",
        "layer": "estimate",
        "source": "H10",
        "take_id": "recovery_1",
    })


def test_prepare_holdout_separates_context_and_future():
    result = prepare_holdout(sample_frame(), "h10_raw_ecg_rr_bpm | H10", "recovery_1")
    assert len(result["context_frame"]) == 30
    assert result["context_frame"]["time_s"].max() == 30
    assert result["context_actual"]["plot_time_s"].max() <= 30
    assert result["future_actual"]["plot_time_s"].min() >= 31
    assert result["future_actual"]["plot_time_s"].max() < 60


def test_score_forecast_only_uses_measured_future_times():
    truth = pd.DataFrame({"plot_time_s": [31.5, 33.5], "value": [100.5, 102.5]})
    forecast = pd.DataFrame({
        "time_s": [31.0, 32.0, 33.0, 34.0],
        "value": [100.0, 101.0, 102.0, 103.0],
        "low_80": [99.0, 100.0, 101.0, 102.0],
        "high_80": [101.0, 102.0, 103.0, 104.0],
    })
    compared, metrics = score_forecast(forecast, truth)
    assert compared["time_s"].tolist() == [31.5, 33.5]
    assert metrics["n"] == 2
    assert metrics["mae_bpm"] == 0.0


def test_baselines_use_only_context_and_score_at_measured_future_times():
    context = pd.DataFrame({"time_s": np.arange(1, 31), "value": 100.0 - np.arange(1, 31) * 0.5})
    baselines = reference_baselines(context)
    assert baselines["persistence"]["value"].eq(85.0).all()
    # The trend fit uses the final 10 context points; extend their exact slope.
    assert np.isclose(baselines["linear_trend"].iloc[0]["value"], 84.5)
    truth = pd.DataFrame({"plot_time_s": [32.5, 50.5], "value": [84.0, 75.0]})
    scored, metrics = score_point_forecast(baselines["linear_trend"], truth)
    assert scored["time_s"].tolist() == [32.5, 50.5]
    assert metrics["n"] == 2
    assert np.isclose(metrics["forecast_change_bpm"], -9.0)
    assert np.isclose(metrics["observed_change_bpm"], -9.0)
    assert np.isclose(metrics["change_error_bpm"], 0.0)
