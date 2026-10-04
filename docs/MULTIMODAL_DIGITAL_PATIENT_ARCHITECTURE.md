# Multimodal digital-patient architecture

## Purpose

The digital-patient artefact keeps parameterisation, physiological state, sensor formation, recorded measurements, estimates, forecasts, and rendering as separate objects. Every plotted value should retain its origin and its episode/time relationship.

## Scientific layers

```text
PARAMETERISATION
htn-coupling / population evidence / individual parameters
                         |
                         v
LATENT PHYSIOLOGY
Pulse state-transition engine
interventions: exercise, haemorrhage, medication, fluid, etc.
                         |
             +-----------+------------+
             |                        |
             v                        v
     STATE OUTPUTS             SUBSYSTEM / FORWARD MODELS
HR, pressure, CO, SV,          OpenBF vascular waveforms
SVR, volume, flows             when bridged to Pulse state
                                      |
                                      v
                              OBSERVATION MODELS
                              MCX optical transport
                              synthetic ECG / PPG / audio
                              camera/readout models
                                      |
                                      v
                              SYNTHETIC OBSERVATIONS

REAL EPISODE                          INTERPRETATION
H10 / AD8232 / MAX / RGB / audio  ->  estimates and diagnostics
                                      |
                                      v
                              TimesFM forecasts of a named series

STATE + SUBSYSTEM OUTPUTS + OBSERVATIONS  ->  dashboard and animation renderers
```

### Roles

- **htn-coupling and population evidence:** constrain or select patient parameters and phenotypes. This is the parameterisation/calibration layer, not another physiology engine.
- **Pulse:** the mechanistic cardiovascular/whole-body state-transition engine. Haemorrhage is one possible perturbation; exercise, drugs, fluids, and other interventions are conceptually separate inputs.
- **OpenBF:** a vascular-flow model that can be coupled or bridged to Pulse outputs for higher-resolution vascular dynamics. The interface and conservation assumptions must be explicit for each coupling.
- **MCX:** an optical forward model. Given tissue optical properties and vascular state, it models photon transport and optical observations. It does not generate cardiovascular physiology.
- **Subsystem outputs:** retain a distinct `subsystem` layer (for example, OpenBF pressure and flow). They are model outputs downstream of physiology, not sensor measurements.
- **Synthetic observations:** use `synthetic_observation` only for sensor-domain values actually emitted by an explicit forward/observation model. Do not use it for latent variables, subsystem outputs, or illustrative placeholders.
- **Synthetic ECG, PPG, PCG/audio, and camera streams:** each requires a modality-specific observation model downstream of latent state. None should be treated as a direct Pulse variable.
- **Recorded data:** actual sensor streams, with raw observations distinguished from derived estimates. H10-derived RR rate is an estimate from ECG; CHROM and MAX blind peaks are estimator outputs, not raw sensor channels.
- **TimesFM-3:** forecasts the selected input time series. Its target identity follows the series: a CHROM forecast is a forecast of CHROM output; a Pulse-HR forecast would be a forecast of simulated HR. It does not infer the latent state by default.
- **Dashboard and animation:** downstream renderers. Three.js/Blender consume named model or observation state; visual appearance never feeds back into the scientific state unless an explicit model says so.

## Episode and time contract

`time_s` is relative to one declared episode origin. It is not a universal patient clock. Exchange rows should retain:

| Field | Meaning |
|---|---|
| `episode_id` | Identifier for one recording or simulation run. |
| `clock_provenance` | Clock and timestamp source, such as iPad wall time, Polar timestamps, ESP32 device time plus host mapping, or Pulse simulation time. |
| `alignment_status` | `master_clock`, `shared_clock`, `wall_time_aligned`, `derived_alignment`, `unaligned`, or `unknown`. |
| `episode_relationship` | `same_episode`, `comparable_scenario`, `unrelated`, or `unknown`, relative to the episode being compared. |

Never overlay different `episode_id` values as though their equal `time_s` values identify the same physiological moment. A comparison between independent simulations and recordings may be scientifically useful, but it must remain labelled as a scenario comparison unless a protocol, state, initial condition, and time mapping justify same-episode interpretation.

