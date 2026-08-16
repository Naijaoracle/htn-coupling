#!/usr/bin/env python3
"""Run and analyse the paired 20-body Stage 5 acute follow-up."""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import wilcoxon
from tqdm import tqdm

from run_stage5_acute import worker

ROOT = Path(__file__).resolve().parents[1]
STAGE2_SAMPLE = ROOT / "results/stage2/private/haalsi_sample_runs.csv"
STAGE5 = ROOT / "results/stage5"
OUT = ROOT / "results/stage5_followup"
PRIVATE = OUT / "private"
SPEC = ROOT / "config/stage5_followup_v1.json"
PROTOCOL = ROOT / "config/stage5_protocol_v1.json"


def select_bodies() -> pd.DataFrame:
    spec = json.loads(SPEC.read_text())
    source = pd.read_csv(STAGE2_SAMPLE)
    source = source[source.body_admissible & source.age_years.between(*spec["age_range_years"])].copy()
    selected = []
    for sex, prefix in (("Male", "M"), ("Female", "F")):
        group = source[source.sex == sex].sort_values(["bmi_kg_m2", "age_years"]).reset_index(drop=True)
        ranks = np.rint(np.linspace(0, len(group)-1, spec["bodies_per_sex"])).astype(int)
        if len(set(ranks)) != spec["bodies_per_sex"]:
            raise RuntimeError("BMI rank selection produced duplicate bodies")
        for order, rank in enumerate(ranks, 1):
            row = group.iloc[rank]
            selected.append({
                "body_id": f"expanded_{prefix}_{order:02d}", "sex": sex,
                "age_years": float(row.age_years), "height_cm": float(row.height_cm),
                "weight_kg": float(row.weight_kg), "bmi_kg_m2": float(row.bmi_kg_m2),
                "within_sex_bmi_rank": int(rank+1), "within_sex_available_n": len(group),
            })
    frame = pd.DataFrame(selected)
    if len(frame) != spec["expanded_acute_bodies"]:
        raise RuntimeError("Expanded body count differs from predeclaration")
    OUT.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUT/"expanded_acute_body_panel.csv", index=False)
    return frame


def jobs() -> list[dict]:
    spec = json.loads(SPEC.read_text())
    protocol = json.loads(PROTOCOL.read_text())
    return [{**body, "phenotype": phenotype, **modifiers,
             "duration_s": spec["duration_s"]}
            for body in select_bodies().to_dict("records")
            for phenotype, modifiers in protocol["phenotypes"].items()]


def run(workers: int) -> None:
    PRIVATE.mkdir(parents=True, exist_ok=True)
    checkpoint = PRIVATE/"expanded_acute_checkpoint.csv"
    previous = pd.read_csv(checkpoint).to_dict("records") if checkpoint.exists() else []
    successful = {(x["body_id"], x["phenotype"]) for x in previous
                  if x.get("status") == "ok"}
    pending = [job for job in jobs() if (job["body_id"], job["phenotype"]) not in successful]
    rows = previous[:]
    if pending:
        with ProcessPoolExecutor(max_workers=workers,
                                 mp_context=mp.get_context("spawn")) as pool:
            futures = [pool.submit(worker, job) for job in pending]
            with tqdm(total=len(futures), desc="Expanded Pulse acute", unit="run") as bar:
                for future in as_completed(futures):
                    result = future.result(); rows.append(result)
                    pd.DataFrame(rows).to_csv(checkpoint, index=False)
                    bar.set_postfix(body=result["body_id"], phenotype=result["phenotype"],
                                    status=result["status"])
                    bar.update()
    frame = pd.DataFrame(rows).drop_duplicates(["body_id", "phenotype"], keep="last")
    frame = frame.sort_values(["body_id", "phenotype"])
    frame.to_csv(OUT/"expanded_acute_run_results.csv", index=False)
    expected = json.loads(SPEC.read_text())["expanded_acute_bodies"]*4
    if len(frame) != expected or not frame.status.eq("ok").all():
        raise RuntimeError(f"Expanded panel incomplete: {len(frame)}/{expected} successful")
    analyse(frame)


def first_below(frame: pd.DataFrame, threshold: float) -> float:
    values = frame.loc[frame.map_mmHg <= threshold, "time_s"]
    return float(values.iloc[0]) if len(values) else np.nan


def fractional_endpoints(results: pd.DataFrame) -> pd.DataFrame:
    fractions = [0.2, 0.3, 0.4]
    rows = []
    # The shared Pulse worker stores trajectories in the original private acute
    # directory. Generic follow-up body IDs prevent linkage to source rows.
    trajectory_root = STAGE5/"private/acute"
    for _, result in results.iterrows():
        trace = pd.read_csv(trajectory_root/f"{result.body_id}__{result.phenotype}.csv.gz")
        baseline = float(trace.loc[trace.time_s.between(0, 29), "map_mmHg"].median())
        row = {"body_id": result.body_id, "sex": result.sex,
               "phenotype": result.phenotype, "baseline_map_mmHg": baseline,
               "time_to_map65_s": first_below(trace, 65.0)}
        for fraction in fractions:
            row[f"time_to_{int(100*fraction)}pct_map_fall_s"] = first_below(
                trace, baseline*(1-fraction))
        rows.append(row)
    frame = pd.DataFrame(rows)
    frame.to_csv(OUT/"expanded_acute_fractional_endpoints.csv", index=False)
    return frame


