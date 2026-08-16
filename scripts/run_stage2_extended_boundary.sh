#!/usr/bin/env bash
set -euo pipefail

stage2_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
pulse_root="${PULSE_ROOT:-{PULSE_ROOT}}"
system_cxx_runtime="/usr/lib/x86_64-linux-gnu/libstdc++.so.6"

export PULSE_ROOT="$pulse_root"
export PYTHONPATH="$pulse_root/build/install/python:$pulse_root/build/install/lib${PYTHONPATH:+:$PYTHONPATH}"
export LD_LIBRARY_PATH="$pulse_root/build/install/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
if [[ -f "$system_cxx_runtime" ]]; then
  export LD_PRELOAD="$system_cxx_runtime${LD_PRELOAD:+:$LD_PRELOAD}"
fi

exec "$pulse_root/build/venv/bin/python" \
  "$stage2_root/scripts/run_stage2_extended_boundary.py" "$@"
