# Stage 1: HAALSI and ELSA versus the Pulse patient envelope

## Headline

The exclusion is not specific to HAALSI or to an African population:

| Cohort | Valid measured BP n | Outside pressure box n | Outside % |
|---|---:|---:|---:|
| HAALSI Wave 1 | 4,895 | 3,953 | 80.76 |
| ELSA Wave 8 health visit | 3,317 | 2,687 | 81.01 |

**Roughly four in five measured adults are outside Pulse's 90--120 mmHg
systolic by 60--80 mmHg diastolic baseline box in both a rural South African
cohort and an English ageing cohort.** The finding is therefore a limitation
of the engine's narrow normal-patient envelope across these two older-adult
populations, not evidence of a uniquely African mismatch.

Pulse does not clamp these inputs. A real-engine test accepted the in-range
114/73.5 mmHg control and returned failure, with an explicit error, for each
one-unit-outside test (121/73.5, 89/73.5, 114/81, and 114/59 mmHg). None of the
logs mentioned clamping. The operational finding is therefore exclusion, not
silent substitution.

## HAALSI pressure decomposition

| Classification | n | % of 4,895 |
|---|---:|---:|
| Outside pressure box | 3,953 | 80.76 |
| At least one component too high | 3,856 | 78.77 |
| At least one component too low | 123 | 2.51 |
| High, with no low component | 3,830 | 78.24 |
| Low, with no high component | 97 | 1.98 |
| Mixed high systolic and low diastolic | 26 | 0.53 |
| Exactly one component outside | 1,394 | 28.48 |
| Systolic only outside | 1,220 | 24.92 |
| Diastolic only outside | 174 | 3.55 |
| Both components outside | 2,559 | 52.28 |

The high and low rows overlap for 26 physiologically discordant records
(systolic above 120 with diastolic below 60), so the two headline directions
must not be added. Pulse also rejects an abnormally narrow pulse pressure when
diastolic exceeds 75% of systolic. That rule excludes four additional people
who are inside the rectangular pressure box, bringing the full pressure-rule
failure count to 3,957 (80.84%).

## Sex and age

The pressure-box exclusion is effectively identical by sex: 1,824/2,260 men
(80.71%) and 2,129/2,635 women (80.80%). It rises monotonically with age:

| Age (years) | n | Excluded n | Excluded % |
|---|---:|---:|---:|
| 40--49 | 887 | 627 | 70.69 |
| 50--59 | 1,362 | 1,097 | 80.54 |
| 60--69 | 1,273 | 1,057 | 83.03 |
| 70--79 | 851 | 715 | 84.02 |
| 80+ | 522 | 457 | 87.55 |

## Height, weight, BMI, and age

Pulse has no standalone weight bound. When height and weight are supplied,
weight is constrained through BMI: values below 16 or above 30 kg/m2 are hard
errors. Height outside the sex-specific 3rd--97th percentile range is only a
warning; the hard height range is 4.5--7.0 ft (137.16--213.36 cm).

| Rule | Assessed n | Outside n | Outside % | Engine response |
|---|---:|---:|---:|---|
| Sex-specific typical height | 4,694 | 804 | 17.13 | Warning |
| Hard height range | 4,694 | 6 | 0.13 | Reject |
| BMI below 16 | 4,689 | 54 | 1.15 | Reject |
| BMI above 30 | 4,689 | 1,384 | 29.52 | Reject |
| BMI outside 16--30 | 4,689 | 1,438 | 30.67 | Reject |

On the 4,635 participants with complete pressure, age, sex, height, and weight,
the full pressure rules reject 80.65%, BMI rejects 30.57%, age outside Pulse's
18--65-year range rejects 34.95%, and hard height rejects 0.13%. At least one
of these rules rejects 4,142/4,635 (89.36%). Pressure alone rejects 1,526
(32.92%) who pass every other assessed hard constraint, so pressure is the
binding constraint rather than merely the most visible one.

## Denominator and sensitivity

The primary denominator uses the HAALSI release's published Wave 1 derived
means, which are nonmissing for 4,895 participants. HAALSI defines them from
the second and third readings where available. Requiring all four raw values
(systolic and diastolic readings 2 and 3) produces a slightly smaller strict
sample of 4,875; this is recorded for sensitivity analysis and does not replace
the prespecified valid-derived-pressure denominator.

## ELSA Wave 8 comparator

ELSA Wave 8 (2016--17) was selected because it is the health-visit wave closest
in calendar time to HAALSI Wave 1. The source contains 3,525 nurse visits.
ELSA's own validity flag identifies 3,317 records with valid mean systolic and
diastolic pressure; no missing BP was imputed. Age and measured height/weight
were joined from Gateway Harmonized ELSA by `idauniq`. One nurse-versus-
harmonized sex-code disagreement was resolved in favour of the contemporaneous
Wave 8 nurse field and is recorded in the machine-readable extraction metadata.

ELSA's crude pressure-box exclusion is 2,687/3,317 (81.01%), only 0.25
percentage points above HAALSI. Its composition differs, however:

| Classification | ELSA n | ELSA % | HAALSI % |
|---|---:|---:|---:|
| Outside pressure box | 2,687 | 81.01 | 80.76 |
| At least one component too high | 2,476 | 74.65 | 78.77 |
| At least one component too low | 385 | 11.61 | 2.51 |
| Exactly one component outside | 1,811 | 54.60 | 28.48 |
| Both components outside | 876 | 26.41 | 52.28 |

ELSA men are excluded more often than women: 1,244/1,481 (84.00%) versus
1,443/1,836 (78.59%). Age-specific exclusion is 68.68% at 50--59, 79.13% at
60--69, 83.37% at 70--79, and 89.49% at 80+. Only two valid ELSA observations
are aged 40--49, so that cell is not interpretable.

Measured anthropometry gives the same secondary result: 1,069/3,448 (31.00%)
are outside Pulse's BMI range, while none of 3,502 measured heights violates
the hard 4.5--7.0 ft limit. Among 3,254 records complete on all assessed
variables, 3,049 (93.70%) fail at least one hard rule; ELSA's older age
distribution makes Pulse's age ceiling particularly consequential.

These are unweighted health-visit samples, not prevalence estimates for all
adults in South Africa or England. ELSA is substantially older than HAALSI:
66.53% of its complete cases exceed Pulse's age ceiling versus 34.95% in
HAALSI. The near-identical crude pressure exclusion therefore supports a
cross-cohort engine-envelope finding, but it should not be described as an
age-standardized equality or generalized to young adults.

## Reproduction

From the coupling repository:

```bash
python3 scripts/run_stage1_clamp.py
```

To rerun the engine-boundary behavior test, expose the installed Pulse Python
package and library, then run `scripts/test_pulse_patient_bounds.py` with
`--pulse-install` and `--output`. Aggregate CSV, JSON, and PNG outputs under
`results/stage1/` are tracked; no participant identifiers are written.
