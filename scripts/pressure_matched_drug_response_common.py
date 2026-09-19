"""Pure helpers shared by the confirmatory runner and its unit tests."""
from __future__ import annotations

from itertools import product
from pathlib import Path
import re
from typing import Iterable, Mapping

BASELINE_START_S = 30
BASELINE_STOP_S = 60  # half-open: include 30, exclude 60
TARGETS = ("mild", "intermediate", "higher")
ROUTES = ("direct", "modifier")
REPLICATES = (1, 2)


def baseline_window_rows(rows: Iterable[Mapping]):
    """Return samples in the frozen [30,60) second baseline window."""
    return [
        row for row in rows
        if BASELINE_START_S <= float(row["elapsed_s"]) < BASELINE_STOP_S
    ]


def execution_matrix():
    """One entry per final challenge; repeats are numerical, not biological."""
    return list(product(TARGETS, ROUTES, REPLICATES))


def case_directory(root: Path, target: str, route: str, replicate: int, phase: str) -> Path:
    if target not in TARGETS:
        raise ValueError(f"unknown target: {target}")
    if route not in ROUTES:
        raise ValueError(f"unknown route: {route}")
    if replicate not in REPLICATES:
        raise ValueError(f"unknown replicate: {replicate}")
    if phase not in {"baseline", "challenge"}:
        raise ValueError(f"unknown phase: {phase}")
    return Path(root) / target / f"replicate_{replicate:02d}" / route / phase


def pair_gate_passes(direct: Mapping, modifier: Mapping, pressure_tolerance: float = 0.25) -> bool:
    """Check SBP/DBP matching and stationarity for both routes."""
    if not direct.get("stationarity_pass") or not modifier.get("stationarity_pass"):
        return False
    for metric in ("systolic_mmHg", "diastolic_mmHg"):
        if abs(float(direct[metric]) - float(modifier[metric])) > pressure_tolerance:
            return False
    return True


def challenge_gate_passes(challenged: Mapping, peer_screen: Mapping, pressure_tolerance: float = 0.25) -> bool:
    """Check one fresh challenged process against its screened pair state."""
    if not challenged.get("stationarity_pass"):
        return False
    return all(
        abs(float(challenged[metric]) - float(peer_screen[metric])) <= pressure_tolerance
        for metric in ("systolic_mmHg", "diastolic_mmHg")
    )


def attempt_output_directory(base: Path, label: str) -> Path:
    """Return a unique run-attempt directory and reject path traversal labels."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,47}", label) or label in {".", ".."}:
        raise ValueError(f"invalid attempt label: {label!r}")
    return Path(base) / label
