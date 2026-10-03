from __future__ import annotations

from io import BytesIO

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = {"time_s", "channel", "value", "unit", "layer", "source"}
ALLOWED_LAYERS = {
    "latent", "subsystem", "synthetic_observation", "sensor", "estimate", "forecast",
}
ALLOWED_ALIGNMENT = {"master_clock", "shared_clock", "wall_time_aligned", "derived_alignment", "unaligned", "unknown"}
ALLOWED_EPISODE_RELATION = {"same_episode", "comparable_scenario", "unrelated", "unknown"}


SYNTHETIC_PREFIX = "SYNTH:"
SYNTHETIC_STAGE_MAP = {"synthetic_ensemble_candidate_v1": "hr_constrained_pulse_ensemble_candidate_v1"}


def is_synthetic(frame: pd.DataFrame) -> bool:
    return "data_class" in frame.columns and bool(len(frame)) and frame["data_class"].astype(str).str.strip().eq("synthetic").all()


def adapt_synthetic_for_panels(frame: pd.DataFrame) -> pd.DataFrame:
    """In memory only: let panels written for the research schema run on a fully synthetic file.

    On disk a synthetic file labels sensor-domain rows `synthetic_observation` and prefixes
    sources with `SYNTH:`. The panels match the research names exactly, so this restores
    those names for display. The `data_class` column is kept, and the app shows a persistent
    SYNTHETIC DATA banner whenever it is present.
    """
    frame = frame.copy()
    frame["source"] = frame["source"].astype("string").str.replace(f"^{SYNTHETIC_PREFIX}", "", regex=True)
    frame["layer"] = frame["layer"].replace({"synthetic_observation": "sensor"})
    if "processing_stage" in frame:
        frame["processing_stage"] = frame["processing_stage"].replace(SYNTHETIC_STAGE_MAP)
    return frame


def load_observations(file: BytesIO | bytes) -> pd.DataFrame:
    """Load and validate the public, long-form exchange CSV."""
    frame = pd.read_csv(BytesIO(file) if isinstance(file, bytes) else file, low_memory=False)
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"Missing required CSV columns: {', '.join(sorted(missing))}")

    frame = frame.copy()
    frame["time_s"] = pd.to_numeric(frame["time_s"], errors="coerce")
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    for column in ("channel", "unit", "layer", "source"):
        frame[column] = frame[column].astype("string").str.strip()

    if is_synthetic(frame):
        frame = adapt_synthetic_for_panels(frame)

    # Optional provenance fields keep older exchange CSVs readable while
    # preventing the dashboard from implying a clock relationship by default.
    if "episode_id" not in frame:
        frame["episode_id"] = frame["scenario"].astype("string") if "scenario" in frame else "unspecified"
    if "clock_provenance" not in frame:
        frame["clock_provenance"] = "unspecified"
    if "alignment_status" not in frame:
        frame["alignment_status"] = "unknown"
    if "episode_relationship" not in frame:
        frame["episode_relationship"] = "unknown"
    optional_provenance = {
        "model_version": "unspecified",
        "parameterization": "unspecified",
        "processing_stage": "unspecified",
        "derived_from": "unspecified",
        "alignment_method": "unspecified",
    }
    for column, default in optional_provenance.items():
        if column not in frame:
            frame[column] = default
    for column in ("episode_id", "clock_provenance", "alignment_status", "episode_relationship"):
        frame[column] = frame[column].astype("string").str.strip()
    for column in optional_provenance:
        frame[column] = frame[column].fillna(optional_provenance[column]).astype("string").str.strip()
    if frame[["episode_id", "clock_provenance", "alignment_status", "episode_relationship"]].isna().any().any():
        raise ValueError("episode and clock provenance fields cannot be empty")
    if (frame[["episode_id", "clock_provenance"]].apply(lambda col: col.str.len() == 0)).any().any():
        raise ValueError("episode_id and clock_provenance cannot be blank")

    if frame[["time_s", "value"]].isna().any().any() or not np.isfinite(frame[["time_s", "value"]].to_numpy(dtype=float)).all():
        raise ValueError("time_s and value must contain finite numeric values")
    if not set(frame["layer"].dropna().unique()).issubset(ALLOWED_LAYERS):
        invalid = sorted(set(frame["layer"].dropna().unique()) - ALLOWED_LAYERS)
        raise ValueError(f"Unknown layer values: {invalid}")
    if frame[["channel", "unit", "layer", "source"]].isna().any().any():
        raise ValueError("channel, unit, layer, and source cannot be empty")
    invalid_alignment = set(frame["alignment_status"].dropna().unique()) - ALLOWED_ALIGNMENT
    if invalid_alignment:
        raise ValueError(f"Unknown alignment_status values: {sorted(invalid_alignment)}")
    invalid_relation = set(frame["episode_relationship"].dropna().unique()) - ALLOWED_EPISODE_RELATION
    if invalid_relation:
        raise ValueError(f"Unknown episode_relationship values: {sorted(invalid_relation)}")

    # Equal timestamps are allowed across channels, episodes, takes, and
    # ensemble candidates. Candidate identity is part of the series key when
    # present, since multiple Pulse trajectories intentionally share a source,
    # channel, and time grid.
    keys = ["channel", "source", "unit", "layer", "time_s"]
    for scope in ("episode_id", "candidate_id", "take_id"):
        if scope in frame.columns:
            keys.append(scope)
    if "scenario" in frame.columns:
        keys.append("scenario")
    if frame.duplicated(keys).any():
        raise ValueError("Duplicate time_s rows found for a channel/source series")
    return frame.sort_values(["time_s", "layer", "channel"]).reset_index(drop=True)
