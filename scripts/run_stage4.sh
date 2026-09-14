#!/usr/bin/env bash
set -euo pipefail

stage4_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
pulse_root="${PULSE_ROOT:-$stage4_root/../pulse-physiology-engine}"
openbf_root="${OPENBF_ROOT:-$stage4_root/../openBF}"
python_bin="$pulse_root/build/venv/bin/python"

export PULSE_ROOT="$pulse_root"
export OPENBF_ROOT="$openbf_root"
export PYTHONPATH="$pulse_root/build/install/python:$pulse_root/build/install/lib${PYTHONPATH:+:$PYTHONPATH}"
export LD_LIBRARY_PATH="$pulse_root/build/install/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export LD_PRELOAD="/usr/lib/x86_64-linux-gnu/libstdc++.so.6${LD_PRELOAD:+:$LD_PRELOAD}"

run_manifest() {
  local mode="$1"
  "$python_bin" "$stage4_root/scripts/prepare_stage4_openbf.py" "$mode"
  "$python_bin" - "$stage4_root" "$mode" <<'PY'
import json, subprocess, sys
from pathlib import Path
root, mode = Path(sys.argv[1]), sys.argv[2]
manifest = json.loads((root / "results/stage4" / f"{mode}_config_manifest.json").read_text())
for case in manifest["cases"]:
    result = root / "results/stage4/runs" / case["case"]
    subprocess.run(["julia", f"--project={root}",
                    str(root / "scripts/run_stage4_openbf.jl"),
                    case["yaml"], str(result)], check=True)
PY
}

"$python_bin" "$stage4_root/scripts/extract_stage4_pulse_inlet.py"
run_manifest base
"$python_bin" "$stage4_root/scripts/analyse_stage4.py" gate
run_manifest sensitivity
"$python_bin" "$stage4_root/scripts/analyse_stage4.py" final
