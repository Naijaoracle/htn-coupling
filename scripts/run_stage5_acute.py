#!/usr/bin/env python3
"""Run the four Stage 5 phenotypes through haemorrhage on four bodies."""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import re
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from tqdm import tqdm

from run_stage2_tier0 import (BIN, first_below, modify, person_configuration,
                              pulse_symbols, requests, row)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/stage5"
PRIVATE = OUT / "private/acute"
PANEL = ROOT / "config/stage5_acute_panel_v1.json"
PROTOCOL = ROOT / "config/stage5_protocol_v1.json"


def worker(job: dict) -> dict:
    try:
        s = pulse_symbols()

        class Events(s["IEventHandler"]):
            def __init__(self):
                super().__init__()
                self.first = {}

            def handle_event(self, change):
                if change.active and change.event not in self.first:
                    self.first[change.event] = change.sim_time.get_value(s["TimeUnit"].s)

        engine = s["PulseEngine"](data_root_dir=str(BIN))
        engine.log_to_console(False)
        log = PRIVATE / f"{job['body_id']}__{job['phenotype']}.log"
        engine.set_log_filename(str(log))
        spec = {**job, "sample_id": f"stage5_{job['body_id']}"}
        if not engine.initialize_engine(person_configuration(s, spec), requests(s)):
            raise RuntimeError("Pulse body initialisation failed")
        if job["resistance_multiplier"] != 1 or job["compliance_multiplier"] != 1:
            modify(engine, s, job["resistance_multiplier"], job["compliance_multiplier"])
        events = Events()
        engine.set_event_handler(events)
        initial = row(engine.pull_data())
        origin = initial["time_s"]
        rows = [{"body_id": job["body_id"], "phenotype": job["phenotype"], **initial}]

        def bleed(compartment, rate):
            action = s["SEHemorrhage"]()
            action.set_compartment(compartment)
            action.get_flow_rate().set_value(rate, s["VolumePerTimeUnit"].mL_Per_min)
            return action

        for second in range(job["duration_s"]):
            if second == 30:
                engine.process_actions([
                    bleed(s["eHemorrhage_Compartment"].RightLeg, 50),
                    bleed(s["eHemorrhage_Compartment"].VenaCava, 150)])
            elif second == 655:
                engine.process_actions([
                    bleed(s["eHemorrhage_Compartment"].RightLeg, 0),
                    bleed(s["eHemorrhage_Compartment"].VenaCava, 0)])
            if not engine.advance_time_s(1):
                break
            rows.append({"body_id": job["body_id"],
                         "phenotype": job["phenotype"], **row(engine.pull_data())})
        frame = pd.DataFrame(rows)
        frame["engine_time_s"] = frame.time_s
        frame.time_s = frame.time_s-origin
        frame.to_csv(PRIVATE/f"{job['body_id']}__{job['phenotype']}.csv.gz",
                     index=False, compression="gzip")

        def event_time(event_name):
            event = getattr(s["eEvent"], event_name, None)
            value = events.first.get(event, np.nan) if event is not None else np.nan
            if np.isfinite(value):
                return value-origin
            text = log.read_text(errors="replace")
            match = re.search(rf"\[(\d+(?:\.\d+)?)\(s\)\] \[Event {event_name} 1\]", text)
            return float(match.group(1))-origin if match else np.nan

        return {"status": "ok", "body_id": job["body_id"],
                "sex": job["sex"], "age_years": job["age_years"],
                "height_cm": job["height_cm"], "weight_kg": job["weight_kg"],
                "bmi_kg_m2": job["weight_kg"]/(job["height_cm"]/100)**2,
                "phenotype": job["phenotype"],
                "resistance_multiplier": job["resistance_multiplier"],
                "compliance_multiplier": job["compliance_multiplier"],
                "simulated_through_s": float(frame.time_s.max()),
                "time_to_map_below_65_s": first_below(frame, "map_mmHg", 65),
                "time_to_hypovolemic_shock_s": event_time("HypovolemicShock"),
                "time_to_irreversible_state_s": event_time("IrreversibleState"),
                "minimum_cardiac_output_L_min": float(frame.cardiac_output_L_min.min()),
                "minimum_map_mmHg": float(frame.map_mmHg.min()),
                "maximum_heart_rate_per_min": float(frame.heart_rate_per_min.max())}
    except Exception as exc:
        return {"status": "failed", "body_id": job["body_id"],
                "phenotype": job["phenotype"], "error": str(exc),
                "traceback": traceback.format_exc()}


def run(workers: int) -> None:
    PRIVATE.mkdir(parents=True, exist_ok=True)
    panel = json.loads(PANEL.read_text())
    protocol = json.loads(PROTOCOL.read_text())
    jobs = [{**body, "phenotype": phenotype, **modifiers,
             "duration_s": panel["duration_s"]}
            for body in panel["bodies"]
            for phenotype, modifiers in protocol["phenotypes"].items()]
    rows = []
    with ProcessPoolExecutor(max_workers=workers,
                             mp_context=mp.get_context("spawn")) as pool:
        futures = [pool.submit(worker, job) for job in jobs]
        with tqdm(total=len(futures), desc="Pulse Stage 5 acute", unit="run") as progress:
            for future in as_completed(futures):
                result = future.result()
                rows.append(result)
                progress.set_postfix(body=result["body_id"],
                                     phenotype=result["phenotype"],
                                     status=result["status"])
                progress.update()
    frame = pd.DataFrame(rows).sort_values(["phenotype", "body_id"])
    frame.to_csv(OUT/"acute_body_results.csv", index=False)
    if not frame.status.eq("ok").all():
        raise RuntimeError("At least one Stage 5 acute run failed")
    summarise(frame)


def summarise(frame: pd.DataFrame) -> None:
    metrics = ["time_to_map_below_65_s", "time_to_hypovolemic_shock_s",
               "time_to_irreversible_state_s", "minimum_cardiac_output_L_min"]
    rows = []
    for phenotype, group in frame.groupby("phenotype", sort=False):
        row = {"phenotype": phenotype, "bodies_n": len(group)}
        for metric in metrics:
            values = group[metric].dropna()
            row[f"{metric}_n"] = len(values)
            row[f"{metric}_median"] = float(values.median()) if len(values) else np.nan
            row[f"{metric}_min"] = float(values.min()) if len(values) else np.nan
            row[f"{metric}_max"] = float(values.max()) if len(values) else np.nan
        rows.append(row)
    summary = pd.DataFrame(rows)
    summary.to_csv(OUT/"acute_phenotype_spread.csv", index=False)

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), constrained_layout=True)
    for axis, metric, ylabel in zip(
            axes,
            ["time_to_map_below_65_s", "time_to_hypovolemic_shock_s",
             "minimum_cardiac_output_L_min"],
            ["Time to MAP <=65 (s)", "Time to shock event (s)", "Minimum CO (L/min)"]):
        groups = [frame.loc[frame.phenotype == name, metric].dropna().to_numpy()
                  for name in ("normotensive", "resistance_dominant",
                               "compliance_dominant", "combined")]
        axis.boxplot(groups, tick_labels=["Norm", "R", "C", "R+C"], showmeans=True)
        axis.set_ylabel(ylabel)
        axis.grid(axis="y", alpha=.25)
    fig.savefig(OUT/"acute_phenotype_body_spread.png", dpi=180)
    plt.close(fig)
    print(summary.to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    run(args.workers)


if __name__ == "__main__":
    main()