## Individual state inference is not implemented

The current artefact replays observations, model outputs, estimates, and forecasts. It does not estimate an individual's latent physiological state or parameters from measurements. Any future implementation would require a separately validated inference method.

The dashboard must not imply that a generic Pulse run is the recorded participant's hidden state.

## Renderer state interface, first version

The dashboard-to-Three.js boundary is a read-only snapshot at the selected scenario cursor. Each scalar field is linearly interpolated to that same cursor only when a source-sample bracket is no wider than 0.1 s; extrapolation is disabled. Per-field provenance records the contributing source timestamps, interpolation method, cursor delta, and supplied/derived/unavailable status. Derived values use only fields sampled at the common cursor. A field outside the time range, with an unsupported unit, or with a wider bracket is unavailable.

```json
{
  "episode_id": "pulse_normotensive_cycle",
  "time_s": 12.345,
  "source": "Pulse",
  "hr_bpm": 72.02,
  "map_mmHg": 95.33,
  "systolic_mmHg": 114.27,
  "diastolic_mmHg": 73.59,
  "cardiac_output_L_min": 5.788,
  "stroke_volume_mL": 80.367,
  "svr_absolute_mmHg_s_mL": 0.9394,
  "svr_relative": 0.9997,
  "aortic_inflow_mL_s": 366.698,
  "aortic_pressure_mmHg": 103.059,
  "provided_fields": [
    "hr_bpm", "map_mmHg", "systolic_mmHg", "diastolic_mmHg",
    "cardiac_output_L_min", "svr_absolute_mmHg_s_mL",
    "aortic_inflow_mL_s", "aortic_pressure_mmHg"
  ],
  "derived_fields": ["stroke_volume_mL", "svr_relative"],
  "field_provenance": {
    "hr_bpm": {
      "value": 72.02,
      "provenance": "supplied",
      "sample_time_s": 12.345,
      "cursor_delta_s": 0.0,
      "source_sample_times_s": [12.34, 12.36],
      "method": "linear_interpolation",
      "bracket_width_s": 0.02
    },
    "stroke_volume_mL": {
      "value": 80.367,
      "provenance": "arithmetic_derived",
      "inputs": ["cardiac_output_L_min", "hr_bpm"],
      "sample_time_s": 12.345,
      "cursor_delta_s": 0.0
    }
  },
  "waveform_template": {
    "cycle_start_time_s": 11.40,
    "cycle_end_time_s": 12.24,
    "cycle_period_s": 0.84,
    "cursor_age_after_cycle_s": 0.105,
    "phase_cycles_at_cursor": 0.134,
    "phase_sample_count": 128,
    "source_sample_range_s": [11.40, 12.24],
    "aortic_inflow_peak_mL_s": 434.13,
    "flow_onset_rule": "10% of available-history P95 above P5 baseline"
  }
}
```

The excerpt omits the 128-value `phase`, `aortic_inflow_mL_s`, and `aortic_pressure_mmHg` arrays in `waveform_template`. The live snapshot contains these arrays and `field_provenance` entries for every supported scalar. It uses the most recent complete aortic-inflow up-crossing-to-up-crossing cycle at or before the cursor. The onset threshold is fixed at 10% of the 95th-percentile inflow available up to the cursor above its 5th-percentile baseline; no future samples are used to locate the cycle. A cycle is accepted only when its period is 0.5–1.5 times the cursor HR period, its age is at most 1.5 cursor-HR periods, inflow, pressure and HR coverage have no source gaps wider than 0.1 s, and the same interval has valid aortic-pressure coverage. Inflow and pressure are linearly resampled to 128 phase points. The source interval and age are included in waveform provenance. If no qualifying complete cycle exists, waveform-driven motion is unavailable rather than synthesized.