def holm_adjust(pvalues: dict[str, float]) -> dict[str, float]:
    ordered = sorted(pvalues, key=pvalues.get)
    adjusted, running = {}, 0.0
    m = len(ordered)
    for rank, name in enumerate(ordered):
        value = min(1.0, (m-rank)*pvalues[name])
        running = max(running, value)
        adjusted[name] = running
    return adjusted


def paired_analysis(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    spec = json.loads(SPEC.read_text())
    rng = np.random.default_rng(spec["bootstrap_seed"])
    primary = "time_to_30pct_map_fall_s"
    pivot = frame.pivot(index="body_id", columns="phenotype", values=primary)
    comparisons = ["resistance_dominant", "compliance_dominant", "combined"]
    raw_p, cache = {}, {}
    for phenotype in comparisons:
        pairs = pivot[["normotensive", phenotype]].dropna()
        differences = (pairs[phenotype]-pairs.normotensive).to_numpy()
        raw_p[phenotype] = float(wilcoxon(differences, alternative="two-sided").pvalue)
        cache[phenotype] = differences
    adjusted = holm_adjust(raw_p)
    rows = []
    for phenotype in comparisons:
        differences = cache[phenotype]
        samples = rng.choice(differences, size=(spec["bootstrap_replicates"], len(differences)),
                             replace=True)
        boot = np.median(samples, axis=1)
        rows.append({
            "phenotype_vs_normotensive": phenotype, "paired_bodies_n": len(differences),
            "median_time_difference_s": float(np.median(differences)),
            "mean_time_difference_s": float(np.mean(differences)),
            "bootstrap_95pct_low_s": float(np.quantile(boot, .025)),
            "bootstrap_95pct_high_s": float(np.quantile(boot, .975)),
            "earlier_n": int((differences < 0).sum()),
            "later_n": int((differences > 0).sum()),
            "equal_n": int((differences == 0).sum()),
            "wilcoxon_p": raw_p[phenotype], "holm_adjusted_p": adjusted[phenotype],
        })
    paired = pd.DataFrame(rows)
    paired.to_csv(OUT/"expanded_acute_paired_primary.csv", index=False)

    aggregate_rows = []
    for phenotype, group in frame.groupby("phenotype"):
        row = {"phenotype": phenotype, "bodies_n": len(group),
               "baseline_map_median_mmHg": group.baseline_map_mmHg.median()}
        for metric in ("time_to_20pct_map_fall_s", "time_to_30pct_map_fall_s",
                       "time_to_40pct_map_fall_s", "time_to_map65_s"):
            values = group[metric].dropna()
            row[f"{metric}_n"] = len(values)
            row[f"{metric}_median"] = values.median()
            row[f"{metric}_q1"] = values.quantile(.25)
            row[f"{metric}_q3"] = values.quantile(.75)
        aggregate_rows.append(row)
    aggregate = pd.DataFrame(aggregate_rows)
    aggregate.to_csv(OUT/"expanded_acute_endpoint_summary.csv", index=False)
    return paired, aggregate


def plot(frame: pd.DataFrame) -> None:
    pivot = frame.pivot(index="body_id", columns="phenotype",
                        values="time_to_30pct_map_fall_s")
    order = ["normotensive", "resistance_dominant", "compliance_dominant", "combined"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), constrained_layout=True)
    for _, row in pivot[order].iterrows():
        axes[0].plot(range(4), row, color="gray", alpha=.35, linewidth=1)
    axes[0].plot(range(4), pivot[order].median(), color="black", marker="o",
                 linewidth=2.5, label="median")
    axes[0].set(xticks=range(4), xticklabels=["Norm", "R", "C", "R+C"],
                ylabel="Time to 30% MAP fall (s)", title="Paired within-body trajectories")
    axes[0].legend(); axes[0].grid(axis="y", alpha=.2)
    differences = [pivot[x]-pivot.normotensive for x in order[1:]]
    axes[1].boxplot(differences, tick_labels=["R−Norm", "C−Norm", "R+C−Norm"],
                    showmeans=True)
    axes[1].axhline(0, color="black", linewidth=1)
    axes[1].set(ylabel="Paired time difference (s)", title="Primary endpoint effects")
    axes[1].grid(axis="y", alpha=.2)
    fig.savefig(OUT/"expanded_acute_paired_30pct_map_fall.png", dpi=200)
    plt.close(fig)


def analyse(results: pd.DataFrame | None = None) -> None:
    if results is None:
        results = pd.read_csv(OUT/"expanded_acute_run_results.csv")
    endpoints = fractional_endpoints(results)
    paired, aggregate = paired_analysis(endpoints)
    plot(endpoints)
    summary = {
        "bodies_n": int(endpoints.body_id.nunique()),
        "runs_n": len(endpoints), "all_runs_successful": bool(results.status.eq("ok").all()),
        "primary_endpoint": "time_to_30pct_map_fall_s",
        "paired_results": paired.to_dict("records"),
    }
    (OUT/"expanded_acute_summary.json").write_text(json.dumps(summary, indent=2)+"\n")
    print(aggregate.to_string(index=False))
    print("\nPaired primary endpoint:\n", paired.to_string(index=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "analyse"))
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    run(args.workers) if args.mode == "run" else analyse()


if __name__ == "__main__":
    main()
