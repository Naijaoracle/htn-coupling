# Data de-identification record

This note records post-hoc disclosure-control changes made to published aggregates. It is a statement of what the tracked files contain, not a statement about HAALSI or ELSA data-use terms; those remain the responsibility of the authorised user.

## 1. Cohort-derived simulation panel

The simulation panel was derived from cohort anthropometry. Because distinctive profiles can increase identification risk, the tracked files now publish only coarsened values:

| Field | Published as |
|---|---|
| Age | nearest 5 years |
| Height | nearest 5 cm |
| Weight | nearest 5 kg |
| BMI | rounded to an integer |
| Infusion rate, administered mass, nominal volume | omitted (they equal the exact weight up to a constant) |

Affected files: `config/stage5_acute_panel_v1.json`, `config/pressure_matched_drug_response_multibody_v1.json`, `results/pressure_matched_drug_response_multibody/{manifest.json,matched_states.csv,aggregate.csv}`, `results/stage5/acute_body_results.csv`, and the multi-body protocol and results documents. Unit tests use synthetic bodies.

**Consequences.** All simulated results were produced with the exact values, so the published coarsened panel does not reproduce them bit-for-bit. Hash locks recorded in manifests (panel, configuration, protocol, tests) refer to the original exact-value files, and the runner's panel-hash check will not pass against the coarsened panel. The exact files are kept in the gitignored `config/private/`.

## 2. Small-cell suppression

In cohort summary tables and their JSON mirrors (`results/stage1`, `results/stage2`, `results/stage6`):

- Counts of 1–9 are replaced by `<10`, with the matching percentage and any medians over that group replaced by `NA`.
- Where a within-row identity (for example `too_low = low_without_high + mixed`, or `n = reachable + unreachable`) would reveal a suppressed cell, a second cell is `withheld`.
- A sparse ELSA age stratum is pooled with the adjacent band, and the corresponding figure was regenerated.
- Sparse HAALSI and ELSA blood-pressure strata are pooled or suppressed.

## 3. Residual limitations

- **History.** Earlier commits on the public remote still contain the exact panel values and the unsuppressed tables. Removing them requires rewriting history and force-pushing, which has not been done.
- **Cross-output disclosure.** Tables and percentages must be reviewed together: totals or rounded percentages can imply suppressed cell values by subtraction. Sparse counts are not enumerated in this note.
- **Manuscript.** The paper removes sparse-cell counts and coarsens values that would imply them; its cohort-density figure uses a minimum of 10 participants per displayed bin.
- **Threshold.** The threshold of 10 is a conservative convention, not a figure taken from the HAALSI or ELSA terms.
