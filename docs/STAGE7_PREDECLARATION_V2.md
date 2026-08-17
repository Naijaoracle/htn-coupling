# Stage 7 version-2 predeclaration

Author: David Dasa  
Date: 17 August 2026

This is the frozen parameter and provenance record for Stage 7. It supersedes
the earlier Stage 7 protocol text. Numeric values, units, population source,
and implementation status are in
[`config/stage7_parameter_provenance_v2.json`](../config/stage7_parameter_provenance_v2.json).

The Stage 7.1 gate is complete first. It found compensated/mixed regional-flow
behavior in direct creation, so P1 renal and hepatosplanchnic flow targets are
deferred. No P1 target is applied until the compensation mechanism is explained.

Implementation order is P4 named haemodynamic stage, P3 cardiovagal gain, P2
stateful resetting, P5 chamber/contractility separation, then a revisited P1.
Every change is a separate commit and must pass the Stage 0 byte-identity gate.
Omitted fields preserve current Pulse behavior. The defaults are not claims
that any preset is clinically validated, and no value is treated as African-
population-specific.

Numeric values marked `modelling_synthesis`, animal-derived, or
architecture-dependent are not to be silently promoted to universal defaults.
