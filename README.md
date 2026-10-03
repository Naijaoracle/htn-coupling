# Hypertension coupling

`htn-coupling` is a research repository for mechanistic cardiovascular modelling, multimodal physiological observation and forecasting. It began with characterisation and extension of the Pulse Physiology Engine for hypertension and a one-way Pulse to openBF arterial-flow coupling, and that remains the first major research strand: this repository owns the parameter mapping and coupling between the Kitware Pulse physiology engine and the openBF one-dimensional blood-flow solver. Neither upstream solver is vendored here.

The work is organised as predeclared, gated experiments. Real participant and cohort data are not redistributed. Public interactive traces use fully synthetic data; aggregate findings from real-data experiments may be reported separately.

## Repository boundaries

| Repository | Role | Modification policy |
|---|---|---|
| `../pulse-physiology-engine` | Whole-body physiology and operating points | Keep the upstream diff small |
| `../openBF` | One-dimensional arterial waveform solver | Use unmodified |
| `htn-coupling` | Configuration generation, mapping, bridge, analysis, results | Project-owned code |

Cohort inputs are third-party controlled data. This repository uses only authorised local copies during analysis and never redistributes source records or participant-level derivatives.

## Multimodal digital-patient work

The repository also contains a newer multimodal digital-patient research layer:

- [docs/MULTIMODAL_DIGITAL_PATIENT_ARCHITECTURE.md](docs/MULTIMODAL_DIGITAL_PATIENT_ARCHITECTURE.md) separates population parameterisation, latent physiology, vascular subsystem outputs, observation models, estimates and forecasts.
- `multimodal_demo_next/` is research tooling for multimodal replay and evaluation, covering electrical, optical and acoustic observations alongside Pulse/openBF state and time-series forecasts.
- `tools/` contains acquisition importers and ESP32 firmware for the sensor hardware.
- `public_demo/` generates the synthetic data used by the public website demonstrator. See [public_demo/README.md](public_demo/README.md) for what is synthetic, what is genuine model output, and the controls that keep private recordings out.

The public artefact and the research tooling are deliberately separate: the former demonstrates the architecture with generated data.

## Reproducible environment

The project uses Julia 1.11 and pins openBF by Git revision in `Manifest.toml`. Clone the repository, then instantiate it with a Julia 1.11 installation:

```bash
git clone https://github.com/Naijaoracle/htn-coupling.git
cd htn-coupling
julia --project=. -e 'using Pkg; Pkg.instantiate()'
```

Run the independent openBF control:

```bash
julia --project=. scripts/run_openbf_baseline.jl
```

Large model and experiment-generated traces under `results/` remain ignored; compact aggregate results and figures for reported stages are tracked. Repository locations can be overridden in `config/repos.local.toml`; copy `config/repos.example.toml` when setting up another machine.

## Data boundary

This public repository contains no participant recordings, participant identifiers, or participant- or cohort-derived per-run trajectories. Explicitly labelled synthetic demonstration trajectories and non-participant mechanistic model outputs may be tracked. There are two separate boundaries.

**Cohort data (HAALSI, ELSA).** Tracked cohort tables and figures are aggregate summaries with disclosure control: counts below 10 are suppressed (`<10`), cells that would reveal them by subtraction within a table are `withheld`, and sparse strata are pooled. The cohort-derived simulation panel is published only with demographics coarsened to the nearest 5 years, 5 cm and 5 kg, and with exact-weight-derived dose rates omitted. [docs/DATA_DE_IDENTIFICATION.md](docs/DATA_DE_IDENTIFICATION.md) records exactly what was changed and what remains. Authorised users must obtain HAALSI Wave 1 (ICPSR 36633) and ELSA Wave 8 (UK Data Service study 5050) independently and comply with their access conditions.

**Multimodal recordings.** Private research recordings are not tracked in this repository. The public demonstration is generated from synthetic observations and non-participant model outputs only.

Historic result manifests use `{PULSE_ROOT}`, `{OPENBF_ROOT}`, and `{HTN_COUPLING_ROOT}` as redacted local-path placeholders.

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
- [Numbered engine findings](docs/ENGINE_FINDINGS.md)

## Acknowledgements and data citation

HAALSI (Health and Aging in Africa: A Longitudinal Study of an INDEPTH Community in South Africa) is sponsored by the National Institute on Aging (grant number 1P01AG041710-01A1) and is conducted by the Harvard Center for Population and Development Studies in partnership with Witwatersrand University. The Agincourt HDSS was supported by the Wellcome Trust, UK, (058893/Z/99/A, 069683/Z/02/Z, 085477/Z/08/Z and 085477/B/08/Z), the University of the Witwatersrand and South African Medical Research Council.

HAALSI data citation: Harvard Center for Population and Development Studies, 2016, "HAALSI Baseline Survey", doi:10.7910/DVN/F5YHML, Harvard Dataverse, V1.


ELSA data used in this study were obtained from the UK Data Service (Study 5050, 50th Edition, DOI: 10.5255/UKDA-SN-5050-37) and are cited below. The collection metadata lists the Department for Work and Pensions, Economic and Social Research Council, Department for Communities and Local Government, Office for National Statistics, HM Revenue and Customs, National Institute of Aging, Department of Health, and Department for Transport as sponsors. Copyright is held jointly between NatCen Social Research, University College London and Institute for Fiscal Studies. The UK Data Service is funded by UKRI through the Economic and Social Research Council.

Research reported in this publication was supported by the National Institute On Aging of the National Institutes of Health under Award Number R01AG017644. The content is solely the responsibility of the authors and does not necessarily represent the official views of the National Institutes of Health.

ELSA is funded by the NIHR Policy Research Programme (HEI) 198_1074_03. The views expressed are those of the author(s) and not necessarily those of the NIHR or the Department of Health and Social Care.

ELSA data citation: Banks, J., Cribb, J., Coughlin, K., Di Gessa, G., Kapadia, D., Lloyd, L., Marmot, M., Nazroo, J., Oldfield, Z., Steel, N., Steptoe, A., Wood, M., Zaninotto, P. (2026). English Longitudinal Study of Ageing: Waves 0--11, 1998--2024. [data collection]. 50th Edition. UK Data Service. SN: 5050, DOI: https://doi.org/10.5255/UKDA-SN-5050-37.

## Licensing

Project-owned software, configuration, and documentation are licensed under [Apache-2.0](LICENSE). Original manuscript text and original figures in `paper/` are licensed under [CC-BY-4.0](paper/LICENSE). [NOTICE](NOTICE) identifies material and rights excluded from these grants, including Pulse, openBF, HAALSI, ELSA, and all restricted cohort data.
