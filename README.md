# Hypertension coupling

`htn-coupling` is a research-software repository for cardiovascular simulation,
arterial-flow coupling, and multimodal physiological data tooling. The main
simulation workflow connects the Pulse Physiology Engine to the openBF 1D
arterial solver. The repository contains project-owned configuration,
coupling, analysis, and reporting code; the upstream simulator source trees are
not included.

The repository also contains a synthetic comparison report covering runs made
with Pulse, CircAdapt, and svZeroDSolver. That report describes constructed
inputs and simulator behaviour only. CircAdapt and svZeroDSolver are not
required dependencies, and this repository does not include maintained
adapters or their upstream source code.

## What is in the repository

| Path | Contents |
|---|---|
| `src/`, `scripts/`, `config/` | Project code, experiment configuration, and tools for the Pulse/openBF workflow. |
| `results/`, `docs/` | Reported simulation outputs, aggregate findings, methods, and technical reports. |
| `paper/` | The research manuscript, supporting material, licenses, and the synthetic simulator comparison report. |
| `multimodal_demo_next/` | Research tooling for replay and evaluation of physiological observations, model outputs, estimates, and forecasts. It does not run Pulse or openBF from the dashboard. |
| `public_demo/` | Generators and checks for the public synthetic demonstrator. |
| `tools/` | Acquisition importers and ESP32 firmware. |
| `test/`, `.github/workflows/` | Automated tests and continuous-integration configuration. |

The public demonstrator and research tooling have separate data paths. The
demonstrator uses generated observations and clearly labelled model outputs.
It does not turn a simulated trajectory into a participant measurement.

## Synthetic multi-simulator report

[Synthetic parameter-recovery and uncertainty benchmarks across three
cardiovascular simulators](paper/reports/three_engine_synthetic_benchmark.pdf)
summarizes the synthetic cohort rehearsal, model-specific parameter searches,
known-truth recovery, and uncertainty stress experiments. Its recovery
percentages are conditional on the tested builds, parameterizations, search
grids, observation mappings, and noise assumptions; they are not clinical
performance estimates. The report is an aggregate summary; its run scripts,
synthetic input files, and candidate-level outputs are not included here.

## Reproducible environment

The core Julia project targets Julia 1.11 and pins openBF in `Manifest.toml`.
From a clean checkout with Julia 1.11 installed:

```bash
git clone https://github.com/Naijaoracle/htn-coupling.git
cd htn-coupling
julia --project=. -e 'using Pkg; Pkg.instantiate()'
```

Run the independent openBF control:

```bash
julia --project=. scripts/run_openbf_baseline.jl
```

The multimodal viewer has its own Python environment and setup instructions in
[multimodal_demo_next/README.md](multimodal_demo_next/README.md). The public
synthetic data generators and bundle workflow are documented in
[public_demo/README.md](public_demo/README.md). CircAdapt and svZeroDSolver
experiments were run in separate local environments; those environments and
their source checkouts are not bundled here.

Large generated traces and private working files are excluded from version
control. Repository locations can be overridden in `config/repos.local.toml`;
copy `config/repos.example.toml` for a local setup. The local `notes/` folder is
also excluded from version control.

## Data boundary

Source cohort records, participant identifiers, real-session recordings, and
participant-level trajectories are not included. Tracked cohort-derived tables
and figures are aggregate or coarsened outputs, with the disclosure controls
described in [docs/DATA_DE_IDENTIFICATION.md](docs/DATA_DE_IDENTIFICATION.md).
Authorised users must obtain the source datasets independently and follow their
access conditions.

Public interactive traces use synthetic observations. The synthetic benchmark
report linked above likewise contains no participant measurements. Historic
result manifests use `{PULSE_ROOT}`, `{OPENBF_ROOT}`, and
`{HTN_COUPLING_ROOT}` as redacted local-path placeholders.

## Acknowledgements and data citation

HAALSI (Health and Aging in Africa: A Longitudinal Study of an INDEPTH
Community in South Africa) is sponsored by the National Institute on Aging
(grant number 1P01AG041710-01A1) and is conducted by the Harvard Center for
Population and Development Studies in partnership with Witwatersrand
University. The Agincourt HDSS was supported by the Wellcome Trust, UK,
(058893/Z/99/A, 069683/Z/02/Z, 085477/Z/08/Z and 085477/B/08/Z), the University
of the Witwatersrand and South African Medical Research Council.

HAALSI data citation: Harvard Center for Population and Development Studies,
2016, “HAALSI Baseline Survey”, doi:10.7910/DVN/F5YHML, Harvard Dataverse, V1.

ELSA data used in this study were obtained from the UK Data Service (Study
5050, 50th Edition, DOI: 10.5255/UKDA-SN-5050-37). Collection sponsors and
funding bodies are listed in the collection metadata. Copyright is held jointly
between NatCen Social Research, University College London and Institute for
Fiscal Studies. The UK Data Service is funded by UKRI through the Economic and
Social Research Council.

Research reported in this publication was supported by the National Institute
On Aging of the National Institutes of Health under Award Number R01AG017644.
The content is solely the responsibility of the authors and does not
necessarily represent the official views of the National Institutes of Health.

ELSA is funded by the NIHR Policy Research Programme (HEI) 198_1074_03. The
views expressed are those of the author(s) and not necessarily those of the
NIHR or the Department of Health and Social Care.

ELSA data citation: Banks, J., Cribb, J., Coughlin, K., Di Gessa, G., Kapadia,
D., Lloyd, L., Marmot, M., Nazroo, J., Oldfield, Z., Steel, N., Steptoe, A.,
Wood, M., Zaninotto, P. (2026). English Longitudinal Study of Ageing: Waves
0--11, 1998--2024. [data collection]. 50th Edition. UK Data Service. SN: 5050,
DOI: https://doi.org/10.5255/UKDA-SN-5050-37.

## Licensing

Project-owned software, configuration, documentation, and the synthetic
benchmark report are licensed under [Apache-2.0](LICENSE). The original
manuscript and its figures are licensed under [CC-BY-4.0](paper/LICENSE).
[NOTICE](NOTICE) identifies material and rights excluded from these grants,
including upstream simulators and controlled source data.
