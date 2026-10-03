from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
APP_ROOT = Path(__file__).resolve().parent
INTENSITIES = (0.05, 0.10, 0.15, 0.20, 0.25, 0.30)
DURATIONS_S = (30, 45, 60)
DELAYS_S = (0, 5, 10, 15)
CONDITIONING_SIGMA_BPM = 10.0
PULSE_VERSION = "4.3.2-e8a36497b"
BASELINE_FILENAME = "StandardMale_stage2_baseline.json"
BASELINE_SHA256 = "2f1c4416afec84b1b903988aa98833b7e672169a072c6f826a45aa90a7ef2115"
PROCESSING_STAGE = "hr_constrained_pulse_ensemble_candidate_v1"


def candidate_specs() -> list[dict]:
    specs = []
    for intensity in INTENSITIES:
        for duration_s in DURATIONS_S:
            for delay_s in DELAYS_S:
                candidate_id = (
                    f"pulse_exercise_i{int(round(intensity * 100)):02d}_"
                    f"d{duration_s:02d}_delay{delay_s:02d}"
                )
                specs.append({
                    "candidate_id": candidate_id,
                    "exercise_intensity": intensity,
                    "exercise_duration_s": duration_s,
                    "cessation_to_recovery_origin_delay_s": delay_s,
                })
    return specs


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _pulse_run(job: dict) -> dict:
    """Run one fresh Pulse trajectory; imports occur inside worker processes."""
    try:
        pulse_bin = Path(job["pulse_bin"])
        pulse_python = pulse_bin.parent / "python"
        sys.path[:0] = [str(pulse_python), str(pulse_bin)]
        from pulse.cdm.engine import SEDataRequest, SEDataRequestManager
        from pulse.cdm.patient_actions import SEExercise
        from pulse.cdm.scalars import FrequencyUnit
        from pulse.engine.PulseEngine import PulseEngine

        state_file = Path(job["state_file"])
        request = SEDataRequest.create_physiology_request("HeartRate", FrequencyUnit.Per_min)
        requests = SEDataRequestManager([request])
        engine = PulseEngine(data_root_dir=str(pulse_bin))
        engine.log_to_console(False)
        engine.set_log_filename(job["log_file"])
        if not engine.serialize_from_file(str(state_file), requests):
            raise RuntimeError("Pulse failed to load the frozen StandardMale checkpoint")

        exercise = SEExercise()
        exercise.get_intensity().set_value(float(job["exercise_intensity"]))
        exercise.set_comment("Predeclared exercise-recovery ensemble candidate")
        engine.process_action(exercise)
        for _ in range(int(job["exercise_duration_s"])):
            if not engine.advance_time_s(1.0):
                raise RuntimeError("Pulse stopped during the exercise action")

        cessation = SEExercise()
        cessation.get_intensity().set_value(0.0)
        cessation.set_comment("Predeclared abrupt exercise cessation")
        engine.process_action(cessation)
        for _ in range(int(job["cessation_to_recovery_origin_delay_s"])):
            if not engine.advance_time_s(1.0):
                raise RuntimeError("Pulse stopped during the pre-capture delay")

        samples = []
        for elapsed_s in range(1, 61):
            if not engine.advance_time_s(1.0):
                raise RuntimeError(f"Pulse stopped at recovery-relative second {elapsed_s}")
            values = np.asarray(engine.pull_data(), dtype=float).reshape(-1)
            if len(values) < 2 or not np.isfinite(values[:2]).all():
                raise RuntimeError(f"Pulse returned non-finite or incomplete output at {elapsed_s} s")
            samples.append({"time_s": float(elapsed_s), "heart_rate": float(values[1])})
        return {**job, "status": "ok", "samples": samples}
    except Exception as exc:
        return {**job, "status": "failed", "error": f"{type(exc).__name__}: {exc}", "samples": []}


