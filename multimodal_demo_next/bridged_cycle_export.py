from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

MMHG_PER_PA = 1.0 / 133.322387415


def _read_last_cycle(path: Path) -> np.ndarray:
    values = np.loadtxt(path, dtype=float)
    if values.ndim != 2 or values.shape[1] < 2 or values.shape[0] < 3:
        raise ValueError(f"Expected a time column and at least two spatial values in {path}")
    if not np.isfinite(values).all() or not np.all(np.diff(values[:, 0]) > 0):
        raise ValueError(f"OpenBF output must be finite with strictly increasing time: {path}")
    return values


def _long_rows(
    times: np.ndarray,
    values: np.ndarray,
    *,
    channel: str,
    unit: str,
    layer: str,
    source: str,
    scenario: str,
    episode_id: str,
    relation: str,
    model_version: str,
    parameterization: str,
    processing_stage: str,
    derived_from: str,
    alignment_method: str,
) -> pd.DataFrame:
    return pd.DataFrame({
        "time_s": times,
        "channel": channel,
        "value": values,
        "unit": unit,
        "layer": layer,
        "source": source,
        "scenario": scenario,
        "episode_id": episode_id,
        "clock_provenance": "Pulse/OpenBF coupled cardiac-cycle phase",
        "alignment_status": "derived_alignment",
        "episode_relationship": relation,
        "model_version": model_version,
        "parameterization": parameterization,
        "processing_stage": processing_stage,
        "derived_from": derived_from,
        "alignment_method": alignment_method,
    })


