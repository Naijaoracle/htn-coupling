#!/usr/bin/env python3
"""Empirically test whether Pulse rejects or mutates out-of-range BP inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pulse.cdm.engine import SEDataRequestManager
from pulse.cdm.patient import SEPatientConfiguration, eSex
from pulse.cdm.scalars import LengthUnit, MassUnit, PressureUnit, TimeUnit
from pulse.engine.PulseEngine import PulseEngine


CASES = {
    "inside_control": (114.0, 73.5),
    "systolic_high": (121.0, 73.5),
    "systolic_low": (89.0, 73.5),
    "diastolic_high": (114.0, 81.0),
    "diastolic_low": (114.0, 59.0),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pulse-install", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    for name, (sbp, dbp) in CASES.items():
        configuration = SEPatientConfiguration()
        configuration.set_data_root_dir(str(args.pulse_install))
        patient = configuration.get_patient()
        patient.set_name(name)
        patient.set_sex(eSex.Male)
        patient.get_age().set_value(44.0, TimeUnit.yr)
        patient.get_height().set_value(177.0, LengthUnit.cm)
        patient.get_weight().set_value(77.1, MassUnit.kg)
        patient.get_systolic_arterial_pressure_baseline().set_value(sbp, PressureUnit.mmHg)
        patient.get_diastolic_arterial_pressure_baseline().set_value(dbp, PressureUnit.mmHg)
        engine = PulseEngine(data_root_dir=str(args.pulse_install))
        engine.log_to_console(False)
        log_path = args.output / f"{name}.log"
        engine.set_log_filename(str(log_path))
        initialized = bool(engine.initialize_engine(configuration, SEDataRequestManager([])))
        text = log_path.read_text(errors="replace") if log_path.exists() else ""
        results.append({
            "case": name,
            "configured_systolic_mmHg": sbp,
            "configured_diastolic_mmHg": dbp,
            "initialize_engine_returned": initialized,
            "logged_error": "[ERROR]" in text,
            "mentions_too_high": "is too high" in text,
            "mentions_too_low": "is too low" in text,
            "mentions_clamp": "clamp" in text.lower(),
        })
    (args.output / "patient_bound_behavior.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