def run(args: argparse.Namespace) -> tuple[Path, Path, dict]:
    pulse_home = Path(args.pulse_home).resolve()
    pulse_bin = (Path(args.pulse_bin).resolve() if args.pulse_bin else pulse_home / "build/install/bin")
    pulse_python = pulse_home / "build/install/python"
    state_file = Path(args.state_file).resolve()
    output = Path(args.output).resolve()
    if not pulse_bin.is_dir() or not (pulse_bin / "PyPulse.cpython-312-x86_64-linux-gnu.so").exists():
        raise FileNotFoundError(f"Pulse Python bindings not found in {pulse_bin}")
    if not pulse_python.is_dir():
        raise FileNotFoundError(f"Pulse Python package not found in {pulse_python}")
    if not state_file.is_file():
        raise FileNotFoundError(f"Frozen baseline checkpoint not found: {state_file}")
    actual_state_hash = sha256(state_file)
    if actual_state_hash != BASELINE_SHA256:
        raise ValueError(
            f"Baseline checkpoint hash mismatch: expected {BASELINE_SHA256}, got {actual_state_hash}"
        )

    # Spawned workers must inherit the install paths before they import PyPulse.
    python_path = os.environ.get("PYTHONPATH", "")
    os.environ["PYTHONPATH"] = os.pathsep.join(
        [str(pulse_python), str(pulse_bin)] + ([python_path] if python_path else [])
    )
    lib_path = os.environ.get("LD_LIBRARY_PATH", "")
    os.environ["LD_LIBRARY_PATH"] = os.pathsep.join(
        [str(pulse_bin)] + ([lib_path] if lib_path else [])
    )

    log_dir = output.parent / "exercise_recovery_run_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    jobs = []
    for spec in candidate_specs():
        jobs.append({
            **spec,
            "pulse_bin": str(pulse_bin),
            "state_file": str(state_file),
            "log_file": str(log_dir / f"{spec['candidate_id']}.log"),
        })

    output.parent.mkdir(parents=True, exist_ok=True)
    outcomes = []
    with ProcessPoolExecutor(max_workers=args.workers, mp_context=mp.get_context("spawn")) as pool:
        futures = [pool.submit(_pulse_run, job) for job in jobs]
        for index, future in enumerate(as_completed(futures), 1):
            outcome = future.result()
            outcomes.append(outcome)
            detail = f" — {outcome['error']}" if outcome["status"] != "ok" else ""
            print(f"[{index:02d}/{len(jobs)}] {outcome['candidate_id']}: {outcome['status']}{detail}", flush=True)

    outcomes.sort(key=lambda item: item["candidate_id"])
    rows = []
    stable_identity = "StandardMale baseline; frozen parameterization; no patient/cardiovascular modifiers"
    for result in outcomes:
        if result["status"] != "ok":
            continue
        candidate_id = result["candidate_id"]
        episode_id = f"{candidate_id}_recovery_1"
        for sample in result["samples"]:
            t = sample["time_s"]
            rows.append({
                "time_s": t,
                "channel": "heart_rate",
                "value": sample["heart_rate"],
                "unit": "bpm",
                "layer": "latent",
                "source": "Pulse",
                "scenario": args.scenario,
                "episode_id": episode_id,
                "episode_relationship": "comparable_scenario",
                "clock_provenance": "Pulse 4.3.2 simulation-relative clock",
                "alignment_status": "derived_alignment",
                "take_id": args.take_id,
                "take_time_s": t,
                "phase": "recovery",
                "model_version": PULSE_VERSION,
                "parameterization": stable_identity,
                "processing_stage": PROCESSING_STAGE,
                "derived_from": "Pulse physiology HeartRate output; no real H10 samples used in candidate generation",
                "alignment_method": "protocol-relative: origin follows exercise cessation plus declared delay; not wall-time or same-episode alignment",
                "candidate_id": candidate_id,
                "exercise_intensity": result["exercise_intensity"],
                "exercise_duration_s": result["exercise_duration_s"],
                "cessation_to_recovery_origin_delay_s": result["cessation_to_recovery_origin_delay_s"],
                "conditioning_sigma_bpm": CONDITIONING_SIGMA_BPM,
            })

    candidates = pd.DataFrame(rows)
    if candidates.empty:
        raise RuntimeError("All Pulse candidate runs failed; no candidate CSV was written")
    candidates.to_csv(output, index=False)
    manifest_path = output.with_suffix(".manifest.json")
    manifest = {
        "experiment_id": "hr_constrained_pulse_exercise_recovery_v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "status": "complete" if len([x for x in outcomes if x["status"] == "ok"]) == len(jobs) else "partial",
        "scenario": args.scenario,
        "take_id": args.take_id,
        "pulse_version": PULSE_VERSION,
        "pulse_install": "local Pulse installation; path omitted",
        "baseline_state": "local frozen baseline checkpoint; path omitted",
        "baseline_state_sha256": actual_state_hash,
        "baseline_parameterization": stable_identity,
        "exercise_action": "constant Exercise intensity, then intensity 0 at cessation; abrupt stop; no taper",
        "candidate_grid": {
            "intensity_fraction_of_requested_max_work": list(INTENSITIES),
            "duration_s": list(DURATIONS_S),
            "cessation_to_recovery_origin_delay_s": list(DELAYS_S),
            "count": len(jobs),
            "prior": "equal",
            "extra_recovery_or_autonomic_parameters_varied": [],
            "conditioning_sigma_bpm": CONDITIONING_SIGMA_BPM,
        },
        "validity_rule": "Engine initialized, actions processed, all 60 recovery-relative seconds completed, finite HR throughout; no trajectory rejected on physiological appearance or held-out fit.",
        "heldout_data_used": False,
        "candidate_count_requested": len(jobs),
        "candidate_count_completed": int(sum(item["status"] == "ok" for item in outcomes)),
        "failed_candidates": [
            {"candidate_id": item["candidate_id"], "status": "failed"}
            for item in outcomes if item["status"] != "ok"
        ],
        "candidate_csv": output.name,
        "candidate_csv_sha256": sha256(output),
        "run_logs": "local run logs; paths omitted",
        "interpretation": "HR-constrained mechanistic projection candidates; not an individualized state estimate or same-episode synchronized simulation.",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return output, manifest_path, manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pulse-home", default=str(ROOT.parent / "pulse-physiology-engine"))
    parser.add_argument("--pulse-bin", default=None)
    parser.add_argument("--state-file", default=str(ROOT / "results/stage2/private/cache" / BASELINE_FILENAME))
    parser.add_argument("--scenario", default="real_session_demo")
    parser.add_argument("--take-id", default="recovery_1")
    parser.add_argument(
        "--output", default=str(APP_ROOT / "examples/pulse_exercise_recovery_candidates.csv"),
    )
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be at least 1")
    output, manifest_path, manifest = run(args)
    print(f"Candidate CSV: {output}")
    print(f"Manifest: {manifest_path}")
    print(f"Completed: {manifest['candidate_count_completed']}/{manifest['candidate_count_requested']}")
    print(f"CSV SHA-256: {manifest['candidate_csv_sha256']}")
    if manifest["status"] != "complete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
