#!/usr/bin/env python3
"""Extract a periodic, cycle-averaged Pulse aortic inlet for openBF."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from bridge_units import ml_per_s_to_m3_per_s

ROOT = Path(__file__).resolve().parents[1]
PULSE = Path(os.environ.get("PULSE_ROOT", ROOT.parent / "pulse-physiology-engine"))
BIN = PULSE / "build/install/bin"
OUT = ROOT / "results/stage4"
INTERFACE = ROOT / "config/stage4_interface_v1.json"
STAGE0 = ROOT / "results/stage2/stage0_regression_gate.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def requests():
    from pulse.cdm.engine import SEDataRequest, SEDataRequestManager
    from pulse.cdm.scalars import (FrequencyUnit, PressureTimePerVolumeUnit,
                                   PressureUnit, VolumePerTimeUnit)
    r = SEDataRequest
    return SEDataRequestManager([
        r.create_liquid_compartment_request("Aorta", "InFlow", VolumePerTimeUnit.mL_Per_s),
        r.create_liquid_compartment_request("Aorta", "Pressure", PressureUnit.mmHg),
        r.create_physiology_request("HeartRate", FrequencyUnit.Per_min),
        r.create_physiology_request("CardiacOutput", VolumePerTimeUnit.L_Per_min),
        r.create_physiology_request("MeanArterialPressure", PressureUnit.mmHg),
        r.create_physiology_request("SystolicArterialPressure", PressureUnit.mmHg),
        r.create_physiology_request("DiastolicArterialPressure", PressureUnit.mmHg),
        r.create_physiology_request("SystemicVascularResistance",
                                    PressureTimePerVolumeUnit.mmHg_s_Per_mL),
    ])


def sample_pulse(duration_s=20.0):
    from pulse.engine.PulseEngine import PulseEngine
    engine = PulseEngine(data_root_dir=str(BIN))
    engine.log_to_console(False)
    private = OUT / "private"
    private.mkdir(parents=True, exist_ok=True)
    engine.set_log_filename(str(private / "pulse_inlet_extraction.log"))
    state = BIN / "states/StandardMale@0s.json"
    if not engine.serialize_from_file(str(state), requests()):
        raise RuntimeError("Pulse could not load StandardMale@0s")
    columns = ["time_s", "aorta_inflow_mL_s", "aorta_pressure_mmHg",
               "heart_rate_per_min", "cardiac_output_L_min", "map_mmHg",
               "systolic_mmHg", "diastolic_mmHg", "svr_mmHg_s_mL"]
    rows = []
    for _ in range(int(round(duration_s / 0.02))):
        if not engine.advance_time_s(0.02):
            raise RuntimeError("Pulse stopped during stable inlet extraction")
        rows.append(dict(zip(columns, engine.pull_data().copy())))
    frame = pd.DataFrame(rows)
    frame.to_csv(private / "pulse_stable_raw.csv.gz", index=False, compression="gzip")
    return frame


def average_cycles(frame, n_cycles, n_points):
    dt = float(np.median(np.diff(frame.time_s)))
    peaks, _ = find_peaks(frame.aorta_inflow_mL_s.to_numpy(), prominence=100.0,
                          distance=max(1, int(0.6 / dt)))
    if len(peaks) < n_cycles + 1:
        raise RuntimeError(f"Only {len(peaks) - 1} complete cardiac cycles found")
    starts = peaks[-(n_cycles + 1):]
    phase = np.linspace(0.0, 1.0, n_points)
    flows, pressures, periods = [], [], []
    for left, right in zip(starts[:-1], starts[1:]):
        segment = frame.iloc[left:right + 1]
        local_phase = ((segment.time_s - segment.time_s.iloc[0]) /
                       (segment.time_s.iloc[-1] - segment.time_s.iloc[0]))
        flows.append(np.interp(phase, local_phase, segment.aorta_inflow_mL_s))
        pressures.append(np.interp(phase, local_phase, segment.aorta_pressure_mmHg))
        periods.append(float(segment.time_s.iloc[-1] - segment.time_s.iloc[0]))
    flows, pressures = np.asarray(flows), np.asarray(pressures)
    mean_flow, mean_pressure = flows.mean(axis=0), pressures.mean(axis=0)
    rmses = np.sqrt(np.mean((flows - mean_flow) ** 2, axis=1))
    # openBF initializes its characteristic inlet at t=0. Start immediately
    # before the steepest systolic upstroke, not at the flow peak used to align
    # the Pulse cycles.
    unique_flow, unique_pressure = mean_flow[:-1], mean_pressure[:-1]
    start = int(np.argmax(np.diff(unique_flow, append=unique_flow[0])))
    unique_flow = np.roll(unique_flow, -start)
    unique_pressure = np.roll(unique_pressure, -start)
    mean_flow = np.r_[unique_flow, unique_flow[0]]
    mean_pressure = np.r_[unique_pressure, unique_pressure[0]]
    time_s = phase * float(np.mean(periods))
    return time_s, mean_flow, mean_pressure, periods, rmses


def main():
    spec = json.loads(INTERFACE.read_text())
    gate = json.loads(STAGE0.read_text())
    if not gate.get("passed"):
        raise RuntimeError("Stage 0 regression gate is not passing")
    OUT.mkdir(parents=True, exist_ok=True)
    frame = sample_pulse()
    cycle = spec["cycle"]
    time_s, flow_ml_s, pressure, periods, rmses = average_cycles(
        frame, cycle["cycles_to_average"],
        cycle["resampled_points_including_periodic_endpoint"])
    flow_m3_s = ml_per_s_to_m3_per_s(flow_ml_s)
    floor = cycle["openbf_zero_flow_floor_m3_s"]
    flow_m3_s[np.abs(flow_m3_s) < floor] = floor
    inlet = OUT / "pulse_aortic_inlet.dat"
    np.savetxt(inlet, np.column_stack([time_s, flow_m3_s]), fmt="%.12g")
    pd.DataFrame({"time_s": time_s, "aorta_inflow_mL_s": flow_ml_s,
                  "aorta_inflow_m3_s": flow_m3_s,
                  "aorta_pressure_mmHg": pressure}).to_csv(
                      OUT / "pulse_representative_cycle.csv", index=False)
    cycle_co = float(np.trapz(flow_ml_s, time_s) / time_s[-1] * 0.06)
    pulse_co = float(frame.cardiac_output_L_min.median())
    relative_error = abs(cycle_co - pulse_co) / pulse_co
    periodic_error = abs(float(flow_m3_s[-1] - flow_m3_s[0]))
    max_rmse_fraction = float(np.max(rmses) / np.max(flow_ml_s))
    if relative_error > cycle["maximum_flow_integral_relative_error"]:
        raise RuntimeError(f"Flow integral/CO mismatch: {relative_error:.3%}")
    if periodic_error > cycle["periodic_endpoint_absolute_tolerance_m3_s"]:
        raise RuntimeError("Representative flow is not periodic")
    if max_rmse_fraction > cycle["maximum_cycle_flow_rmse_fraction_of_peak"]:
        raise RuntimeError("Stable Pulse cycles are insufficiently repeatable")
    metadata = {
        "interface_schema": spec["schema"], "interface_version": spec["version"],
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "pulse_revision": subprocess.check_output(
            ["git", "-C", str(PULSE), "rev-parse", "HEAD"], text=True).strip(),
        "coupling_revision_at_generation": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
        "patient_state": str(BIN / "states/StandardMale@0s.json"),
        "source_flow": "Aorta-InFlow", "inlet_file": str(inlet),
        "inlet_sha256": sha256(inlet), "samples": len(time_s),
        "cycles_averaged": len(periods), "cardiac_cycle_length_s": float(time_s[-1]),
        "heart_rate_per_min": float(frame.heart_rate_per_min.median()),
        "mean_arterial_pressure_mmHg": float(frame.map_mmHg.median()),
        "systolic_pressure_mmHg": float(frame.systolic_mmHg.median()),
        "diastolic_pressure_mmHg": float(frame.diastolic_mmHg.median()),
        "aortic_cycle_mean_pressure_mmHg": float(np.trapz(pressure, time_s) / time_s[-1]),
        "aortic_cycle_systolic_pressure_mmHg": float(np.max(pressure)),
        "aortic_cycle_diastolic_pressure_mmHg": float(np.min(pressure)),
        "cardiac_output_reported_L_min": pulse_co,
        "cardiac_output_from_flow_integral_L_min": cycle_co,
        "flow_integral_relative_error": relative_error,
        "periodic_endpoint_error_m3_s": periodic_error,
        "cycle_periods_s": periods,
        "maximum_cycle_flow_rmse_fraction_of_peak": max_rmse_fraction,
        "systemic_vascular_resistance_mmHg_s_mL": float(frame.svr_mmHg_s_mL.median()),
        "stage0_gate": gate,
    }
    (OUT / "pulse_inlet_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
