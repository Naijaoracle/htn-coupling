# Stage 7.1: supra-proportional scaling diagnostic

Author: David Dasa  
Date: 17 August 2026

## Gate result

The required direct-patient comparison was completed before adding Stage 7
defaults. It compares stabilized endpoint medians at 120/80 and 150/90 mmHg
using the same body definition and the same compartment requests.

Mean arterial pressure rose from 101.36 to 120.98 mmHg, a ratio of 1.194. The
Stage 6 logs show bone, fat, gut, liver, and skin tissue resistances doubling
at 150/90. The regional flows do not respond as a simple inverse-resistance
calculation would predict:

| Compartment | 120/80 inflow | 150/90 inflow | Ratio |
|---|---:|---:|---:|
| Brain | 673.3 mL/min | 713.3 mL/min | 1.060 |
| Left/right kidney | 500.1 mL/min | 647.4 mL/min | 1.295 |
| Gut | 790.5 mL/min | 837.9 mL/min | 1.060 |
| Liver | 1340.0 mL/min | 1417.2 mL/min | 1.058 |
| Muscle | 863.7 mL/min | 914.1 mL/min | 1.058 |
| Skin | 280.6 mL/min | 297.0 mL/min | 1.058 |
| Myocardium | 232.2 mL/min | 246.1 mL/min | 1.060 |

The outcome is compensated/mixed, not hypoperfusion. In particular, renal flow
rises by 29.5%, while the other measured beds rise by approximately 5.8--6.0%.
The doubled tissue resistances therefore do not represent the dominant net
regional-flow constraint in this direct route, or another circuit component is
compensating for them.

## P1 decision

The proposed literature-derived renal and hepatosplanchnic flow targets are
not implemented at this point. Applying them would overwrite an observed
engine compensation before its mechanism is understood. P1 remains deferred;
the current default/proportional behavior is retained and this diagnostic is
the required Stage 7 finding.

The data are endpoint medians rather than full-cycle distributions. Bone and
fat resistances are present in the tuning logs but were not represented by
separate requested vascular inflows in the Stage 6 output. The machine-readable
artifacts are [the CSV](../results/stage7/diagnostic_7_1_regional_flows.csv) and
[the JSON](../results/stage7/diagnostic_7_1.json).
