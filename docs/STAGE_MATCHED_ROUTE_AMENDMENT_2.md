# Pressure-matched route predeclaration amendment 2

## Reason for amendment

Review of the interrupted refinement found that some nominal 12-second pressure summaries covered rapid cardiovascular transitions. Targeted cases varied by more than 50 mmHg within the measurement window, and two apparent higher-target matches failed independent reruns. The previous endpoint median alone did not establish that a pressure match represented a steady state.

## Stationarity gate

For every 12-second pressure measurement trace, divide the samples into four consecutive, equal-duration bins. Compute the median systolic and diastolic pressure in each bin. A trace passes stationarity only when the range across the four systolic medians is at most 0.25 mmHg and the range across the four diastolic medians is at most 0.25 mmHg. A pressure match must pass both this stationarity gate and the previously declared absolute SBP and DBP residual limits. Independent reruns must pass both gates as well.

The 0.25 mmHg stationarity limits use the already declared maximum pressure-match residual. The gate rejects transitional windows while retaining the stable saved candidate traces reviewed to date. It does not alter targets, route definitions, parameter bounds, objective, or the previously declared physiological outcome measures.

## Durable results

The search runner now writes the accumulated evaluation table and a per-step checkpoint after each completed refinement step. Run the reconstruction script before resuming an interrupted search; completed parameter points are reused rather than simulated again. Independent confirmation outcomes are also written to a dedicated table, including failed runs. Per-case logs and traces remain preserved under the private case directory.

This amendment applies prospectively to the focused validation evaluations. Previously completed results retain their recorded endpoints; their stored traces can be re-evaluated against this gate.
