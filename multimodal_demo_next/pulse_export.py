from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

PULSE_CHANNELS = {
    "heart_rate_per_min": ("heart_rate", "bpm"),
    "map_mmHg": ("mean_arterial_pressure", "mmHg"),
    "systolic_mmHg": ("systolic_pressure", "mmHg"),
    "diastolic_mmHg": ("diastolic_pressure", "mmHg"),
    "pulse_pressure_mmHg": ("pulse_pressure", "mmHg"),
    "cardiac_output_L_min": ("cardiac_output", "L/min"),
    "stroke_volume_mL": ("stroke_volume", "mL"),
    "svr_mmHg_s_mL": ("systemic_vascular_resistance", "mmHg s/mL"),
    "systemic_vascular_resistance_mmHg_s_mL": ("systemic_vascular_resistance", "mmHg s/mL"),
    "blood_volume_mL": ("blood_volume", "mL"),
    "aorta_pressure_mmHg": ("aortic_pressure", "mmHg"),
    "aorta_inflow_mL_s": ("aortic_inflow", "mL/s"),
}


def export_pulse_trace(source: Path, destination: Path, scenario: str) -> int:
    """Convert one exported Pulse CSV/CSV.GZ trajectory to the demo contract."""
    source = Path(source)
    destination = Path(destination)
    frame = pd.read_csv(source)
    if "time_s" not in frame:
        raise ValueError("Pulse input must contain a time_s column")

    records = []
    emitted_channels: set[str] = set()
    for pulse_column, (channel, unit) in PULSE_CHANNELS.items():
        if pulse_column not in frame or channel in emitted_channels:
            continue
        part = frame[["time_s", pulse_column]].rename(columns={pulse_column: "value"})
        part["channel"] = channel
        part["unit"] = unit
        part["layer"] = "latent"
        part["source"] = "Pulse"
        part["scenario"] = scenario
        part["episode_id"] = scenario
        part["clock_provenance"] = "Pulse simulation-relative time"
        part["alignment_status"] = "unaligned"
        part["episode_relationship"] = "unrelated"
        records.append(part)
        emitted_channels.add(channel)

    if not records:
        raise ValueError("No recognised Pulse channels found in input")
    output = pd.concat(records, ignore_index=True)
    output = output[[
        "time_s", "channel", "value", "unit", "layer", "source", "scenario",
        "episode_id", "clock_provenance", "alignment_status", "episode_relationship",
    ]]
    output = output.dropna(subset=["time_s", "value"]).sort_values(["time_s", "channel"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(destination, index=False)
    return len(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pulse_csv", type=Path, help="Pulse CSV or CSV.GZ export")
    parser.add_argument("output_csv", type=Path, help="Destination exchange-format CSV")
    parser.add_argument("--scenario", required=True, help="Descriptive scenario/take identifier")
    args = parser.parse_args()
    rows = export_pulse_trace(args.pulse_csv, args.output_csv, args.scenario)
    print(f"Wrote {rows} latent Pulse observations to {args.output_csv}")


if __name__ == "__main__":
    main()
