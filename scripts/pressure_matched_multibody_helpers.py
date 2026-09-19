"""Pure calculations for the pressure-matched multi-body experiment."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping, Sequence


def norepinephrine_rate_mL_s(dose_ug_kg_min: float, mass_kg: float,
                             concentration_ug_mL: float) -> float:
    if dose_ug_kg_min <= 0 or mass_kg <= 0 or concentration_ug_mL <= 0:
        raise ValueError("dose, mass, and concentration must be positive")
    return dose_ug_kg_min * mass_kg / (60.0 * concentration_ug_mL)


def body_bmi_kg_m2(body: Mapping) -> float:
    return float(body["weight_kg"]) / (float(body["height_cm"]) / 100.0) ** 2


def attempt_output_directory(root: Path, label: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,47}", label) or label in {".", ".."}:
        raise ValueError(f"invalid attempt label: {label!r}")
    return Path(root) / label


def pressure_residual(record: Mapping, target: Mapping) -> tuple[float, float]:
    return (float(record["systolic_mmHg"]) - float(target["systolic_mmHg"]),
            float(record["diastolic_mmHg"]) - float(target["diastolic_mmHg"]))


def pressure_match_passes(record: Mapping, reference: Mapping, tolerance: float = 0.25) -> bool:
    if not record.get("stationarity_pass", False):
        return False
    return all(abs(float(record[m]) - float(reference[m])) <= tolerance
               for m in ("systolic_mmHg", "diastolic_mmHg"))


def bounded_newton_proposal(point: Sequence[float], residual: Sequence[float],
                            jacobian: Sequence[Sequence[float]],
                            bounds: Sequence[Sequence[float]],
                            max_coordinate_step: float = 0.25) -> tuple[float, float]:
    """Return a clipped Newton proposal; singular Jacobians fail closed."""
    import numpy as np

    matrix = np.asarray(jacobian, dtype=float)
    vector = np.asarray(residual, dtype=float)
    if matrix.shape != (2, 2) or vector.shape != (2,) or not np.isfinite(matrix).all():
        raise ValueError("expected a finite 2x2 Jacobian and 2-vector residual")
    if abs(float(np.linalg.det(matrix))) < 1e-10:
        raise ValueError("pressure residual Jacobian is singular")
    step = np.linalg.solve(matrix, -vector)
    step = np.clip(step, -max_coordinate_step, max_coordinate_step)
    proposed = np.asarray(point, dtype=float) + step
    proposed = np.clip(proposed, [b[0] for b in bounds], [b[1] for b in bounds])
    return float(proposed[0]), float(proposed[1])