The renderer has two separate inputs and does not run a second physiology model in either mode. In **Pulse model state** mode, it consumes Pulse latent state. **Inspect mode** repeats the most recent complete source beat at the dashboard cursor. Its phase is anchored to the detected flow-cycle onset relative to the cursor and advances at that measured period. **Playback mode** starts at the cursor and advances a renderer playhead through the episode. At each frame, every field is sampled at that common playhead time; Pulse HR, aortic inflow and pressure must pass the 0.1 s bracket rule. HR gaps stop playback; optional fields with gaps become unavailable. Playback stops at the episode end. The upper dashboard charts remain at the playback-origin cursor: orange dashed is the fixed inspection/start cursor, and a blue solid overlay follows the renderer playhead during playback. The renderer labels its advancing time separately. When the full aortic-inflow trajectory has at least two onset crossings and every onset interval is consistent with the midpoint HR period (0.5–1.5×), mechanical phase is mapped directly between successive detected inflow up-crossings. If that waveform screen is unavailable, phase advances by integrated HR. This is Pulse mechanical-cycle timing, not ECG timing.

In **Observed HR cadence** mode, one explicitly selected sensor/estimate bpm series is passed as the only supplied field. It sets the visual beat cadence; phase remains illustrative and is not ECG-synchronized. Pressure, flow, volume, stroke volume, and resistance remain unavailable. Vessel geometry is static and schematic, and flow particles are disabled. Playback interpolates only across observed-HR brackets no wider than 2.5 s; extrapolation is disabled and larger gaps stop playback. The renderer labels the selected source/channel and episode.

In inspect mode, the sampled aortic-inflow shape drives left-ventricular ejection amplitude and a relative flow-motion encoding; in playback mode, the current Pulse inflow sample drives those mappings directly, normalized by the episode's positive-flow 95th percentile for display only. Neither is a local vessel velocity. Aortic pressure drives a small systemic-arterial distension encoding using a fixed 95 mmHg visual reference and 0.00025 per mmHg display gain, clipped to ±1.5%. This is schematic and is not a pressure-compliance law or a pulse-propagation model; pulmonary pressure is not supplied by this example and pulmonary arteries are not pressure-driven. Relative SVR is normalized by the declared 0.939706 mmHg·s/mL Pulse reference and used only for schematic resistance/calibre encoding, not anatomical radius. Stroke volume may be arithmetically derived as `CO × 1000 / HR` only when the common-time source omits it, and that derivation is labelled. Missing fields remain unavailable in readouts; renderer baselines used for display-only motion are not presented as patient values. Playback payloads are capped at 100,000 source samples across supported channels; larger episodes remain inspectable but playback is disabled rather than silently decimated.

## Current implementation status

- Exchange CSV supports `latent`, `subsystem`, `synthetic_observation`, `sensor`, `estimate`, and `forecast` layers, plus source, scenario, and optional episode/clock/alignment metadata. Missing metadata defaults to `unknown` rather than guessed synchronization. Optional provenance fields include model version, parameterisation, processing stage, derivation, and alignment method.
- The first Pulse/OpenBF bridge exports the normotensive Pulse representative cardiac cycle and the saved OpenBF distal external-carotid pressure/flow waveforms. The OpenBF cycle is shifted onto the Pulse cycle endpoint using the shared period and is labelled `derived_alignment`; it is a phase-aligned cycle bridge, not a continuous coupled simulation. The exchange file contains `latent` and `subsystem` rows only. No MCX-derived or synthetic sensor-domain observations are yet included.
- The six-take physical export marks each iPad capture as an episode, the iPad interval as master time, and H10/ESP32 observations as wall-time aligned to it. PCG is excluded because its interval mapping is not sufficiently secure.
- Pulse export labels simulation-relative time and keeps the simulation unaligned and unrelated to the physical participant episodes.
- The embedded Three.js twin is a local adapted copy of the existing circulation view. Pulse mode consumes a read-only, common-time model-state snapshot and trajectory; observed-HR mode consumes only an explicitly selected sensor/estimate rate and animates cadence schematically. Neither mode infers latent state, and raw participant recordings are not passed through Pulse. Playback overlays a moving blue playhead on the fixed orange-cursor plots. The source twin in the separate `daviddasa` project is unchanged.
- Dashboard cursor is scenario-relative. It marks values within the selected scenario; it does not align independent scenarios.
- TimesFM reads only observed/estimated bpm streams, and its forecast origin is the latest shared sampled point at or before the inspection cursor.