def export_bridged_cycle(
    *,
    project_root: Path,
    openbf_case: str,
    output: Path,
    site: str = "external_carotid_R",
) -> int:
    """Export a Pulse representative cycle with its corresponding Stage 5 OpenBF cycle.

    OpenBF's ``.last`` files are phase-mapped to the Pulse inlet cycle by using
    the shared period and the end of the saved converged OpenBF cycle. The final
    spatial column is retained, matching the project's distal-site analysis.
    """
    root = Path(project_root).resolve()
    pulse_dir = root / "results" / "stage5" / "pulse" / "normotensive"
    pulse_cycle_path = pulse_dir / "representative_cycle.csv"
    pulse_metadata_path = pulse_dir / "metadata.json"
    run_dir = root / "results" / "stage5" / "runs" / openbf_case
    manifest_path = root / "results" / "stage5" / "run_manifest.json"

    pulse = pd.read_csv(pulse_cycle_path).sort_values("time_s")
    required = {"time_s", "aorta_inflow_mL_s", "aorta_pressure_mmHg"}
    if not required.issubset(pulse.columns):
        raise ValueError(f"Pulse cycle is missing columns: {sorted(required - set(pulse.columns))}")
    pulse_time = pulse["time_s"].to_numpy(dtype=float)
    period_s = float(pulse_time[-1] - pulse_time[0])
    if period_s <= 0 or not np.isfinite(pulse_time).all() or not np.all(np.diff(pulse_time) > 0):
        raise ValueError("Pulse representative cycle needs finite, strictly increasing time")

    pulse_metadata = json.loads(pulse_metadata_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    matches = [case for case in manifest["cases"] if case["case"] == openbf_case]
    if len(matches) != 1:
        raise ValueError(f"OpenBF case {openbf_case!r} is not uniquely listed in the Stage 5 manifest")
    case_meta = matches[0]
    if case_meta.get("source", "").lower() != "pulse":
        raise ValueError(f"OpenBF case {openbf_case!r} is not marked as Pulse-inlet-driven")

    pressure = _read_last_cycle(run_dir / f"{site}_P.last")
    flow = _read_last_cycle(run_dir / f"{site}_Q.last")
    if pressure.shape != flow.shape or not np.allclose(pressure[:, 0], flow[:, 0], atol=1e-10, rtol=0):
        raise ValueError("OpenBF pressure and flow files have different time/spatial grids")
    openbf_time = pressure[:, 0]
    openbf_period = float(openbf_time[-1] - openbf_time[0])
    sample_step = float(np.median(np.diff(openbf_time)))
    if abs(openbf_period - period_s) > sample_step / 2.0:
        raise ValueError(
            f"OpenBF cycle duration ({openbf_period:.6f}s) differs from Pulse inlet "
            f"period ({period_s:.6f}s) by more than one output sample"
        )
    # Align the last saved OpenBF cycle's end to the Pulse periodic endpoint.
    # This retains the OpenBF propagation delay within that shared cardiac phase.
    openbf_phase_time = openbf_time - (openbf_time[-1] - (pulse_time[0] + period_s))

    relation = "same_episode" if openbf_case == "normotensive_arm1_inlet_only" else "comparable_scenario"
    episode_id = f"pulse_normotensive__{openbf_case}"
    scenario = episode_id
    openbf_revision = manifest.get("openbf_revision", "unspecified")
    model_version_pulse = "Pulse Stage 5 export; commit not recorded in metadata"
    model_version_openbf = f"openBF {openbf_revision}"
    parameterization = (
        f"Stage 5 {openbf_case}; Pulse normotensive inlet; "
        f"terminal resistance scale={case_meta.get('terminal_resistance_scale')}; "
        f"compliance scale={case_meta.get('terminal_compliance_scale')}; "
        f"wall Young's modulus scale={case_meta.get('wall_youngs_modulus_scale')}"
    )
    alignment_method = (
        f"OpenBF converged-cycle time shifted onto Pulse cardiac-cycle phase; its endpoint matches the Pulse "
        f"representative-cycle endpoint; shared cycle period={period_s:.9f}s; "
        "no within-cycle resampling"
    )

    records = []
    records.append(_long_rows(
        pulse_time, pulse["aorta_inflow_mL_s"].to_numpy(dtype=float),
        channel="aortic_inflow", unit="mL/s", layer="latent", source="Pulse",
        scenario=scenario, episode_id=episode_id, relation=relation,
        model_version=model_version_pulse,
        parameterization=f"Pulse normotensive phenotype; inlet sha256={pulse_metadata['inlet_sha256']}",
        processing_stage="latent_physiology", derived_from="Pulse representative_cycle.csv",
        alignment_method="Pulse representative-cycle source time; cycle origin at 0s",
    ))
    records.append(_long_rows(
        pulse_time, pulse["aorta_pressure_mmHg"].to_numpy(dtype=float),
        channel="aortic_pressure", unit="mmHg", layer="latent", source="Pulse",
        scenario=scenario, episode_id=episode_id, relation=relation,
        model_version=model_version_pulse,
        parameterization=f"Pulse normotensive phenotype; inlet sha256={pulse_metadata['inlet_sha256']}",
        processing_stage="latent_physiology", derived_from="Pulse representative_cycle.csv",
        alignment_method="Pulse representative-cycle source time; cycle origin at 0s",
    ))
    hr = float(pulse_metadata["heart_rate_per_min"])
    records.append(_long_rows(
        pulse_time, np.full_like(pulse_time, hr, dtype=float),
        channel="heart_rate", unit="bpm", layer="latent", source="Pulse",
        scenario=scenario, episode_id=episode_id, relation=relation,
        model_version=model_version_pulse,
        parameterization="Pulse normotensive representative-cycle metadata",
        processing_stage="latent_physiology", derived_from="Pulse metadata.json",
        alignment_method="constant representative-cycle HR; not beat-resolved",
    ))

    for quantity, matrix, unit, scale in (
        ("pressure", pressure, "mmHg", MMHG_PER_PA),
        ("flow", flow, "mL/s", 1e6),
    ):
        records.append(_long_rows(
            openbf_phase_time, matrix[:, -1] * scale,
            channel=f"openbf_{site}_{quantity}", unit=unit, layer="subsystem",
            source=f"OpenBF ADAN56 {site} final sampled node",
            scenario=scenario, episode_id=episode_id,
            relation=relation,
            model_version=model_version_openbf,
            parameterization=parameterization,
            processing_stage="vascular_subsystem_output",
            derived_from=f"{site}_{'P' if quantity == 'pressure' else 'Q'}.last (final spatial column)",
            alignment_method=alignment_method,
        ))

    output_frame = pd.concat(records, ignore_index=True).sort_values(["time_s", "layer", "channel"])
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output_frame.to_csv(output, index=False)
    return len(output_frame)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--openbf-case", required=True, help="Stage 5 case in results/stage5/run_manifest.json")
    parser.add_argument("--site", default="external_carotid_R", help="OpenBF vessel output prefix")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = export_bridged_cycle(
        project_root=args.project_root,
        openbf_case=args.openbf_case,
        site=args.site,
        output=args.output,
    )
    print(f"Wrote {rows} Pulse/OpenBF cycle rows to {args.output}")


if __name__ == "__main__":
    main()
