from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pandas as pd

from data_contract import load_observations


ROOT = Path(__file__).resolve().parent.parent
APP_ROOT = Path(__file__).resolve().parent


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def combine(real_path: Path, candidate_path: Path, output_path: Path, take_ids: list[str]) -> Path:
    real_bytes = Path(real_path).read_bytes()
    candidate_bytes = Path(candidate_path).read_bytes()
    real = load_observations(BytesIO(real_bytes))
    candidates = load_observations(BytesIO(candidate_bytes))

    if not real["episode_relationship"].astype(str).eq("same_episode").all():
        raise ValueError("The real-session input must contain only rows labelled same_episode")
    if not candidates["episode_relationship"].astype(str).eq("comparable_scenario").all():
        raise ValueError("Pulse candidate rows must be labelled comparable_scenario")
    if not candidates["processing_stage"].astype(str).eq("hr_constrained_pulse_ensemble_candidate_v1").all():
        raise ValueError("Candidate file contains rows outside the frozen ensemble stage")
    if set(real["scenario"].astype(str)) != set(candidates["scenario"].astype(str)):
        raise ValueError("Real and candidate files must use the same scenario identifier")
    if candidates["episode_id"].nunique() != 72:
        raise ValueError(f"Expected 72 distinct Pulse candidate episodes, found {candidates['episode_id'].nunique()}")
    if not candidates["conditioning_sigma_bpm"].astype(float).eq(10.0).all():
        raise ValueError("Candidate rows do not match the predeclared 10 bpm discrepancy scale")

    if not set(take_ids).issubset({"recovery_1", "recovery_2", "recovery_3"}):
        raise ValueError("This experiment only applies to recovery_1, recovery_2 and recovery_3")
    # The Pulse parameter grid is protocol-level and H10-independent, so reuse
    # the same 72 frozen simulations for each repeated recovery context.
    candidates = candidates.copy()
    if "candidate_id" not in candidates:
        raise ValueError("Candidate export must identify the frozen simulation candidate_id")
    candidates["episode_id"] = candidates["candidate_id"].astype(str)
    candidate_branches = []
    for take_id in take_ids:
        take_candidates = candidates.copy()
        take_candidates["take_id"] = take_id
        candidate_branches.append(take_candidates)
    candidates = pd.concat(candidate_branches, ignore_index=True)
    combined = pd.concat([real, candidates], ignore_index=True, sort=False)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(output_path, index=False)
    # Validate the exact emitted exchange file, including cross-branch key uniqueness.
    validated = load_observations(BytesIO(output_path.read_bytes()))
    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "scenario": str(real["scenario"].iloc[0]),
        "real_session_source": "local real-session exchange CSV; file path omitted",
        "real_session_sha256": sha256_bytes(real_bytes),
        "pulse_candidate_source": "local Pulse candidate CSV; file path omitted",
        "pulse_candidate_sha256": sha256_bytes(candidate_bytes),
        "output_csv": output_path.name,
        "output_csv_sha256": sha256_bytes(output_path.read_bytes()),
        "real_session_rows": int(len(real)),
        "pulse_candidate_rows": int(len(candidates)),
        "combined_rows": int(len(validated)),
        "candidate_episodes": int(candidates["episode_id"].nunique()),
        "candidate_target_takes": take_ids,
        "same_frozen_simulations_reused_across_recovery_takes": True,
        "raw_audio_included": False,
        "alignment_note": "Pulse candidates are protocol-comparable episodes. The dashboard keeps them out of the real-session timeline and uses them for HR-constrained forecast comparison only.",
    }
    output_path.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real-session", type=Path, default=APP_ROOT / "examples/real_session_timeline.csv")
    parser.add_argument(
        "--candidates", type=Path,
        default=APP_ROOT / "examples/pulse_exercise_recovery_candidates.csv",
    )
    parser.add_argument(
        "--output", type=Path, required=True,
        help="write outside this repository when the session CSV contains real recordings",
    )
    parser.add_argument("--take-ids", nargs="+", default=["recovery_1", "recovery_2", "recovery_3"])
    args = parser.parse_args()
    combine(args.real_session, args.candidates, args.output, args.take_ids)


if __name__ == "__main__":
    main()
