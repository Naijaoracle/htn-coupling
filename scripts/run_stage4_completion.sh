#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
pulse_root="${PULSE_ROOT:-$root/../pulse-physiology-engine}"
python_bin="$pulse_root/build/venv/bin/python"
export OPENBF_ROOT="${OPENBF_ROOT:-$root/../openBF}"

"$python_bin" "$root/scripts/finish_stage4.py" prepare
"$python_bin" - "$root" <<'PY'
import json, subprocess, sys
from pathlib import Path
root = Path(sys.argv[1])
manifest = json.loads((root / "results/stage4_completion/run_manifest.json").read_text())
for case in manifest["cases"]:
    result = root / "results/stage4_completion/runs" / case["case"]
    subprocess.run(["julia", f"--project={root}",
                    str(root / "scripts/run_stage4_openbf.jl"),
                    case["yaml"], str(result)], check=True)
PY
"$python_bin" "$root/scripts/finish_stage4.py" analyse
