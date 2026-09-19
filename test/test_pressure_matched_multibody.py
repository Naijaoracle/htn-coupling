from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import pressure_matched_multibody_helpers as helpers
import run_pressure_matched_drug_response_multibody as multibody
from run_pressure_matched_drug_response_multibody import patient_payload


def test_weight_based_norepinephrine_rates_and_volume_equivalents():
    expected = {
        56.6: 0.18866666666666668,
        80.1: 0.267,
        39.6: 0.132,
        74.4: 0.248,
    }
    for mass_kg, rate in expected.items():
        calculated = helpers.norepinephrine_rate_mL_s(0.2, mass_kg, 1.0)
        assert calculated == pytest.approx(rate)
        assert calculated * 300 == pytest.approx(mass_kg)


@pytest.mark.parametrize("dose,mass,concentration", [(0, 50, 1), (0.2, 0, 1), (0.2, 50, 0)])
def test_dose_conversion_rejects_nonpositive_inputs(dose, mass, concentration):
    with pytest.raises(ValueError):
        helpers.norepinephrine_rate_mL_s(dose, mass, concentration)


def test_fixed_panel_body_bmi_and_direct_payload_envelope():
    body = {"body_id": "female_low_bmi", "sex": "Female", "age_years": 52,
            "height_cm": 155.5, "weight_kg": 39.6}
    assert helpers.body_bmi_kg_m2(body) == pytest.approx(16.377)
    payload = patient_payload(body, 140, 90, "test_body")
    assert payload["Sex"] == "Female"
    assert payload["Weight"]["ScalarMass"] == {"Value": 39.6, "Unit": "kg"}
    assert payload["Height"]["ScalarLength"] == {"Value": 155.5, "Unit": "cm"}
    assert payload["SystolicArterialPressureBaselineMaximum"]["ScalarPressure"]["Value"] == 200
    assert payload["DiastolicArterialPressureBaselineMinimum"]["ScalarPressure"]["Value"] == 40
    assert "BodyFatFraction" not in payload


def test_pair_matching_requires_stationarity_and_both_pressures():
    direct = {"systolic_mmHg": 140.1, "diastolic_mmHg": 90.1}
    modifier = {"systolic_mmHg": 139.9, "diastolic_mmHg": 89.9, "stationarity_pass": True}
    assert helpers.pressure_match_passes(modifier, direct)
    modifier["diastolic_mmHg"] = 89.8
    assert not helpers.pressure_match_passes(modifier, direct)
    modifier["diastolic_mmHg"] = 89.9
    modifier["stationarity_pass"] = False
    assert not helpers.pressure_match_passes(modifier, direct)


def test_bounded_newton_step_solves_local_two_pressure_system():
    point = helpers.bounded_newton_proposal(
        (1.5, 0.7), (2.0, -1.0), ((10.0, 0.0), (0.0, 10.0)),
        ((1.0, 2.0), (0.4, 1.0)), max_coordinate_step=0.25)
    assert point == pytest.approx((1.3, 0.8))


def test_bounded_newton_step_clips_to_declared_domain_and_rejects_singular_system():
    clipped = helpers.bounded_newton_proposal(
        (1.9, 0.95), (-100.0, 100.0), ((1.0, 0.0), (0.0, 1.0)),
        ((1.0, 2.0), (0.4, 1.0)), max_coordinate_step=0.25)
    assert clipped == pytest.approx((2.0, 0.7))
    with pytest.raises(ValueError, match="singular"):
        helpers.bounded_newton_proposal(
            (1.5, 0.7), (1.0, 1.0), ((1.0, 1.0), (2.0, 2.0)),
            ((1.0, 2.0), (0.4, 1.0)))


def test_local_search_finds_a_synthetic_stationary_pressure_match(monkeypatch, tmp_path):
    reference = {"systolic_mmHg": 140.0, "diastolic_mmHg": 90.0}

    def fake_evaluate(jobs, workers):
        rows = []
        for job in jobs:
            r, c = float(job["R"]), float(job["C"])
            rows.append({**job, "status": "ok", "stationarity_pass": True,
                "systolic_mmHg": 140.0 + 10 * (r - 1.5) + 4 * (c - 0.7),
                "diastolic_mmHg": 90.0 + 5 * (r - 1.5) - 10 * (c - 0.7)})
        return rows

    monkeypatch.setattr(multibody, "evaluate_jobs", fake_evaluate)
    body = {"body_id": "unit_body"}
    search_rows, selected = multibody.search_body(
        body, reference, tmp_path / "state.json", tmp_path, workers=1)
    assert selected is not None
    assert selected["R"] == pytest.approx(1.5)
    assert selected["C"] == pytest.approx(0.7)
    assert multibody.within_match(selected, reference)
    assert len(search_rows) <= 20


@pytest.mark.parametrize("label", ["", "../escape", "has space", "x" * 49])
def test_attempt_label_cannot_escape_result_root(label):
    with pytest.raises(ValueError):
        helpers.attempt_output_directory(Path("/tmp/results"), label)
