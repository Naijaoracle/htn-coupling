#!/usr/bin/env python3
"""Rebuild search result rows from saved Pulse traces after an interrupted run."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

import run_pressure_matched_route_search as search

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/pressure_matched_routes"
CASES = OUT / "private/cases"
CASE_PATTERNS = (
    re.compile(r"^coarse_(mild|intermediate|higher)_R([0-9.]+)_C([0-9.]+)$"),
    re.compile(r"^refine_(mild|intermediate|higher)_([0-9.]+)_R([0-9.]+)_C([0-9.]+)$"),
    re.compile(r"^targeted_(mild|intermediate|higher)_R([0-9.]+)_C([0-9.]+)$"),
    re.compile(r"^confirm_(mild|intermediate|higher)_\d+_R([0-9.]+)_C([0-9.]+)$"),
)


def parse_case(name: str) -> dict | None:
    for index, pattern in enumerate(CASE_PATTERNS):
        match = pattern.match(name)
        if not match:
            continue
        fields = match.groups()
        if index == 1:
            target, step, resistance, compliance = fields
            return {"target": target, "R": float(resistance), "C": float(compliance),
                    "refinement_step": float(step), "route": "modifier"}
        target, resistance, compliance = fields
        return {"target": target, "R": float(resistance), "C": float(compliance),
                "route": "modifier"}
    return None


def main() -> None:
    protocol = search.load_protocol()
    direct = pd.read_csv(OUT / "direct_states.csv").set_index("target")
    rows = []
    for folder in sorted(CASES.iterdir()):
        if not folder.is_dir():
            continue
        job = parse_case(folder.name)
        if job is None:
            continue
        reference = direct.loc[job["target"]]
        row = {"case_id": folder.name, **job,
               "requested_systolic_mmHg": float(reference.requested_systolic_mmHg),
               "requested_diastolic_mmHg": float(reference.requested_diastolic_mmHg),
               "achieved_systolic_mmHg": float(reference.systolic_mmHg),
               "achieved_diastolic_mmHg": float(reference.diastolic_mmHg)}
        trace_path = folder / "stable_trace.csv.gz"
        if not trace_path.is_file():
            row.update(status="no_saved_trace", stationarity_pass=False)
            rows.append(row)
            continue
        trace = pd.read_csv(trace_path)
        values = search.stage6.endpoint(trace)
        stability = search.stationarity_metrics(trace, protocol)
        row.update(status="ok", **values, **stability,
                   **search.stage6.log_metrics(folder / "pulse.log"))
        row["stroke_volume_mL"] = (row["cardiac_output_L_min"] * 1000 /
                                   row["heart_rate_per_min"])
        row["systolic_residual_mmHg"] = (
            row["systolic_mmHg"] - row["achieved_systolic_mmHg"])
        row["diastolic_residual_mmHg"] = (
            row["diastolic_mmHg"] - row["achieved_diastolic_mmHg"])
        row["J"] = row["systolic_residual_mmHg"] ** 2 + row["diastolic_residual_mmHg"] ** 2
        row["pressure_match_pass"] = search._passes(row, reference, protocol)
        rows.append(row)
    frame = pd.DataFrame(rows).sort_values(["target", "J"], na_position="last")
    frame.to_csv(OUT / "reconstructed_completed_cases.csv", index=False)
    print(f"Reconstructed {len(frame)} case folders; saved {int(frame.status.eq('ok').sum())} traces")
    print(frame.groupby(["target", "status"]).size().to_string())
    print("Stationary match candidates:")
    passing = frame[frame.pressure_match_pass.eq(True)]
    print(passing[["case_id", "R", "C", "systolic_mmHg", "diastolic_mmHg",
                   "systolic_residual_mmHg", "diastolic_residual_mmHg"]].to_string(index=False))
    formal = frame[frame.case_id.str.startswith(("coarse_", "refine_"))].copy()
    formal["_step_rank"] = formal.refinement_step.fillna(0.0)
    formal = formal.sort_values(["target", "R", "C", "_step_rank"])
    formal = formal.drop_duplicates(["target", "R", "C"], keep="last").drop(columns="_step_rank")
    formal.to_csv(OUT / "search_evaluations.csv", index=False)
    frame[frame.case_id.str.startswith("coarse_")].to_csv(
        OUT / "coarse_search_evaluations.csv", index=False)
    for step, checkpoint in formal[formal.refinement_step.notna()].groupby("refinement_step"):
        checkpoint.to_csv(OUT / f"search_checkpoint_refine_{step:g}.csv", index=False)
    confirmations = frame[frame.case_id.str.startswith("confirm_")].copy()
    comparison_rows = []
    for rerun in confirmations.to_dict("records"):
        prior = formal[(formal.target == rerun["target"]) &
                       (formal.R == rerun["R"]) & (formal.C == rerun["C"])]
        first = prior.iloc[-1].to_dict() if len(prior) else {}
        rerun["first_run_case_id"] = first.get("case_id", "")
        rerun["first_run_systolic_mmHg"] = first.get("systolic_mmHg", float("nan"))
        rerun["first_run_diastolic_mmHg"] = first.get("diastolic_mmHg", float("nan"))
        rerun["first_run_stationarity_pass"] = bool(first.get("stationarity_pass", False))
        rerun["first_run_pressure_match_pass"] = bool(first.get("pressure_match_pass", False))
        rerun["rerun_minus_first_systolic_mmHg"] = (
            rerun.get("systolic_mmHg", float("nan")) - rerun["first_run_systolic_mmHg"])
        rerun["rerun_minus_first_diastolic_mmHg"] = (
            rerun.get("diastolic_mmHg", float("nan")) - rerun["first_run_diastolic_mmHg"])
        comparison_rows.append(rerun)
    comparisons = pd.DataFrame(comparison_rows)
    comparisons.to_csv(OUT / "confirmation_evaluations.csv", index=False)
    confirmed = comparisons[
        comparisons.pressure_match_pass.eq(True) &
        comparisons.first_run_pressure_match_pass.eq(True) &
        comparisons.first_run_stationarity_pass.eq(True)
    ]
    confirmed.to_csv(OUT / "confirmed_solutions.csv", index=False)
    if not confirmed.empty:
        confirmed["distance_from_stock"] = (
            (confirmed.R - 1.0) ** 2 + (confirmed.C - 1.0) ** 2) ** 0.5
        provisional = confirmed.sort_values(
            ["target", "distance_from_stock", "J", "R", "C"],
            ascending=[True, True, True, True, False]).groupby(
                "target", as_index=False).first()
        provisional["selection_scope"] = (
            "nearest among confirmed candidates; 0.001 refinement not completed")
        provisional.to_csv(OUT / "provisional_primary_confirmed.csv", index=False)
    print(f"Saved {len(formal)} formal search rows, per-step checkpoints, "
          f"{len(comparisons)} independent reruns, and {len(confirmed)} confirmed matches")


if __name__ == "__main__":
    main()
