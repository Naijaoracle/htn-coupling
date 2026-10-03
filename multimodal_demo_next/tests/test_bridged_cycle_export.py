import json
import sys
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bridged_cycle_export import export_bridged_cycle
from data_contract import load_observations
from pulse_state_adapter import renderer_state_at_cursor


def make_project(root: Path, *, openbf_period: float = 0.84) -> Path:
    pulse_dir = root / "results/stage5/pulse/normotensive"
    pulse_dir.mkdir(parents=True)
    pulse_times = np.linspace(0.0, 0.84, 51)
    pulse_phase = pulse_times / 0.84
    pd.DataFrame({
        "time_s": pulse_times,
        "aorta_inflow_mL_s": np.maximum(0.0, 400.0 * (1.0 - np.abs(pulse_phase - 0.28) / 0.28)),
        "aorta_pressure_mmHg": 80.0 + 20.0 * np.sin(np.pi * pulse_phase),
    }).to_csv(pulse_dir / "representative_cycle.csv", index=False)
    (pulse_dir / "metadata.json").write_text(json.dumps({
        "heart_rate_per_min": 60.0 / 0.84,
        "inlet_sha256": "pulse-fixture-hash",
    }))
    (root / "results/stage5/run_manifest.json").write_text(json.dumps({
        "openbf_revision": "openbf-fixture-revision",
        "cases": [{
            "case": "normotensive_arm1_inlet_only", "source": "pulse",
            "terminal_resistance_scale": 1.0, "terminal_compliance_scale": 1.0,
            "wall_youngs_modulus_scale": 1.0,
        }],
    }))
    run = root / "results/stage5/runs/normotensive_arm1_inlet_only"
    run.mkdir(parents=True)
    times = np.linspace(2.0, 2.0 + openbf_period, 51)
    # The final column represents the selected distal spatial sample.
    pressure_values = np.full_like(times, 133.322387415)
    flow_values = np.full_like(times, 1e-6)
    flow_values[len(times) // 2] = 2e-6
    np.savetxt(run / "external_carotid_R_P.last", np.column_stack((times, np.full_like(times, 2), pressure_values)))
    np.savetxt(run / "external_carotid_R_Q.last", np.column_stack((times, np.ones_like(times), flow_values)))
    return root


def test_bridged_cycle_exports_latent_and_subsystem_with_phase_provenance(tmp_path):
    root = make_project(tmp_path)
    output = tmp_path / "bridged.csv"
    count = export_bridged_cycle(
        project_root=root,
        openbf_case="normotensive_arm1_inlet_only",
        output=output,
    )

    frame = load_observations(BytesIO(output.read_bytes()))
    assert count == len(frame)
    assert set(frame.layer) == {"latent", "subsystem"}
    assert set(frame.scenario) == {"pulse_normotensive__normotensive_arm1_inlet_only"}
    assert set(frame.episode_relationship) == {"same_episode"}
    assert set(frame.alignment_status) == {"derived_alignment"}
    pressure = frame[frame.channel == "openbf_external_carotid_R_pressure"]
    flow = frame[frame.channel == "openbf_external_carotid_R_flow"]
    assert pressure.value.iloc[0] == pytest.approx(1.0)
    assert flow.value.max() == pytest.approx(2.0)
    assert pressure.time_s.iloc[0] == pytest.approx(0.0)
    assert pressure.model_version.iloc[0] == "openBF openbf-fixture-revision"
    assert "phase" in pressure.alignment_method.iloc[0]
    hr = frame[frame.channel == "heart_rate"]
    assert np.allclose(hr.time_s.to_numpy(), np.linspace(0.0, 0.84, 51))
    state = renderer_state_at_cursor(frame[frame.layer == "latent"], "Pulse", 0.27)
    assert state["hr_bpm"] == pytest.approx(60.0 / 0.84)


def test_bridged_cycle_rejects_openbf_period_outside_one_output_step(tmp_path):
    root = make_project(tmp_path, openbf_period=0.9)
    with pytest.raises(ValueError, match="cycle duration"):
        export_bridged_cycle(
            project_root=root,
            openbf_case="normotensive_arm1_inlet_only",
            output=tmp_path / "bad.csv",
        )


def test_exchange_contract_accepts_synthetic_observation_layer():
    csv = (
        "time_s,channel,value,unit,layer,source,scenario\n"
        "0.0,rgb_red,0.12,a.u.,synthetic_observation,MCX,demo\n"
    ).encode()
    frame = load_observations(BytesIO(csv))
    assert frame.layer.iloc[0] == "synthetic_observation"
    assert frame.model_version.iloc[0] == "unspecified"
