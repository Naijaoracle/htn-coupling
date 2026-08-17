# Draft merge request: parameterize the patient baseline-pressure envelope

## Summary

Preserve Pulse's current baseline-pressure defaults while allowing a patient
definition to explicitly declare a wider admissible range. Values outside the
reference envelope are logged as unsupported; positive pressure and systolic
greater than diastolic remain hard requirements.

## Motivation

With current defaults, only 19.16% of 4,895 HAALSI adults and 18.99% of 3,317
ELSA Wave 8 adults have directly admissible measured pressure. A predeclared
60--200/40--130 mmHg envelope raises those pressure-only rates to 98.61% and
99.85%, while retaining provenance warnings. The population envelope is an
analysis setting and is not proposed as a new default.

## Change

- Add optional systolic/diastolic baseline minima and maxima and an optional
  maximum DBP/SBP ratio to `PatientData`.
- Round-trip them through `SEPatient` and `PBPatient`.
- Use them in SetupPatient, falling back exactly to existing constants.
- Warn outside the reference range and reject invalid declared ranges or hard
  physical violations.
- Add focused SetupPatient coverage.

## Verification

- `SetupPatientTest`: 74/74 pass.
- Default 2,155-second `HemorrhageToShock`: byte-identical CSV, SHA-256
  `462c43248785ce45771b056b53443252414ec066ae50bee0d3b276a42fcfab0a`.
- Direct grid: 8/10 targets stabilize through 180/110; 160/90 and 170/100
  oscillate during circuit tuning and end in irreversible state. This behavior
  is disclosed rather than hidden.
- Full distributed comparison suite: pending access to the expected baseline
  CSV corpus, which is absent from this checkout.

## Scope

This change parameterizes validation bounds only. It does not introduce a
hypertension condition, change cardiovascular equations, alter age/BMI limits,
or claim that out-of-reference patients are validated.
