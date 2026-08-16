# Stage 1: HAALSI Wave 1 versus the Pulse patient envelope

## Headline

**3,953 of 4,895 HAALSI Wave 1 adults with valid published derived blood
pressure (80.76%) are outside Pulse's 90--120 mmHg systolic by 60--80 mmHg
diastolic baseline box.** Only 942 (19.24%) are inside it.

Pulse does not clamp these inputs. A real-engine test accepted the in-range
114/73.5 mmHg control and returned failure, with an explicit error, for each
one-unit-outside test (121/73.5, 89/73.5, 114/81, and 114/59 mmHg). None of the
logs mentioned clamping. The operational finding is therefore exclusion, not
silent substitution.

## Pressure decomposition

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

## Comparator gate

No HRS or ELSA microdata are present locally, and the available local NHANES
extract contains age, sex, height, weight, and haemoglobin but no blood
pressure. The non-African comparator therefore has **not** been run. It is an
explicit external-data gate, not an unlabelled substitution. The audit script
accepts a comparator once registered HRS or ELSA data are supplied.

## Reproduction

From the coupling repository:

```bash
python3 scripts/run_stage1_clamp.py
```

To rerun the engine-boundary behavior test, expose the installed Pulse Python
package and library, then run `scripts/test_pulse_patient_bounds.py` with
`--pulse-install` and `--output`. Aggregate CSV, JSON, and PNG outputs under
`results/stage1/` are tracked; no participant identifiers are written.
