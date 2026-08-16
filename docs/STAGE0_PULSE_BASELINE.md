# Stage 0: Pulse regression baseline

Status: **pass**.

Pulse 4.3.2 at revision `e8a36497b8ba78e788dc201a6baf74e1c297c56f`
completed its distributed `HemorrhageToShock` verification scenario. The
unmodified StandardMale patient stabilized for 30 seconds, bled at a fixed
200 mL/min for 625 seconds, and completed the prescribed recovery interval.
The engine reached exactly the expected final simulation time of 2,155 seconds.

The fresh 107,751-row output is byte-for-byte identical to the archived local
reference trace: both have SHA-256
`462c43248785ce45771b056b53443252414ec066ae50bee0d3b276a42fcfab0a`.
Hypovolemic shock began at 615.16 seconds and cleared at 1,322.44 seconds.
Runtime was 330.346 seconds on CPU.

Key active-bleed checkpoints were:

| Blood loss | MAP (mmHg) | Heart rate (/min) | Cardiac output (L/min) |
|---:|---:|---:|---:|
| 0% | 95.3 | 72.02 | 5.79 |
| 10% | 94.2 | 86.11 | 5.13 |
| 20% | 93.0 | 105.13 | 4.55 |
| 30% | 69.6 | 120.52 | 3.46 |
| 35% | 43.1 | 127.90 | 2.03 |

The full CSV and log remain local and ignored because the CSV is 46 MB. The
tracked machine-readable summary is
`results/stage0/pulse_hemorrhage_to_shock/baseline_summary.json`.
