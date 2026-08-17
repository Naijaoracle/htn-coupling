# Hypertension coupling

This repository owns the parameter mapping and one-way coupling between the
Kitware Pulse physiology engine and the openBF one-dimensional blood-flow
solver. Neither upstream solver is vendored here.

## Repository boundaries

| Repository | Role | Modification policy |
|---|---|---|
| `../pulse-physiology-engine` | Whole-body physiology and operating points | Keep the upstream diff small |
| `../openBF` | One-dimensional arterial waveform solver | Use unmodified |
| `htn-coupling` | Configuration generation, mapping, bridge, analysis, results | Project-owned code |

The HAALSI study remains in
`../pulse-physiology-engine/studies/haalsi_progression`. This project may read
its exported tables but must not move or duplicate the study.

## Reproducible environment

The project uses Julia 1.11 and pins openBF by Git revision in
`Manifest.toml`. On this machine Julia 1.11.2 is installed at
`~/.local/bin/julia`.

```bash
cd {HTN_COUPLING_ROOT}
~/.local/bin/julia --project=. -e 'using Pkg; Pkg.instantiate()'
```

Run the independent openBF control:

```bash
~/.local/bin/julia --project=. scripts/run_openbf_baseline.jl
```

Large raw traces are generated under `results/` and remain ignored; compact
aggregate results and figures for reported stages are tracked. Repository
locations can be overridden in `config/repos.local.toml`; copy
`config/repos.example.toml` when setting up another machine.

## Gates

Work advances in the order recorded in [docs/ROADMAP.md](docs/ROADMAP.md).
Pulse and openBF controls must pass before phenotype or bridge work begins.
The facial-artery topology question gates the optical stages.

Completed controls and analyses:

- [Stage 0 Pulse baseline](docs/STAGE0_PULSE_BASELINE.md)
- [Stage 1 HAALSI clamp audit](docs/STAGE1_CLAMP_AUDIT.md)
- [Stage 2 Tier 0 hypertension phenotype](docs/STAGE2_TIER0_HYPERTENSION.md)
- [Stage 3 optical-site reachability](docs/STAGE3_OPTICAL_SITE_REACHABILITY.md)
- [Stage 4 Pulse-to-openBF bridge gate](docs/STAGE4_PULSE_OPENBF_BRIDGE.md)
- [Stage 5 hypertension through the coupled pipeline](docs/STAGE5_HYPERTENSION_COUPLED_PIPELINE.md)
- [Stage 6 Pulse bounds parameterisation](docs/STAGE6_BOUNDS_PARAMETERISATION.md)
