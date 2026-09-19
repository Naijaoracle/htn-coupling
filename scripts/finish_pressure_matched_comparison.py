#!/usr/bin/env python3
"""Finish high-target waveform attribution and summarize restart diagnostics."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import stage5_pipeline as stage5
from run_pressure_matched_route_search import load_protocol, stationarity_metrics

RESULTS = ROOT / "results/pressure_matched_routes"
COUPLED = RESULTS / "coupled_openbf"
CASES = RESULTS / "private/cases"
NOISE = ROOT / "results/stage5/metric_noise_floors.csv"
PULSE = Path(os.environ.get("PULSE_ROOT", "/tmp/pulse-htn-a04"))
OPENBF_RUNNER = ROOT / "scripts/run_stage4_openbf.jl"
PRIMARY = {
    "direct": "direct_inlet_direct_resistance",
    "modifier": "modifier_inlet_modifier_resistance",
}
FACTORIAL = {
    ("direct", "direct"): "direct_inlet_direct_resistance",
    ("direct", "modifier"): "direct_inlet_modifier_resistance",
    ("modifier", "direct"): "modifier_inlet_direct_resistance",
    ("modifier", "modifier"): "modifier_inlet_modifier_resistance",
}
RESTART_PAIRS = {
    "mild": {
        "first": "refine_mild_0.02_R1.300_C0.720",
        "reruns": ["confirm_mild_1_R1.300_C0.720", "confirm_mild_2_R1.300_C0.720"],
    },
    "intermediate": {
        "first": "refine_intermediate_0.02_R1.720_C0.600",
        "reruns": ["confirm_intermediate_1_R1.720_C0.600",
                   "confirm_intermediate_2_R1.720_C0.600"],
    },
}
SITES = stage5.SITES
PRIMARY_METRICS = (
    "systolic_mmHg", "diastolic_mmHg", "mean_mmHg", "pulse_pressure_mmHg",
    "time_to_peak_phase", "phase_aligned_normalised_shape_rmse",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def phase_aligned_shape(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    # Use the pre-existing Stage 5 full-cycle, min-max-normalized metric and
    # its bounded +/-5% phase alignment. Reflected-wave features are excluded.
    rmse, shift = stage5.aligned_shape_rmse(a, b)
    return rmse, shift


def run_repeat(case: str) -> dict:
    config = COUPLED / "configs" / case / f"{case}.yaml"
    result = COUPLED / "repeat_runs" / case
    result.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    proc = subprocess.run(
        ["julia", f"--project={ROOT}", str(OPENBF_RUNNER), str(config), str(result)],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (result / "runner.log").write_text(proc.stdout)
    return {"case": case, "status": "ok" if proc.returncode == 0 else "failed",
            "returncode": proc.returncode, "wall_s": time.monotonic() - started,
            "yaml_sha256": sha256(config),
            "inlet_sha256": sha256(COUPLED / "configs" / case /
                                    f"{case}_inlet.dat")}


def ensure_repeats() -> pd.DataFrame:
    status_path = COUPLED / "repeat_run_status.csv"
    if status_path.is_file():
        previous = pd.read_csv(status_path)
        if set(previous.case) == set(PRIMARY.values()) and previous.status.eq("ok").all():
            return previous
    rows = [run_repeat(case) for case in PRIMARY.values()]
    frame = pd.DataFrame(rows)
    frame.to_csv(status_path, index=False)
    if not frame.status.eq("ok").all():
        raise RuntimeError("An independent OpenBF repeat failed; inspect repeat_runs/*/runner.log")
    return frame


def waveform_tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    noise = pd.read_csv(NOISE)
    floor_map = {(row.vessel, row.metric): float(row.noise_floor)
                 for row in noise.itertuples(index=False)}
    main_rows = []
    for site in SITES:
        direct_dir = COUPLED / "runs" / PRIMARY["direct"]
        modifier_dir = COUPLED / "runs" / PRIMARY["modifier"]
        dm = stage5.waveform_metrics(direct_dir, PRIMARY["direct"], site)
        mm = stage5.waveform_metrics(modifier_dir, PRIMARY["modifier"], site)
        phase, dp = stage5.phase_pressure(direct_dir, site)
        _, mp = stage5.phase_pressure(modifier_dir, site)
        shape, shift = phase_aligned_shape(dp, mp)
        pair_values = {**dm, "phase_aligned_normalised_shape_rmse": shape,
                       "optimal_phase_shift": shift}
        modifier_values = {**mm}
        for metric in PRIMARY_METRICS:
            floor_metric = ("phase_aligned_normalised_shape_rmse"
                            if metric == "phase_aligned_normalised_shape_rmse" else metric)
            floor = floor_map[(site, floor_metric)]
            if metric == "phase_aligned_normalised_shape_rmse":
                direct_value, modifier_value, effect = np.nan, np.nan, np.nan
                absolute_effect = shape
            else:
                direct_value = float(pair_values[metric])
                modifier_value = float(modifier_values[metric])
                effect = direct_value - modifier_value
                absolute_effect = abs(effect)
            ratio = absolute_effect / floor if floor > 0 else np.nan
            main_rows.append({
                "site": site, "metric": metric,
                "direct_route_value": direct_value,
                "modifier_route_value": modifier_value,
                "direct_minus_modifier": effect,
                "absolute_effect": absolute_effect, "stage4_6_perturbation_floor": floor,
                "effect_to_floor_ratio": ratio,
                "attribution_threshold_ratio": 1.25,
                "clears_1p25x_floor": bool(np.isfinite(ratio) and ratio >= 1.25),
                "phase_shift_direct_vs_modifier": shift if metric.startswith("phase_aligned") else np.nan,
                "comparison": "direct inlet + direct SVR resistance vs modifier inlet + modifier SVR resistance",
            })
    primary = pd.DataFrame(main_rows)
    primary.to_csv(COUPLED / "primary_noise_attribution.csv", index=False)

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.8), sharex=True,
                             constrained_layout=True)
    site_titles = {"aortic_arch_I": "Aortic arch I",
                   "external_carotid_R": "Right external carotid",
                   "internal_carotid_R": "Right internal carotid"}
    colors = {"direct": "#245b9e", "modifier": "#b33b2e"}
    for ax, site in zip(axes, SITES):
        for route, case in PRIMARY.items():
            phase, pressure = stage5.phase_pressure(COUPLED / "runs" / case, site)
            normalized = (pressure - pressure.min()) / np.ptp(pressure)
            ax.plot(phase, normalized, color=colors[route], linewidth=2,
                    label=f"{route.title()} route")
        row = primary[(primary.site == site) &
                      (primary.metric == "phase_aligned_normalised_shape_rmse")].iloc[0]
        ax.set_title(site_titles[site])
        ax.set_xlabel("Cardiac-cycle phase")
        ax.grid(alpha=.2)
        ax.text(.03, .04,
                f"Aligned RMSE {row.absolute_effect:.3f}\n"
                f"Stage 4.6 floor {row.stage4_6_perturbation_floor:.3f}\n"
                f"Effect/floor {row.effect_to_floor_ratio:.2f}x",
                transform=ax.transAxes, fontsize=9,
                bbox={"facecolor": "white", "alpha": .85, "edgecolor": "0.8"})
    axes[0].set_ylabel("Min-max normalized pressure")
    axes[-1].legend(loc="upper right", fontsize=9)
    fig.savefig(COUPLED / "primary_waveform_noise_attribution.png", dpi=180)
    plt.close(fig)

    # One-factor waveform contrasts from the completed 2x2 sensitivity design.
    factorial_rows = []
    for site in SITES:
        curves = {}
        for factor, case in FACTORIAL.items():
            curves[factor] = stage5.phase_pressure(COUPLED / "runs" / case, site)[1]
        pairs = []
        for resistance in ("direct", "modifier"):
            pairs.append(("inlet", resistance,
                          FACTORIAL[("direct", resistance)],
                          FACTORIAL[("modifier", resistance)]))
        for inlet in ("direct", "modifier"):
            pairs.append(("resistance", inlet,
                          FACTORIAL[(inlet, "direct")],
                          FACTORIAL[(inlet, "modifier")]))
        floor = floor_map[(site, "phase_aligned_normalised_shape_rmse")]
        for changed_factor, held_level, case_a, case_b in pairs:
            a_key = next(k for k, v in FACTORIAL.items() if v == case_a)
            b_key = next(k for k, v in FACTORIAL.items() if v == case_b)
            rmse, shift = phase_aligned_shape(curves[a_key], curves[b_key])
            ratio = rmse / floor
            factorial_rows.append({
                "site": site, "changed_factor": changed_factor,
                "held_factor_level": held_level, "case_a": case_a, "case_b": case_b,
                "phase_aligned_normalised_shape_rmse": rmse,
                "optimal_phase_shift": shift,
                "stage4_6_perturbation_floor": floor,
                "effect_to_floor_ratio": ratio,
                "clears_1p25x_floor": bool(ratio >= 1.25),
            })
    factorial = pd.DataFrame(factorial_rows)
    factorial.to_csv(COUPLED / "factorial_shape_attribution.csv", index=False)

    repeat_rows = []
    for case in PRIMARY.values():
        base_dir = COUPLED / "runs" / case
        repeat_dir = COUPLED / "repeat_runs" / case
        for site in SITES:
            bm = stage5.waveform_metrics(base_dir, case, site)
            rm = stage5.waveform_metrics(repeat_dir, case, site)
            base_p = stage5.phase_pressure(base_dir, site)[1]
            repeat_p = stage5.phase_pressure(repeat_dir, site)[1]
            shape, shift = phase_aligned_shape(base_p, repeat_p)
            for metric in ("systolic_mmHg", "diastolic_mmHg", "mean_mmHg",
                           "pulse_pressure_mmHg", "time_to_peak_phase"):
                repeat_rows.append({
                    "case": case, "site": site, "metric": metric,
                    "original": bm[metric], "independent_repeat": rm[metric],
                    "repeat_minus_original": rm[metric] - bm[metric],
                    "phase_aligned_shape_rmse": shape,
                    "optimal_phase_shift": shift,
                    "repeat_converged": bool(rm["openbf_converged"]),
                    "repeat_cycles": rm["openbf_cycles"],
                })
    repeats = pd.DataFrame(repeat_rows)
    repeats.to_csv(COUPLED / "repeatability_metrics.csv", index=False)
    return primary, factorial, repeats


def restart_diagnostics() -> tuple[pd.DataFrame, dict]:
    protocol = load_protocol()
    direct = pd.read_csv(RESULTS / "direct_states.csv").set_index("target")
    base_state = ROOT / "results/stage2/private/cache/StandardMale_stage2_baseline.json"
    rows = []
    for target, pair in RESTART_PAIRS.items():
        direct_row = direct.loc[target]
        for role, case in [("first_search_run", pair["first"])] + [
                (f"independent_rerun_{i+1}", name)
                for i, name in enumerate(pair["reruns"])]:
            folder = CASES / case
            trace = pd.read_csv(folder / "stable_trace.csv.gz")
            log = (folder / "pulse.log").read_text(errors="replace")
            bins = stationarity_metrics(trace, protocol)
            endpoint = trace.median(numeric_only=True)
            convergence = re.findall(
                r"Convergence took ([0-9.]+)s to simulate ([0-9.]+)s", log)
            event_lines = [line.strip() for line in log.splitlines()
                           if any(term in line for term in (
                               "IntracranialHypotension", "Baroreceptors Saturated",
                               "Event Bradycardia"))]
            revision_match = re.search(r"GitHash : ([0-9a-f]+)", log)
            rows.append({
                "target": target, "role": role, "case_id": case,
                "R": 1.3 if target == "mild" else 1.72,
                "C": 0.72 if target == "mild" else 0.6,
                "direct_target_sbp_mmHg": float(direct_row.systolic_mmHg),
                "direct_target_dbp_mmHg": float(direct_row.diastolic_mmHg),
                "rerun_sbp_mmHg": float(endpoint.systolic_mmHg),
                "rerun_dbp_mmHg": float(endpoint.diastolic_mmHg),
                "rerun_map_mmHg": float(endpoint.map_mmHg),
                "rerun_hr_bpm": float(endpoint.heart_rate_per_min),
                "rerun_co_L_min": float(endpoint.cardiac_output_L_min),
                **bins,
                "pulse_git_hash_from_log": revision_match.group(1) if revision_match else "",
                "convergence_wall_s": float(convergence[-1][0]) if convergence else np.nan,
                "convergence_simulated_s": float(convergence[-1][1]) if convergence else np.nan,
                "event_log_lines": " | ".join(event_lines),
                "trace_sha256": sha256(folder / "stable_trace.csv.gz"),
                "log_sha256": sha256(folder / "pulse.log"),
            })
    frame = pd.DataFrame(rows)
    frame.to_csv(RESULTS / "restart_instability_diagnostics.csv", index=False)
    source_search = subprocess.run(
        ["rg", "-n", "rand\\(|srand|mt19937|random_device|uniform_real_distribution|normal_distribution",
         str(PULSE / "src/cpp/engine"), str(PULSE / "src/cpp/cdm")],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    source_matches = [line for line in source_search.stdout.splitlines()
                      if line.strip()]
    diagnosis = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "pulse_source_revision": subprocess.check_output(
            ["git", "-C", str(PULSE), "rev-parse", "HEAD"], text=True).strip(),
        "common_serialized_stock_state": str(base_state),
        "common_stock_state_sha256": sha256(base_state),
        "all_saved_reruns_use_same_logged_pulse_revision": bool(
            frame.pulse_git_hash_from_log.nunique() == 1),
        "repeat_outcome_identical_within_each_target": {
            target: bool(group[group.role.str.startswith("independent")].
                         groupby(["rerun_sbp_mmHg", "rerun_dbp_mmHg"]).size().max()
                         == 2)
            for target, group in frame.groupby("target")
        },
        "common_rng_api_search_match_count": len(source_matches),
        "common_rng_api_search_matches": source_matches[:50],
        "interpretation": (
            "The saved first runs and independent repeats start from the same stock-state file, "
            "use the same modifier coordinates, and identify the same pinned Pulse revision, "
            "yet land on different pressure trajectories. The source review found a state-load "
            "defect: m_Stage7ResettingEnabled is a plain bool, not initialized by NervousModel "
            "Clear/SetUp and not included in PBPhysiology serialization. PBPhysiology::Load calls "
            "Clear, SetUp, and then restores serialized NervousData, leaving that flag indeterminate "
            "when patient reset parameters are absent. The two-setting transition diagnostic is "
            "consistent with this defect: mild loaded with a reset midpoint and extreme scales and "
            "collapsed; intermediate first loaded without a reset midpoint and remained stable; "
            "a semantically unchanged reload of the intermediate state then entered the low-pressure "
            "branch. Resetting mild scales at the boundary blunted the collapse. This is the leading "
            "explanation for restart branch variation; a deterministic source fix and regression test "
            "are needed to close it."
        ),
        "limits": [
            "Only the instrumented mild and intermediate transition checks have high-rate tracking; the original accepted/repeat runs do not.",
            "The source defect is established by inspection, but a deterministic source fix plus repeatability regression is still required to close the causal test.",
            "The tracking request does not expose the internal baroreceptor effectiveness parameter or sympathetic fraction."
        ],
    }
    transition_summary = RESULTS / "private/restart_transition_diagnostic/summary.json"
    if transition_summary.is_file():
        diagnosis["restart_transition_control"] = json.loads(transition_summary.read_text())
    diagnosis["state_restore_source_review"] = {
        "source_revision": diagnosis["pulse_source_revision"],
        "flag": "NervousModel::m_Stage7ResettingEnabled",
        "flag_type": "plain bool without a default member initializer",
        "clear_assigns_flag": False,
        "setup_assigns_flag": False,
        "initialize_assigns_from_patient_fields": True,
        "nervous_data_serializes_flag": False,
        "load_sequence": "PBPhysiology::Load calls dst.Clear(), dst.SetUp(), then restores serialized fields",
        "stock_state_has_stage7_patient_reset_fields": any(
            key.startswith("Baroreflex") for key in json.loads(base_state.read_text())["CurrentPatient"]
        ),
        "source_files": [
            "src/cpp/engine/common/system/physiology/NervousModel.h",
            "src/cpp/engine/common/system/physiology/NervousModel.cpp",
            "src/cpp/engine/io/protobuf/PBPhysiology.cpp",
        ],
    }
    instrumented_dir = RESULTS / "private/restart_instrumentation/mild_R1.300_C0.720"
    instrumented_summary = instrumented_dir / "summary.json"
    instrumented_trace = instrumented_dir / "instrumented_trace.csv.gz"
    if instrumented_summary.is_file() and instrumented_trace.is_file():
        diagnosis["instrumented_mild_repeat"] = {
            "summary": json.loads(instrumented_summary.read_text()),
            "trace_path": str(instrumented_trace),
            "trace_sha256": sha256(instrumented_trace),
            "pulse_log_path": str(instrumented_dir / "pulse.log"),
            "pulse_log_sha256": sha256(instrumented_dir / "pulse.log"),
        }
        track_path = instrumented_dir / "during_stabilization.csv"
        if track_path.is_file():
            track = pd.read_csv(track_path)
            time_col = "Time(s)"
            def interval_summary(start: float, end: float) -> dict:
                window = track[(track[time_col] >= start) & (track[time_col] < end)]
                fields = ["MeanArterialPressure(mmHg)", "HeartRate(1/min)",
                          "SystemicVascularResistance(mmHg_s/mL)",
                          "BaroreceptorHeartRateScale", "BaroreceptorResistanceScale",
                          "BaroreceptorComplianceScale", "IntracranialPressure(mmHg)"]
                return {field: {"first": float(window[field].iloc[0]),
                                "last": float(window[field].iloc[-1]),
                                "minimum": float(window[field].min()),
                                "maximum": float(window[field].max())}
                        for field in fields if len(window)}
            scale_hr = track["BaroreceptorHeartRateScale"]
            scale_r = track["BaroreceptorResistanceScale"]
            map_series = track["MeanArterialPressure(mmHg)"]
            hr_series = track["HeartRate(1/min)"]
            diagnosis["instrumented_mild_repeat"]["during_stabilization"] = {
                "track_path": str(track_path), "track_sha256": sha256(track_path),
                "sample_count": len(track), "time_start_s": float(track[time_col].min()),
                "time_end_s": float(track[time_col].max()),
                "first_hr_scale_below_0p5_s": float(track.loc[scale_hr < 0.5, time_col].iloc[0]),
                "first_resistance_scale_below_0p8_s": float(track.loc[scale_r < 0.8, time_col].iloc[0]),
                "first_map_below_90_mmHg_s": float(track.loc[map_series < 90, time_col].iloc[0]),
                "first_hr_below_60_bpm_s": float(track.loc[hr_series < 60, time_col].iloc[0]),
                "windows": {f"{a:g}_{b:g}_s": interval_summary(a, b)
                            for a, b in ((590, 600), (600, 601), (601, 602), (602, 603), (603, 604))},
            }
    (RESULTS / "restart_instability_diagnosis.json").write_text(
        json.dumps(diagnosis, indent=2) + "\n")
    return frame, diagnosis


def main() -> None:
    status = ensure_repeats()
    if len(status) != 2 or not status.status.eq("ok").all():
        raise RuntimeError("Primary OpenBF independent repeats incomplete")
    primary, factorial, repeats = waveform_tables()
    restart, diagnosis = restart_diagnostics()
    print("Primary paired waveform attribution:")
    print(primary[["site", "metric", "direct_minus_modifier",
                   "stage4_6_perturbation_floor", "effect_to_floor_ratio",
                   "clears_1p25x_floor"]].to_string(index=False))
    print("\nFactorial shape contrasts:")
    print(factorial[["site", "changed_factor", "held_factor_level",
                     "phase_aligned_normalised_shape_rmse",
                     "effect_to_floor_ratio", "clears_1p25x_floor"]].to_string(index=False))
    print("\nRestart findings:")
    print(restart[["target", "role", "rerun_sbp_mmHg", "rerun_dbp_mmHg",
                   "stationarity_pass", "convergence_simulated_s"]].to_string(index=False))
    print(json.dumps(diagnosis, indent=2))


if __name__ == "__main__":
    main()
