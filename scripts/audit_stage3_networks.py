#!/usr/bin/env python3
"""Audit openBF facial-site reachability and existing resting waveforms."""

from __future__ import annotations

import csv
import hashlib
import os
import json
from collections import defaultdict
from heapq import heappop, heappush
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import yaml
from scipy.signal import find_peaks


PROJECT = Path(__file__).resolve().parents[1]
OPENBF = Path(os.environ.get("OPENBF_ROOT", PROJECT.parent / "openBF"))
OUT = PROJECT / "results" / "stage3"
BASELINE = PROJECT / "results" / "stage0" / "openbf_adan56"
COW_BASELINE = OUT / "openbf_circle_of_willis"
MODELS = {
    "adan56": OPENBF / "models" / "boileau2015" / "adan56" / "adan56.yaml",
    "alastruey2007": OPENBF / "models" / "alastruey2007" / "circle_of_willis.yaml",
}
MMHG_PA = 133.32236842105263
TARGET_TERMS = (
    "facial",
    "superficial temporal",
    "ophthalmic",
    "supraorbital",
    "supratrochlear",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def root_distances(vessels: list[dict]) -> dict[int, float]:
    graph: dict[int, list[tuple[int, float]]] = defaultdict(list)
    starts = {int(v["sn"]) for v in vessels}
    ends = {int(v["tn"]) for v in vessels}
    roots = sorted(starts - ends) or [min(starts)]
    for vessel in vessels:
        graph[int(vessel["sn"])].append((int(vessel["tn"]), float(vessel["L"])))
    distances = {node: 0.0 for node in roots}
    queue = [(0.0, node) for node in roots]
    while queue:
        distance, node = heappop(queue)
        if distance != distances[node]:
            continue
        for target, length in graph[node]:
            candidate = distance + length
            if candidate < distances.get(target, float("inf")):
                distances[target] = candidate
                heappush(queue, (candidate, target))
    return distances


def inventory_model(name: str, path: Path) -> tuple[list[dict], dict]:
    document = yaml.safe_load(path.read_text())
    vessels = document["network"]
    distances = root_distances(vessels)
    outgoing = defaultdict(int)
    for vessel in vessels:
        outgoing[int(vessel["sn"])] += 1
    rows = []
    for index, vessel in enumerate(vessels, start=1):
        sn, tn = int(vessel["sn"]), int(vessel["tn"])
        proximal = distances.get(sn)
        length = float(vessel["L"])
        rows.append(
            {
                "configured_index": index,
                "label": vessel["label"],
                "start_node": sn,
                "end_node": tn,
                "length_m": length,
                "root_to_proximal_m": proximal,
                "root_to_distal_m": None if proximal is None else proximal + length,
                "proximal_radius_m": vessel.get("Rp"),
                "distal_radius_m": vessel.get("Rd"),
                "youngs_modulus_pa": vessel.get("E"),
                "outlet": vessel.get("outlet", ""),
                "terminal_by_topology": outgoing[tn] == 0,
                "R1_pa_s_m3": vessel.get("R1"),
                "R2_pa_s_m3": vessel.get("R2"),
                "C_m3_pa": vessel.get("Cc"),
            }
        )
    metadata = {
        "model_key": name,
        "project_name": document.get("project_name"),
        "configured_segment_count": len(vessels),
        "outlet_count": sum("outlet" in vessel for vessel in vessels),
        "yaml": str(path),
        "yaml_sha256": sha256(path),
        "target_name_matches": {
            term: [
                vessel["label"]
                for vessel in vessels
                if term.replace(" ", "") in vessel["label"].lower().replace("_", "").replace("-", "")
            ]
            for term in TARGET_TERMS
        },
    }
    return rows, metadata


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def carotid_candidates(inventories: dict[str, list[dict]]) -> list[dict]:
    direct_route_overrides = {
        ("alastruey2007", "18-L-int-carotidII"): 0.450,
        ("alastruey2007", "21-R-int-carotidII"): 0.433,
    }
    rows = []
    for model, inventory in inventories.items():
        for vessel in inventory:
            label = vessel["label"].lower()
            if "carotid" not in label:
                continue
            if "common" in label:
                relation = "upstream of both facial territories"
            elif "ext" in label:
                relation = "upstream reference for ECA-supplied facial skin"
            elif "int" in label:
                relation = "upstream reference for ICA/ophthalmic-supplied facial skin"
            else:
                relation = "carotid candidate"
            rows.append(
                {
                    "model": model,
                    "label": vessel["label"],
                    "shortest_graph_root_to_distal_m": vessel["root_to_distal_m"],
                    "direct_carotid_route_to_distal_m": direct_route_overrides.get(
                        (model, vessel["label"]), vessel["root_to_distal_m"]
                    ),
                    "distal_radius_mm": float(vessel["distal_radius_m"]) * 1000,
                    "terminal_by_topology": vessel["terminal_by_topology"],
                    "outlet": vessel["outlet"],
                    "relationship_to_facial_territory": relation,
                    "physical_optical_site": False,
                }
            )
    return rows


def pressure_trace(vessel: str, directory: Path = BASELINE) -> tuple[np.ndarray, np.ndarray]:
    data = np.loadtxt(directory / f"{vessel}_P.last")
    return data[:, 0] - data[0, 0], data[:, -1] / MMHG_PA


def flow_trace(vessel: str, directory: Path = BASELINE) -> tuple[np.ndarray, np.ndarray]:
    data = np.loadtxt(directory / f"{vessel}_Q.last")
    return data[:, 0] - data[0, 0], data[:, -1] * 60e6


def waveform_metrics(vessel: str, directory: Path = BASELINE, model: str = "adan56") -> dict:
    time, pressure = pressure_trace(vessel, directory)
    flow_time, flow = flow_trace(vessel, directory)
    assert np.allclose(time, flow_time)
    peak_index = int(np.argmax(pressure))
    after = np.arange(peak_index + 2, len(pressure) - 1)
    minima = after[(pressure[after] < pressure[after - 1]) & (pressure[after] <= pressure[after + 1])]
    notch_index = int(minima[0]) if len(minima) else None
    secondary_index = None
    if notch_index is not None:
        maxima = find_peaks(pressure[notch_index:], prominence=0.15)[0]
        if len(maxima):
            secondary_index = int(notch_index + maxima[0])
    return {
        "model": model,
        "vessel": vessel,
        "sample_count": len(time),
        "cycle_duration_s": float(time[-1] - time[0]),
        "diastolic_mmHg": float(np.min(pressure)),
        "systolic_mmHg": float(np.max(pressure)),
        "mean_mmHg": float(np.trapz(pressure, time) / (time[-1] - time[0])),
        "pulse_pressure_mmHg": float(np.ptp(pressure)),
        "primary_peak_time_s": float(time[peak_index]),
        "first_post_peak_min_time_s": None if notch_index is None else float(time[notch_index]),
        "first_post_peak_min_mmHg": None if notch_index is None else float(pressure[notch_index]),
        "next_local_peak_time_s": None if secondary_index is None else float(time[secondary_index]),
        "next_local_peak_mmHg": None if secondary_index is None else float(pressure[secondary_index]),
        "minimum_flow_mL_min": float(np.min(flow)),
        "maximum_flow_mL_min": float(np.max(flow)),
        "mean_flow_mL_min": float(np.trapz(flow, time) / (time[-1] - time[0])),
        "end_cycle_flow_mL_min": float(flow[-1]),
        "has_reverse_flow": bool(np.any(flow < 0)),
    }


def plot_waveforms(vessels: list[str]) -> None:
    fig, axis = plt.subplots(figsize=(8.2, 4.8), constrained_layout=True)
    for vessel in vessels:
        time, pressure = pressure_trace(vessel)
        axis.plot(time, pressure, label=vessel.replace("_", " "))
    axis.set(xlabel="Time in final cycle (s)", ylabel="Distal pressure (mmHg)")
    axis.grid(alpha=0.25)
    axis.legend(frameon=False, ncol=2)
    fig.savefig(OUT / "adan56_distal_carotid_pressure.png", dpi=200)
    plt.close(fig)


def plot_cow_waveforms(vessels: list[str]) -> None:
    fig, axis = plt.subplots(figsize=(8.2, 4.8), constrained_layout=True)
    for vessel in vessels:
        time, pressure = pressure_trace(vessel, COW_BASELINE)
        axis.plot(time, pressure, label=vessel)
    axis.set(xlabel="Time in final cycle (s)", ylabel="Distal pressure (mmHg)")
    axis.grid(alpha=0.25)
    axis.legend(frameon=False, ncol=2)
    fig.savefig(OUT / "circle_of_willis_carotid_pressure.png", dpi=200)
    plt.close(fig)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    inventories = {}
    metadata = {}
    for name, path in MODELS.items():
        rows, model_metadata = inventory_model(name, path)
        inventories[name] = rows
        metadata[name] = model_metadata
        write_csv(OUT / f"{name}_vessel_inventory.csv", rows)
    write_csv(OUT / "candidate_carotid_sites.csv", carotid_candidates(inventories))

    waveform_vessels = [
        "aortic_arch_I",
        "common_carotid_R",
        "external_carotid_R",
        "internal_carotid_R",
        "common_carotid_L",
        "external_carotid_L",
        "internal_carotid_L",
    ]
    metrics = [waveform_metrics(vessel) for vessel in waveform_vessels]
    write_csv(OUT / "adan56_waveform_metrics.csv", metrics)
    plot_waveforms(waveform_vessels[:4])

    cow_vessels = [
        "10-L-ext-carotid",
        "18-L-int-carotidII",
        "13-R-ext-carotid",
        "21-R-int-carotidII",
    ]
    cow_metrics = []
    if all((COW_BASELINE / f"{vessel}_P.last").exists() for vessel in cow_vessels):
        cow_metrics = [
            waveform_metrics(vessel, COW_BASELINE, "alastruey2007") for vessel in cow_vessels
        ]
        write_csv(OUT / "circle_of_willis_waveform_metrics.csv", cow_metrics)
        plot_cow_waveforms(cow_vessels)

    manifest = {
        "openbf_revision": "928c046906687c1347bf5496b47325acd0b2c032",
        "models": metadata,
        "baseline_directory": str(BASELINE),
        "baseline_waveform_files_sha256": {
            f"{vessel}_{quantity}": sha256(BASELINE / f"{vessel}_{quantity}.last")
            for vessel in waveform_vessels
            for quantity in ("P", "Q")
        },
        "distance_definition": "shortest directed cumulative configured segment length from a graph root to the vessel distal node",
        "waveform_position": "last spatial column (distal end), final stored cycle",
        "circle_of_willis_control_directory": str(COW_BASELINE) if cow_metrics else None,
    }
    (OUT / "audit_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"output": str(OUT), "models": metadata, "adan56_waveforms": metrics,
                      "circle_of_willis_waveforms": cow_metrics}, indent=2))


if __name__ == "__main__":
    main()
