# Stage 6: baseline-pressure bounds parameterisation

Author: David Dasa  
Date: 17 August 2026

## Outcome

The fork now permits a patient file to declare an admissible baseline-pressure
envelope while retaining Pulse's current 90--120/60--80 mmHg and 0.75 ratio
defaults. Values outside the reference envelope but inside the declared range
are accepted with a warning containing the parameter and value. Positive
pressures and systolic pressure greater than diastolic pressure remain
non-configurable hard limits.

This removes the pressure parser as the dominant population exclusion, but it
does **not** make arbitrary hypertensive patients valid Pulse patients. Direct
initialization exposes a non-monotonic stabilization boundary, and a direct
patient is physiologically different from a modifier-created patient at the
same pressure.

## Repository discipline

- Upstream: `origin/stable` at
  `e8a36497b8ba78e788dc201a6baf74e1c297c56f`.
- Fork branch: `stage6/bounds-parameterisation`.
- Fork commit: `64dfdf114` (`feat(patient): parameterize baseline pressure envelope`).
- Six source files changed; no openBF or coupling code was added to the fork.
- Age and BMI limits were deliberately left unchanged.

Five optional patient fields were added: systolic and diastolic minimum and
maximum pressures, plus the maximum diastolic-to-systolic ratio. Omission is
the backward-compatible path. The C++ patient model and protobuf round trip
carry the values; SetupPatient applies them and emits reference-envelope
warnings.

## Regression and verification

The post-change 2,155-second `HemorrhageToShock` run completed in 314.73 seconds.
Its 46,098,446-byte CSV has SHA-256
`462c43248785ce45771b056b53443252414ec066ae50bee0d3b276a42fcfab0a`,
byte-identical to the archived Stage 0 control. The targeted
`SetupPatientTest` suite passed 74/74 tests, including default rejection,
declared-envelope acceptance, invalid-range rejection, and hard pressure-order
rejection.

The distributed verification suite could not be compared in this checkout.
The pre-change attempt showed that the runner's expected verification directory
and comparison baseline CSV corpus were absent, producing missing-baseline
comparison failures before this change existed. This is recorded as skipped,
not passed. No baseline was regenerated.

## Direct hypertensive initialization

The predeclared grid covered 120/80 through 180/110 mmHg. Eight of ten points
stabilized. Among successful points, the largest absolute residual was 1.66
mmHg systolic and 0.71 mmHg diastolic; baroreflex scales returned essentially
to one.

| Requested (mmHg) | Result | Achieved (mmHg) |
|---|---:|---:|
| 120/80 | pass | 120.02/80.08 |
| 130/80 | pass | 129.01/80.19 |
| 140/80 | pass | 138.66/80.35 |
| 140/90 | pass | 139.95/89.76 |
| 150/90 | pass | 148.61/90.71 |
| 160/90 | **fail** | irreversible state during tuning |
| 160/100 | pass | 159.54/100.54 |
| 170/100 | **fail** | irreversible state during tuning |
| 180/100 | pass | 178.75/99.41 |
| 180/110 | pass | 178.34/110.25 |

The failures are holes in the tuning manifold, not an upper pressure bound.
In both, tuning alternated above and below the requested pressure pair until
the iteration limit, then intentionally raised `IrreversibleState`. Higher
nearby targets nevertheless converged.

The stabilizer also supplies physiology that the patient file did not specify.
At 150/90, final tissue resistances for bone, fat, gut, liver, and skin were
exactly twice their 120/80 values. For example, gut tissue resistance changed
from 1225.49 to 2450.98 mmHg s/mL and skin from 189.394 to 378.788 mmHg s/mL.
Thus direct hypertension is implemented partly by automatic regional
resistance tuning; the bounds change itself adds no new physiology.

## Direct versus modifier route

Three successful Stage 2 modifier cells supplied shared target pressures.
Both routes reproduced the pressure pairs closely, but their internal states
diverged.

| Target source (R, C) | Direct CO | Modifier CO | Direct SVR | Modifier SVR | Aortic shape RMSE |
|---|---:|---:|---:|---:|---:|
| 1.2, 0.8 | 5.98 | 5.26 | 0.981 | 1.123 | 0.0126 |
| 1.4, 0.6 | 6.31 | 4.80 | 0.974 | 1.312 | 0.0251 |
| 1.6, 0.5 | 6.44 | 4.41 | 0.999 | 1.495 | 0.0331 |

Cardiac output is in L/min and SVR in mmHg s/mL. At the strongest shared
point, direct-minus-modifier flow was +204 mL/min in brain and +308 mL/min in
each kidney. Every recorded regional flow separated in the same direction.
Pressure matching therefore does not make the routes equivalent, and Stages
2--5 cannot be relabelled as direct-patient results.

## Population coverage

The audit used the predeclared 60--200/40--130 mmHg research envelope and a
0.95 ratio maximum. This is a study configuration, not a proposed new Pulse
default.

| Cohort | Pressure coverage before | Pressure coverage after | Full coverage before | Full coverage after |
|---|---:|---:|---:|---:|
| HAALSI (n=4,895) | 19.16% | 98.61% | 10.07% | 40.86% |
| ELSA Wave 8 (n=3,317) | 18.99% | 99.85% | 6.18% | 21.40% |

Wide-pulse-pressure coverage rose from zero to 95.85% in HAALSI and 99.73% in
ELSA. Among pressure-representable participants, age above the unchanged
18--65 range excludes 33.0% of HAALSI and 65.2% of ELSA; BMI outside 16--30
excludes 28.9% and 30.2%. Pressure is no longer the binding constraint.

## Acceptance decision

1. Provenance, branch, and minimal diff: pass.
2. Configurable declared range with unchanged defaults, warnings, and hard
   physical limits: pass.
3. Stage 0 byte identity and targeted tests: pass; distributed comparison
   suite unavailable because its baseline corpus is missing.
4. Direct grid, convergence, residuals, and stabilization behavior: complete,
   with two documented tuning failures.
5. Direct-versus-modifier comparison: complete; routes differ materially.
6. Both cohort audits and new binding constraints: complete.
7. Upstream-ready source commit and merge-request draft: prepared; submission
   deliberately deferred.

The fork is a useful instrument for exposing the next layer of model behavior,
not a completed hypertension model. Stage 7 must decide what physiology and
baroreflex accommodation a chronic hypertensive patient should carry rather
than inheriting the stabilizer's implicit answer.

## Reproduction and evidence

Run `scripts/run_stage6_bounds.sh`. Aggregate tables are in `results/stage6/`;
generated patient files, traces, and logs remain in the ignored
`results/stage6/private/` directory. The exact configuration is
`config/stage6_envelope_v1.json`.

The upstream preparation follows Kitware's contribution guide: branch the
repository, understand the CDM and affected methodology, add unit/scenario
tests, run the test suite and assess changes, update documentation/How-To
material, then submit a merge request. The code remains Apache-2.0 compatible.
The current fork stops before submission because the full baseline corpus must
be obtained and the non-monotonic stabilization failures should be discussed
with Kitware first.

Official guide: <https://gitlab.kitware.com/physiology/engine/-/wikis/Contributing%20to%20Pulse>
