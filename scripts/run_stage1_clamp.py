#!/usr/bin/env python3
"""Quantify cohort exclusion by the Pulse adult patient definition.

The primary analysis uses HAALSI Wave 1's published derived mean blood
pressures.  Aggregate outputs are written without participant identifiers.
An optional comparator can be supplied after HRS or ELSA has been obtained
and standardized to the command-line column names.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


PULSE = {
    "systolic_min_mmHg": 90.0,
    "systolic_max_mmHg": 120.0,
    "diastolic_min_mmHg": 60.0,
    "diastolic_max_mmHg": 80.0,
    "narrow_pulse_max_diastolic_systolic_ratio": 0.75,
    "age_min_years": 18.0,
    "age_max_years": 65.0,
    "height_hard_min_cm": 4.5 * 30.48,
    "height_hard_max_cm": 7.0 * 30.48,
    "bmi_min_kg_m2": 16.0,
    "bmi_max_kg_m2": 30.0,
    "male_height_typical_min_cm": 163.0,
    "male_height_typical_max_cm": 190.0,
    "female_height_typical_min_cm": 151.0,
    "female_height_typical_max_cm": 175.5,
}

HAALSI_COLUMNS = {
    "prim_key": "participant_id",
    "rage": "age_years",
    "rsex": "sex_code",
    "c_bs_mean_sys": "systolic_mmHg",
    "c_bs_mean_dia": "diastolic_mmHg",
    "c_bs_height": "height_cm",
    "c_bs_weight": "weight_kg",
    "c_bs_bmi": "published_bmi_kg_m2",
    "bs012_2_": "systolic_reading_2_mmHg",
    "bs012_3_": "systolic_reading_3_mmHg",
    "bs013_2_": "diastolic_reading_2_mmHg",
    "bs013_3_": "diastolic_reading_3_mmHg",
}


def percent(count: int, denominator: int) -> float:
    return 100.0 * count / denominator if denominator else float("nan")


def load_haalsi(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, sep="\t", usecols=list(HAALSI_COLUMNS), low_memory=False)
    frame = frame.rename(columns=HAALSI_COLUMNS)
    frame["sex"] = frame["sex_code"].map({1: "Male", 2: "Female"})
    if len(frame) != 5_059:
        raise RuntimeError(f"Expected 5,059 HAALSI Wave 1 records, found {len(frame):,}")
    if frame[["systolic_mmHg", "diastolic_mmHg"]].notna().all(axis=1).sum() != 4_895:
        raise RuntimeError("Expected 4,895 records with both published derived pressures")
    return frame


def load_comparator(args: argparse.Namespace) -> pd.DataFrame | None:
    if args.comparator is None:
        return None
    if not args.comparator_age or not args.comparator_sex:
        raise RuntimeError(
            "A comparator requires --comparator-age and --comparator-sex for the requested breakdowns")
    path = args.comparator
    if path.suffix.lower() == ".dta":
        frame = pd.read_stata(path, convert_categoricals=False)
    else:
        separator = "\t" if path.suffix.lower() in {".tab", ".tsv"} else ","
        frame = pd.read_csv(path, sep=separator, low_memory=False)
    rename = {
        args.comparator_sbp: "systolic_mmHg",
        args.comparator_dbp: "diastolic_mmHg",
    }
    for source, target in (
        (args.comparator_age, "age_years"),
        (args.comparator_sex, "sex"),
        (args.comparator_height, "height_cm"),
        (args.comparator_weight, "weight_kg"),
    ):
        if source:
            rename[source] = target
    missing = [column for column in rename if column not in frame]
    if missing:
        raise RuntimeError(f"Comparator columns not found: {missing}")
    return frame.rename(columns=rename)


def add_pressure_flags(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.dropna(subset=["systolic_mmHg", "diastolic_mmHg"]).copy()
    sbp, dbp = out["systolic_mmHg"], out["diastolic_mmHg"]
    out["sbp_low"] = sbp < PULSE["systolic_min_mmHg"]
    out["sbp_high"] = sbp > PULSE["systolic_max_mmHg"]
    out["dbp_low"] = dbp < PULSE["diastolic_min_mmHg"]
    out["dbp_high"] = dbp > PULSE["diastolic_max_mmHg"]
    out["sbp_outside"] = out["sbp_low"] | out["sbp_high"]
    out["dbp_outside"] = out["dbp_low"] | out["dbp_high"]
    out["pressure_box_excluded"] = out["sbp_outside"] | out["dbp_outside"]
    out["high_any"] = out["sbp_high"] | out["dbp_high"]
    out["low_any"] = out["sbp_low"] | out["dbp_low"]
    out["narrow_pulse"] = dbp > (
        PULSE["narrow_pulse_max_diastolic_systolic_ratio"] * sbp
    )
    out["pressure_engine_excluded"] = out["pressure_box_excluded"] | out["narrow_pulse"]
    out["age_band"] = pd.cut(
        out["age_years"],
        bins=[39, 49, 59, 69, 79, np.inf],
        labels=["40-49", "50-59", "60-69", "70-79", "80+"],
    )

    s_state = np.select([out["sbp_low"], out["sbp_high"]], ["low", "high"], default="in")
    d_state = np.select([out["dbp_low"], out["dbp_high"]], ["low", "high"], default="in")
    out["pressure_category"] = pd.Series(s_state, index=out.index) + "_sbp__" + pd.Series(d_state, index=out.index) + "_dbp"
    return out


def pressure_summary(frame: pd.DataFrame, group: str | None = None) -> pd.DataFrame:
    groups = [("All", frame)] if group is None else frame.groupby(group, observed=True, sort=False)
    rows = []
    for label, subset in groups:
        n = len(subset)
        measures = {
            "inside_pressure_box": ~subset["pressure_box_excluded"],
            "pressure_box_excluded": subset["pressure_box_excluded"],
            "too_high_any_component": subset["high_any"],
            "too_low_any_component": subset["low_any"],
            "high_without_any_low": subset["high_any"] & ~subset["low_any"],
            "low_without_any_high": subset["low_any"] & ~subset["high_any"],
            "mixed_high_and_low": subset["high_any"] & subset["low_any"],
            "outside_one_component_only": subset["sbp_outside"] ^ subset["dbp_outside"],
            "systolic_only_outside": subset["sbp_outside"] & ~subset["dbp_outside"],
            "diastolic_only_outside": ~subset["sbp_outside"] & subset["dbp_outside"],
            "both_components_outside": subset["sbp_outside"] & subset["dbp_outside"],
            "narrow_pulse_additional_exclusion": subset["narrow_pulse"] & ~subset["pressure_box_excluded"],
            "full_pressure_rules_excluded": subset["pressure_engine_excluded"],
        }
        row = {"group": str(label), "n": n}
        for name, mask in measures.items():
            count = int(mask.sum())
            row[f"{name}_n"] = count
            row[f"{name}_pct"] = percent(count, n)
        rows.append(row)
    return pd.DataFrame(rows)


def anthropometry_summary(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    height = frame.dropna(subset=["height_cm"]).copy()
    female = height["sex"].eq("Female")
    typical = np.where(
        female,
        height["height_cm"].between(
            PULSE["female_height_typical_min_cm"], PULSE["female_height_typical_max_cm"]
        ),
        height["height_cm"].between(
            PULSE["male_height_typical_min_cm"], PULSE["male_height_typical_max_cm"]
        ),
    )
    hard_height = ~height["height_cm"].between(
        PULSE["height_hard_min_cm"], PULSE["height_hard_max_cm"]
    )
    rows.append({
        "constraint": "height outside sex-specific typical range (warning)",
        "n_assessed": len(height), "n_outside": int((~typical).sum()),
        "pct_outside": percent(int((~typical).sum()), len(height)), "engine_effect": "warning",
    })
    rows.append({
        "constraint": "height outside 4.5-7.0 ft hard range",
        "n_assessed": len(height), "n_outside": int(hard_height.sum()),
        "pct_outside": percent(int(hard_height.sum()), len(height)), "engine_effect": "error/reject",
    })

    paired = frame.dropna(subset=["height_cm", "weight_kg"]).copy()
    paired["calculated_bmi_kg_m2"] = paired["weight_kg"] / (paired["height_cm"] / 100.0) ** 2
    bmi_low = paired["calculated_bmi_kg_m2"] < PULSE["bmi_min_kg_m2"]
    bmi_high = paired["calculated_bmi_kg_m2"] > PULSE["bmi_max_kg_m2"]
    for label, mask in (
        ("BMI below 16 kg/m2", bmi_low),
        ("BMI above 30 kg/m2", bmi_high),
        ("BMI outside 16-30 kg/m2", bmi_low | bmi_high),
    ):
        rows.append({
            "constraint": label, "n_assessed": len(paired), "n_outside": int(mask.sum()),
            "pct_outside": percent(int(mask.sum()), len(paired)), "engine_effect": "error/reject",
        })
    rows.append({
        "constraint": "weight alone", "n_assessed": int(frame["weight_kg"].notna().sum()),
        "n_outside": 0, "pct_outside": 0.0,
        "engine_effect": "no standalone bound; weight is constrained through BMI",
    })
    return pd.DataFrame(rows), paired


def complete_case_constraints(frame: pd.DataFrame) -> pd.DataFrame:
    required = ["systolic_mmHg", "diastolic_mmHg", "age_years", "sex", "height_cm", "weight_kg"]
    complete = add_pressure_flags(frame.dropna(subset=required))
    complete["age_excluded"] = ~complete["age_years"].between(
        PULSE["age_min_years"], PULSE["age_max_years"]
    )
    complete["height_hard_excluded"] = ~complete["height_cm"].between(
        PULSE["height_hard_min_cm"], PULSE["height_hard_max_cm"]
    )
    bmi = complete["weight_kg"] / (complete["height_cm"] / 100.0) ** 2
    complete["bmi_excluded"] = ~bmi.between(PULSE["bmi_min_kg_m2"], PULSE["bmi_max_kg_m2"])
    flags = ["pressure_engine_excluded", "age_excluded", "height_hard_excluded", "bmi_excluded"]
    complete["any_excluded"] = complete[flags].any(axis=1)
    rows = []
    for flag in flags + ["any_excluded"]:
        count = int(complete[flag].sum())
        rows.append({"constraint": flag, "n_complete": len(complete), "n_excluded": count,
                     "pct_excluded": percent(count, len(complete))})
    for flag in flags:
        only = complete[flag] & ~complete[[other for other in flags if other != flag]].any(axis=1)
        rows.append({"constraint": f"{flag}_only", "n_complete": len(complete),
                     "n_excluded": int(only.sum()), "pct_excluded": percent(int(only.sum()), len(complete))})
    return pd.DataFrame(rows)


def save_plots(by_sex: pd.DataFrame, by_age: pd.DataFrame, constraints: pd.DataFrame, output: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), constrained_layout=True)
    axes[0].bar(by_sex["group"], by_sex["pressure_box_excluded_pct"], color="#35618d")
    axes[0].set_title("HAALSI Wave 1 by sex")
    axes[0].set_ylabel("Outside pressure box (%)")
    axes[0].set_ylim(0, 100)
    axes[1].bar(by_age["group"], by_age["pressure_box_excluded_pct"], color="#a9523f")
    axes[1].set_title("HAALSI Wave 1 by age")
    axes[1].set_ylim(0, 100)
    axes[1].tick_params(axis="x", rotation=30)
    fig.savefig(output / "haalsi_pressure_exclusion_by_sex_age.png", dpi=180)
    plt.close(fig)

    hard = constraints[constraints["constraint"].isin([
        "pressure_engine_excluded", "age_excluded", "height_hard_excluded", "bmi_excluded"
    ])]
    fig, ax = plt.subplots(figsize=(8, 4.5), constrained_layout=True)
    ax.barh(hard["constraint"].str.replace("_", " "), hard["pct_excluded"], color="#35618d")
    ax.set_xlabel("Excluded among complete cases (%)")
    ax.set_xlim(0, 100)
    fig.savefig(output / "haalsi_constraint_comparison.png", dpi=180)
    plt.close(fig)


def audit(name: str, frame: pd.DataFrame, output: Path, include_anthropometry: bool) -> dict:
    pressure = add_pressure_flags(frame)
    overall = pressure_summary(pressure)
    overall.to_csv(output / f"{name}_pressure_summary.csv", index=False)
    categories = pressure["pressure_category"].value_counts().rename_axis("category").reset_index(name="n")
    categories["pct"] = 100.0 * categories["n"] / len(pressure)
    categories.to_csv(output / f"{name}_pressure_categories.csv", index=False)
    result = {"source_rows": len(frame), "valid_derived_pressure_n": len(pressure),
              "pressure": overall.iloc[0].to_dict()}
    if "sex" in pressure:
        by_sex = pressure_summary(pressure.dropna(subset=["sex"]), "sex")
        by_sex.to_csv(output / f"{name}_pressure_by_sex.csv", index=False)
    else:
        by_sex = None
    if "age_years" in pressure:
        by_age = pressure_summary(pressure.dropna(subset=["age_band"]), "age_band")
        by_age.to_csv(output / f"{name}_pressure_by_age.csv", index=False)
    else:
        by_age = None
    if include_anthropometry:
        anthropometry, _ = anthropometry_summary(frame)
        anthropometry.to_csv(output / f"{name}_anthropometry_summary.csv", index=False)
        constraints = complete_case_constraints(frame)
        constraints.to_csv(output / f"{name}_complete_case_constraints.csv", index=False)
        result["anthropometry"] = anthropometry.to_dict(orient="records")
        result["complete_case_constraints"] = constraints.to_dict(orient="records")
        if by_sex is not None and by_age is not None:
            save_plots(by_sex, by_age, constraints, output)
    return result


def parse_args() -> argparse.Namespace:
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--haalsi", type=Path, default=repo.parent / "pulse-physiology-engine" / "dataverse_files" / "HAALSI_baseline_dataverse_14Apr2017.tab")
    parser.add_argument("--output", type=Path, default=repo / "results" / "stage1")
    parser.add_argument("--comparator", type=Path)
    parser.add_argument("--comparator-name", default="comparator")
    parser.add_argument("--comparator-sbp", default="systolic_mmHg")
    parser.add_argument("--comparator-dbp", default="diastolic_mmHg")
    parser.add_argument("--comparator-age")
    parser.add_argument("--comparator-sex")
    parser.add_argument("--comparator-height")
    parser.add_argument("--comparator-weight")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    haalsi = load_haalsi(args.haalsi)
    summary = {
        "pulse_bounds": PULSE,
        "haalsi": audit("haalsi", haalsi, args.output, include_anthropometry=True),
        "strict_readings_2_and_3_complete_n": int(haalsi[[
            "systolic_reading_2_mmHg", "systolic_reading_3_mmHg",
            "diastolic_reading_2_mmHg", "diastolic_reading_3_mmHg",
        ]].notna().all(axis=1).sum()),
    }
    comparator = load_comparator(args)
    if comparator is not None:
        summary[args.comparator_name] = audit(args.comparator_name, comparator, args.output, include_anthropometry=False)
    else:
        summary["comparator_status"] = "not run: no local HRS or ELSA dataset supplied"
    (args.output / "stage1_summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    headline = summary["haalsi"]["pressure"]
    print(f"HAALSI pressure box: {headline['pressure_box_excluded_n']:,}/{headline['n']:,} excluded ({headline['pressure_box_excluded_pct']:.2f}%)")
    print(summary["comparator_status"] if comparator is None else f"Comparator {args.comparator_name} complete")


if __name__ == "__main__":
    main()
