from __future__ import annotations

import json
import importlib
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from data_contract import is_synthetic, load_observations
from pcg_observation_adapter import pcg_observation_payload
from pulse_state_adapter import observed_hr_state_at_cursor, renderer_state_at_cursor
from rppg_observation_adapter import rppg_observation_payload
from timesfm_adapter import forecast_bpm, shared_history_points
import forecast_evaluation
importlib.reload(forecast_evaluation)  # Streamlit may retain helper modules across script reruns.
from forecast_evaluation import prepare_holdout, reference_baselines, score_forecast, score_point_forecast
from mechanistic_forecast import condition_pulse_ensemble

st.set_page_config(page_title="Multimodal Digital Patient", layout="wide")
st.title("Multimodal digital patient")
st.caption("Research replay: latent model state → sensor observations → estimates → empirical forecasts")
st.info(
    "Offline research viewer. Pulse traces are model outputs; recorded sensor streams and estimator outputs "
    "remain separate layers. The cursor is scenario-relative time, not a cross-dataset patient clock. "
    "Clock provenance and alignment status determine which channels can be interpreted together."
)

SHORT_NAMES = {
    "heart_rate": "Heart rate",
    "mean_arterial_pressure": "MAP",
    "systolic_pressure": "Systolic pressure",
    "diastolic_pressure": "Diastolic pressure",
    "cardiac_output": "Cardiac output",
    "stroke_volume": "Stroke volume",
    "systemic_vascular_resistance": "SVR",
    "blood_volume": "Blood volume",
    "aortic_pressure": "Aortic pressure",
    "aortic_inflow": "Aortic inflow",
    "h10_raw_ecg_rr_bpm": "H10 RR rate",
    "h10_ecg_raw": "H10 ECG raw",
    "ad8232_ecg_raw": "AD8232 ECG raw",
    "max_red_raw": "MAX red raw",
    "max_ir_raw": "MAX IR raw",
    "max_red_blind_winner_bpm": "MAX red blind",
    "max_ir_blind_winner_bpm": "MAX IR blind",
    "camera_mean_red": "iPad red mean",
    "camera_mean_green": "iPad green mean",
    "camera_mean_blue": "iPad blue mean",
    "camera_mean_luma": "iPad luma mean",
    "camera_frame_difference_proxy": "iPad frame-difference proxy",
    "y_blind_winner_bpm": "Y blind",
    "pos_blind_winner_bpm": "POS blind",
    "chrom_blind_winner_bpm": "CHROM blind",
    "pcg_cardio_near_candidate": "H10-guided cardiac-rate-near candidate",
    "pcg_dominant_event_rate": "Reference-blind dominant spectral component",
    "pcg_secondary_event_rate": "Second-ranked reference-blind spectral component",
}
LAYER_TITLES = {
    "latent": "Latent model state",
    "subsystem": "Subsystem model outputs",
    "synthetic_observation": "Synthetic observations",
    "sensor": "Sensor observations",
    "estimate": "Estimates and diagnostic candidates",
    "forecast": "Empirical forecasts",
}
LAYER_EXPLANATIONS = {
    "latent": "Mechanistic/model state exported from Pulse. This is not an observed patient measurement.",
    "subsystem": "Outputs from bridged models such as OpenBF. These remain model outputs, not sensor observations.",
    "synthetic_observation": "Model-generated sensor-domain values from an explicit observation/forward model. These are synthetic, not recorded measurements.",
    "sensor": "Recorded sensor channels, shown with their native units and source clocks.",
    "estimate": "Derived rates and estimator outputs. Reference-guided diagnostic candidates must be labelled as such.",
    "forecast": "Model-generated continuations of observed feature histories.",
}


def short_label(row: pd.Series) -> str:
    source = str(row["source"])
    channel = str(row["channel"])
    if source == "Pulse":
        return SHORT_NAMES.get(channel, channel.replace("_", " ").title())
    if source.startswith("iPad8_CHROM"):
        return "CHROM blind" if "blind" in source.lower() else "CHROM"
    if source.startswith("iPad8_POS"):
        return "POS blind" if "blind" in source.lower() else "POS"
    if source.startswith("iPad8_Y"):
        return "Y blind" if "blind" in source.lower() else "Y"
    if source.startswith("MAX30102"):
        component = "IR" if "IR" in source.upper() or "ir" in channel else "red"
        return f"MAX {component} {('blind' if 'blind' in source.lower() else 'raw')}"
    if source.startswith("H10"):
        return "H10 RR rate" if "bpm" in str(row["unit"]) else "H10 ECG raw"
    if source.startswith("AD8232"):
        return "AD8232 ECG"
    if source == "TimesFM-3":
        return f"TimesFM: {channel}"
    return SHORT_NAMES.get(channel, channel.replace("_", " ").title())


def thin_for_plot(frame: pd.DataFrame, max_points: int = 6000) -> pd.DataFrame:
    """Evenly decimate display rows only; source data remain untouched for values/forecast."""
    pieces = []
    keys = ["channel", "source", "unit", "layer"]
    for _, part in frame.groupby(keys, sort=False, dropna=False):
        part = part.sort_values("time_s")
        if len(part) > max_points:
            idx = np.linspace(0, len(part) - 1, max_points).round().astype(int)
            part = part.iloc[np.unique(idx)]
        pieces.append(part)
    return pd.concat(pieces, ignore_index=True) if pieces else frame


uploaded = st.file_uploader("Load an exchange-format CSV", type=["csv"])
if uploaded is None:
    st.subheader("Expected CSV columns")
    st.code(
        "time_s,channel,value,unit,layer,source,scenario\n"
        "0.0,heart_rate,90.2,bpm,latent,Pulse,recovery_demo\n"
        "0.0,h10_raw_ecg_rr_bpm,89.7,bpm,estimate,H10,recovery_demo\n"
        "0.0,chrom_blind_winner_bpm,48.0,bpm,estimate,iPad8_CHROM,recovery_demo",
        language="csv",
    )
    st.write("Layers: `latent`, `subsystem`, `synthetic_observation`, `sensor`, `estimate`, `forecast`. Upload a file to inspect it.")
    st.stop()

try:
    data = load_observations(uploaded)
except Exception as exc:
    st.error(str(exc))
    st.stop()

if is_synthetic(data):
    st.error(
        "**SYNTHETIC DATA** — every value in this file is generated. Channel and source names mirror the research "
        "schema so the panels can run; nothing here is a participant recording, a Pulse run, or an optical forward model.",
        icon="🧪",
    )

if "scenario" in data.columns:
    scenarios = sorted(data["scenario"].dropna().astype(str).unique())
    if scenarios:
        chosen = st.selectbox("Scenario / take", scenarios)
        data = data[data["scenario"].astype(str) == chosen].copy()

if data.empty:
    st.warning("No rows are available for this scenario.")
    st.stop()

# Keep protocol-comparable model branches in the exchange table for forecast
# comparison, but out of the real-episode cursor, plots, and renderers.
real_data = data
if "episode_relationship" in data.columns:
    same_episode_mask = data["episode_relationship"].astype(str).eq("same_episode")
    if same_episode_mask.any():
        real_data = data[same_episode_mask].copy()
        comparable_count = int((~same_episode_mask).sum())
        if comparable_count:
            st.info(
                f"This file includes {comparable_count:,} rows from protocol-comparable model episodes. "
                "They are kept out of the real-session timeline and are available in Forecast comparison."
            )

time_axis_label = "Time from scenario start (s)"
coordinate = "Real session time"
if "protocol_time_s" in real_data.columns and "phase" in real_data.columns:
    coordinate = st.radio(
        "Timeline coordinate",
        ["Real session time", "Recovery-relative protocol time"],
        horizontal=True,
        help="Protocol time zero is the first Recovery 1 capture start, not a precisely timestamped exercise-end event.",
    )
    real_data["session_time_s"] = real_data["time_s"]
    if coordinate == "Recovery-relative protocol time":
        real_data["time_s"] = pd.to_numeric(real_data["protocol_time_s"], errors="coerce")
        time_axis_label = "Time from Recovery 1 capture start (s)"
    else:
        time_axis_label = "Time from first Rest 1 iPad capture (s)"

loaded_layers = sorted(data["layer"].astype(str).unique().tolist())
loaded_sources = sorted(data["source"].astype(str).unique().tolist())
st.caption(
    f"Loaded scenario: **{data['scenario'].iloc[0] if 'scenario' in data.columns else 'unspecified'}** · "
    f"layers: **{', '.join(LAYER_TITLES.get(layer, layer) for layer in loaded_layers)}** · "
    f"sources: **{', '.join(loaded_sources)}**"
)
if "protocol_time_s" in real_data.columns and "phase" in real_data.columns:
    st.caption(
        "Session time is rebased to the first Rest 1 iPad capture. Protocol time is rebased to the first Recovery 1 capture; "
        "this is a recovery-start proxy because the exact exercise-end timestamp was not recorded. Hover a trace to inspect its phase and take."
    )
    with st.expander("Protocol timing and capture intervals"):
        capture_rows = real_data[real_data["take_id"].astype(str).str.match(r"^(rest|recovery)_\d+$")]
        if not capture_rows.empty:
            capture_table = capture_rows.groupby("take_id", as_index=False).agg(
                phase=("phase", "first"), start_s=("time_s", "min"), stop_s=("time_s", "max")
            ).sort_values("start_s")
            st.dataframe(capture_table, hide_index=True, width="stretch")
        transition = real_data[real_data["phase"].astype(str).str.startswith("exercise_and_setup_transition")]
        if not transition.empty:
            st.caption(
                f"Exercise/setup transition is only bounded by available recordings: "
                f"{transition.time_s.min():.2f}–{transition.time_s.max():.2f} s. "
                "The exact jumping-jack start and end times were not timestamped."
            )
if set(loaded_layers) == {"latent"}:
    st.info(
        "This upload contains Pulse model output only; it does not contain the raw H10, AD8232, "
        "MAX30102, iPad, or audio recordings. To inspect the six real rest/recovery takes, upload "
        "the local six-interval exchange CSV and select a rest or recovery scenario."
    )
if "episode_relationship" in data and "unrelated" in set(data["episode_relationship"].astype(str)):
    st.warning("This scenario is explicitly marked unrelated to the recorded participant episode; compare it as a separate model scenario, not as a synchronized trace.")

real_tab, forecast_tab = st.tabs(["Real session", "Forecast comparison"])

with real_tab:
    # One time control drives all layer panels, the readout table, and the forecast origin.
    start_t = float(real_data["time_s"].min())
    stop_t = float(real_data["time_s"].max())
    if stop_t <= start_t:
        cursor_t = start_t
        st.metric("Shared time cursor", f"{cursor_t:.3f} s")
    else:
        cursor_t = st.slider(
            "Shared scenario-time cursor (s)", min_value=start_t, max_value=stop_t,
            value=stop_t, step=max((stop_t - start_t) / 1000.0, 0.01), format="%.2f",
            help="This cursor marks the same selected scenario time in every displayed layer. It does not align unrelated episodes. Readouts use the nearest recorded sample and report its time offset.",
        )

    st.subheader("Current values at cursor")
    readout_rows = []
    for (channel, source, unit, layer), part in real_data.groupby(["channel", "source", "unit", "layer"], sort=False):
        idx = (part["time_s"] - cursor_t).abs().idxmin()
        row = part.loc[idx]
        readout_rows.append({
            "Display": short_label(row), "Value": float(row["value"]), "Unit": unit,
            "Layer": LAYER_TITLES.get(layer, layer), "Sample offset (s)": float(row["time_s"] - cursor_t),
            "Exact channel": channel, "Source / processing": source,
            "Clock": row.get("clock_provenance", "unspecified"),
            "Alignment": row.get("alignment_status", "unknown"),
            "Episode relation": row.get("episode_relationship", "unknown"),
            "Model version": row.get("model_version", "unspecified"),
            "Parameterization": row.get("parameterization", "unspecified"),
            "Processing stage": row.get("processing_stage", "unspecified"),
            "Derived from": row.get("derived_from", "unspecified"),
            "Alignment method": row.get("alignment_method", "unspecified"),
        })
    readout = pd.DataFrame(readout_rows).sort_values(["Layer", "Display"])
    with st.expander("Show nearest samples from each series", expanded=False):
        st.caption("No interpolation is applied to this readout; sample offset exposes cadence and coverage.")
        st.dataframe(readout, hide_index=True, width="stretch")

    layer_order = [layer for layer in ("latent", "subsystem", "synthetic_observation", "sensor", "estimate", "forecast") if layer in set(real_data["layer"])]
    chosen_layers = st.multiselect(
        "Layers to display", options=layer_order, default=layer_order,
        format_func=lambda layer: LAYER_TITLES.get(layer, layer),
    )
    plot_data = real_data[real_data["layer"].isin(chosen_layers)].copy()
    if plot_data.empty:
        st.info("Select at least one layer to display.")
    else:
        plot_data["series"] = plot_data.apply(short_label, axis=1)
        plot_data["series_key"] = (
            plot_data["channel"].astype(str) + " | " + plot_data["source"].astype(str)
            + " | " + plot_data["layer"].astype(str)
        )
        if "take_id" in plot_data.columns:
            # Keep lines from distinct capture intervals separate across the real
            # session's unrecorded gaps, while retaining a shared channel label.
            plot_data["series_key"] += " | " + plot_data["take_id"].astype(str)
        def trace_role(row: pd.Series) -> str:
            if row["layer"] != "estimate":
                return str(row["layer"])
            descriptor = f"{row['channel']} {row['source']}".lower()
            if any(tag in descriptor for tag in ("diagnostic", "candidate", "guided", "surrogate")):
                return "Reference-informed diagnostic"
            if "blind" in descriptor:
                return "Reference-blind estimate"
            return "Derived estimate"

        plot_data["trace_role"] = plot_data.apply(trace_role, axis=1)
        plot_data = thin_for_plot(plot_data)
        tabs = st.tabs([LAYER_TITLES.get(layer, layer) for layer in chosen_layers if layer in set(plot_data["layer"])])
        for tab, layer in zip(tabs, [layer for layer in chosen_layers if layer in set(plot_data["layer"]) ]):
            with tab:
                layer_data = plot_data[plot_data["layer"] == layer]
                st.caption(LAYER_EXPLANATIONS.get(layer, ""))
                if layer == "estimate" and (layer_data["trace_role"] == "Reference-informed diagnostic").any():
                    st.warning("Dashed traces are reference-informed diagnostics, not blind estimator outputs.")
                hover_data = {
                    "channel": True, "source": True, "unit": True, "layer": True,
                    "episode_id": True, "clock_provenance": True,
                    "alignment_status": True, "episode_relationship": True,
                    "model_version": True, "parameterization": True,
                    "processing_stage": True, "derived_from": True,
                    "alignment_method": True,
                    "time_s": ":.3f", "value": ":.5g", "series_key": False,
                    "trace_role": True,
                }
                if "take_id" in layer_data:
                    hover_data["take_id"] = True
                if "phase" in layer_data:
                    hover_data["phase"] = True
                if "protocol_time_s" in layer_data:
                    hover_data["protocol_time_s"] = ":.3f"
                    hover_data["session_time_s"] = ":.3f"
                    hover_data["take_time_s"] = ":.3f"
                fig = px.line(
                    layer_data, x="time_s", y="value", color="series", line_dash="trace_role", facet_row="unit",
                    line_group="series_key",
                    hover_data=hover_data,
                    labels={"time_s": time_axis_label, "value": "Value", "series": "Series"},
                )
                fig.add_vline(x=cursor_t, line_width=1, line_dash="dash", line_color="#ef8a17")
                fig.update_layout(height=max(360, 190 * layer_data["unit"].nunique()),
                                  legend_title_text="", hovermode="closest")
                fig.update_yaxes(matches=None, autorange=True)
                st.plotly_chart(fig, width="stretch")

    st.subheader("Physiological and optical renderers")
    st.caption(
        "Choose either a mechanistic Pulse state input or an observed/estimated HR input. In observed-HR mode, HR sets only the illustrative beat cadence; the anatomical motion is schematic, and unprovided physiology remains unavailable."
    )
    latent_rows = real_data[real_data["layer"] == "latent"].copy()
    latent_sources = sorted(latent_rows["source"].astype(str).unique().tolist())
    pulse_sources = [source for source in latent_sources if source.lower() == "pulse"]
    observed_hr_rows = real_data[
        real_data["layer"].isin(["sensor", "estimate"])
        & (real_data["unit"].astype(str).str.lower().isin(["bpm", "beats/min", "beat/min"]))
    ].copy()
    has_observed_hr = not observed_hr_rows.empty

    if not pulse_sources and not has_observed_hr:
        st.info("No Pulse state or bpm sensor/estimate series is available to drive the renderer.")
    else:
        renderer_modes = []
        if pulse_sources:
            renderer_modes.append("Pulse model state")
        if has_observed_hr:
            renderer_modes.append("Observed HR cadence")
        renderer_mode = st.radio("Renderer input", renderer_modes, horizontal=True)
        renderer_state = None
        if renderer_mode == "Pulse model state":
            renderer_source = st.selectbox("Latent state source for renderer", pulse_sources)
            try:
                renderer_state = renderer_state_at_cursor(latent_rows, renderer_source, cursor_t)
            except ValueError as exc:
                st.warning(f"Renderer input unavailable: {exc}")
            else:
                waveform = renderer_state.get("waveform_template")
                waveform_caption = (
                    f"Pulse aortic waveform template: {waveform['cycle_start_time_s']:.2f}–"
                    f"{waveform['cycle_end_time_s']:.2f} s; cycle age "
                    f"{waveform['cursor_age_after_cycle_s']:.2f} s. "
                    if waveform else "No fresh complete Pulse inflow cycle is available; waveform-driven motion is unavailable. "
                )
                st.caption(
                    f"Input: Pulse · episode {renderer_state['episode_id']}. HR input: "
                    f"{renderer_state['hr_bpm']:.1f} bpm from the selected Pulse series. "
                    f"Scalar interpolation uses source brackets no wider than {renderer_state['freshness_limit_s']:.2f} s. "
                    + waveform_caption
                    + "CO/SVR visual mappings are relative display encodings, not local vessel velocity or anatomical radius."
                )
        else:
            observed_hr_rows["renderer_series_label"] = (
                observed_hr_rows["channel"].astype(str) + " | " + observed_hr_rows["source"].astype(str)
            )
            observed_series = sorted(observed_hr_rows["renderer_series_label"].unique().tolist())
            preferred = [name for name in observed_series if "H10" in name and "rr" in name.lower()]
            default_series = preferred[0] if preferred else observed_series[0]
            selected_hr_series = st.selectbox(
                "Observed/estimated HR series", observed_series,
                index=observed_series.index(default_series),
            )
            selected_rows = observed_hr_rows[
                observed_hr_rows["renderer_series_label"] == selected_hr_series
            ].copy()
            segment = None
            if "take_id" in selected_rows and selected_rows["take_id"].notna().any():
                segments = sorted(selected_rows["take_id"].dropna().astype(str).unique().tolist())
                default_segment = next(
                    (
                        name for name in segments
                        if float(selected_rows.loc[selected_rows.take_id.astype(str) == name, "time_s"].min())
                        <= cursor_t
                        <= float(selected_rows.loc[selected_rows.take_id.astype(str) == name, "time_s"].max())
                    ),
                    max(segments, key=lambda name: float(selected_rows.loc[selected_rows.take_id.astype(str) == name, "time_s"].max())),
                )
                segment = st.selectbox("HR recording segment", segments, index=segments.index(default_segment))
            try:
                renderer_state = observed_hr_state_at_cursor(
                    selected_rows, str(selected_rows["source"].iloc[0]), str(selected_rows["channel"].iloc[0]),
                    cursor_t, segment,
                )
            except ValueError as exc:
                st.warning(f"Observed HR unavailable at this cursor: {exc}")
            else:
                hr_prov = renderer_state["field_provenance"]["hr_bpm"]
                st.info(
                    f"Observed-HR mode: {renderer_state['hr_bpm']:.1f} bpm from {hr_prov['source']} / "
                    f"{hr_prov['channel']} at {cursor_t:.2f} s. This rate drives beat cadence only. "
                    "The heart/vessel drawing is schematic; pressure, flow, volume, stroke volume and resistance "
                    "are unavailable unless separately supplied. No physiology is inferred."
                )

        if renderer_state is not None:
            renderer_path = Path(__file__).parent / "assets" / "circulation-twin-renderer.html"
            renderer_html = renderer_path.read_text(encoding="utf-8")
            payload = json.dumps(renderer_state, ensure_ascii=True, separators=(",", ":"))
            payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            renderer_html = renderer_html.replace("/*__PATIENT_STATE__*/", payload)
            components.html(renderer_html, height=660, scrolling=False)

    st.subheader("rPPG optical observation renderer")
    rgb_rows = real_data[
        (real_data["layer"].astype(str) == "sensor")
        & (real_data["source"].astype(str) == "iPad8_RGB")
        & real_data["channel"].astype(str).isin(["camera_mean_red", "camera_mean_green", "camera_mean_blue"])
    ].copy()
    if rgb_rows.empty:
        st.info("No recorded iPad RGB channel means are present in this episode. Synthetic optical rendering will be added when an MCX observation export exists.")
    else:
        optical_data = real_data.copy()
        if "take_id" not in rgb_rows:
            rgb_rows["take_id"] = rgb_rows["scenario"].astype(str) if "scenario" in rgb_rows else "selected_episode"
            optical_data["take_id"] = rgb_rows["take_id"].iloc[0]
        rgb_takes = sorted(rgb_rows["take_id"].dropna().astype(str).unique().tolist())
        take_covering_cursor = next(
            (
                take for take in rgb_takes
                if float(rgb_rows.loc[rgb_rows.take_id.astype(str) == take, "time_s"].min())
                <= cursor_t
                <= float(rgb_rows.loc[rgb_rows.take_id.astype(str) == take, "time_s"].max())
            ),
            max(rgb_takes, key=lambda take: float(rgb_rows.loc[rgb_rows.take_id.astype(str) == take, "time_s"].max())),
        )
        optical_take = st.selectbox(
            "iPad RGB recording interval", rgb_takes, index=rgb_takes.index(take_covering_cursor),
        )
        try:
            optical_state = rppg_observation_payload(optical_data, optical_take, cursor_t)
        except ValueError as exc:
            st.warning(f"Optical observation unavailable: {exc}")
        else:
            if not optical_state["cursor_inside_take"]:
                st.caption(
                    f"The shared cursor is outside {optical_take}; the interval is still shown, with readouts at its last recorded sample. "
                    "Choose the take containing the cursor for cursor-linked inspection."
                )
            optical_path = Path(__file__).parent / "assets" / "rppg-observation-renderer.html"
            optical_html = optical_path.read_text(encoding="utf-8")
            optical_payload = json.dumps(optical_state, ensure_ascii=True, separators=(",", ":"))
            optical_payload = optical_payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            optical_html = optical_html.replace("/*__RPPG_STATE__*/", optical_payload)
            input_rows_html = "".join(
                "<tr>"
                f"<td>{row['time_s']:.3f}</td>"
                f"<td class=\"r\">{row['red']:.4f}</td>"
                f"<td class=\"g\">{row['green']:.4f}</td>"
                f"<td class=\"b\">{row['blue']:.4f}</td>"
                "</tr>"
                for row in optical_state.get("input_samples", [])
            )
            optical_html = optical_html.replace("<!--__INPUT_ROWS__-->", input_rows_html)
            optical_html = optical_html.replace("<!--__RGB_PLOT_SVG__-->", optical_state.get("rgb_plot_svg", ""))
            optical_html = optical_html.replace("<!--__RATE_PLOT_SVG__-->", optical_state.get("rate_plot_svg", ""))
            optical_html = optical_html.replace("<!--__RATE_LEGEND__-->", optical_state.get("rate_legend_html", ""))
            components.html(optical_html, height=1040, scrolling=False)

    st.subheader("PCG / acoustic observation renderer")
    audio_state = pcg_observation_payload(real_data, cursor_t, coordinate)
    if not audio_state["available"]:
        st.info("No exported PCG band-energy features are present in this episode. Raw WAV files are not loaded by this viewer.")
    else:
        # Keep the UI compatible with a Streamlit process that still has an older
        # cached adapter module loaded after a code reload.
        h10_guidance_current = audio_state.get("h10_guidance_current")
        acoustic_rate_features_exported = audio_state.get(
            "acoustic_rate_features_exported", bool(audio_state.get("acoustic_features"))
        )
        acoustic_rate_feature_description = audio_state.get(
            "acoustic_rate_feature_description", "Stored acoustic rate features; details may be absent from older exports."
        )
        st.markdown("**REAL ACOUSTIC DATA · APPROXIMATE CROSS-DEVICE TIMING · NOT ECG-SYNCHRONISED**")
        status_cols = st.columns(3)
        status_cols[0].markdown("**Raw WAV:** not loaded")
        status_cols[1].markdown("**Clock mapping:** approximate")
        status_cols[2].markdown("**ECG beat synchrony:** unavailable")
        features_by_channel = {item["channel"]: item for item in audio_state.get("acoustic_features", [])}
        summary_cols = st.columns(5, gap="small")
        h10_value = audio_state.get("h10_current")
        h10_display = f"{h10_value['value']:.1f} bpm" if h10_value else "Unavailable"
        with summary_cols[0]:
            st.metric("H10 · nearest", h10_display)
            if h10_value:
                st.caption(f"Sample offset {h10_value['offset_s']:+.2f} s")
        with summary_cols[1]:
            guide_value = h10_guidance_current
            st.metric("H10 · 30 s median", f"{guide_value['value']:.1f} bpm" if guide_value else "Unavailable")
            st.caption("Guide for H10-informed acoustic candidate")
        feature_cards = [
            ("pcg_cardio_near_candidate", "H10-guided cardiac-rate-near candidate", "Diagnostic · H10-informed"),
            ("pcg_dominant_event_rate", "Reference-blind dominant spectral component", "Blind spectral peak"),
            ("pcg_secondary_event_rate", "Second-ranked reference-blind spectral component", "Blind spectral peak"),
        ]
        for column, (channel_name, title, caption) in zip(summary_cols[2:], feature_cards):
            feature = features_by_channel.get(channel_name)
            if feature:
                value_text = f"{feature['current_value']:.1f} {feature['unit']}"
                if channel_name != "pcg_cardio_near_candidate" and guide_value and guide_value["value"] > 0:
                    ratio = feature["current_value"] / guide_value["value"]
                    caption += f" · {ratio:.2f}× H10 median"
                elif channel_name == "pcg_cardio_near_candidate" and guide_value:
                    offset = feature["current_value"] - guide_value["value"]
                    caption += f" · Δ {offset:+.1f}/min vs H10 median"
            else:
                value_text = "No valid window" if acoustic_rate_features_exported else "Not in export"
            with column:
                st.metric(title, value_text)
                st.caption(caption)
        acoustic_path_svg = '''<svg viewBox="0 0 480 205" role="img" aria-label="Acoustic path from chestpiece through stethoscope tubing to the BOYA BY-M1 lavalier microphone and computer">
          <defs><marker id="arr" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="#8fb5ff"/></marker></defs>
          <rect x="8" y="8" width="464" height="189" rx="12" fill="#141a2c" stroke="#293452"/>
          <text x="24" y="31" fill="#dbe5ff" font-size="14" font-weight="600">Acoustic observation path</text>
          <path d="M38 88 C50 63 93 63 105 88 L105 152 L38 152 Z" fill="#26324c" stroke="#8ea4d0" stroke-width="2"/>
          <text x="71" y="111" text-anchor="middle" fill="#e7ecfb" font-size="11">chest</text>
          <circle cx="122" cy="119" r="17" fill="#4b536c" stroke="#c5d1ee" stroke-width="2"/>
          <text x="122" y="157" text-anchor="middle" fill="#a0abc7" font-size="10">stethoscope</text><text x="122" y="170" text-anchor="middle" fill="#a0abc7" font-size="10">chestpiece</text>
          <path d="M139 119 C165 119 156 72 190 72 S225 119 246 119" fill="none" stroke="#7e91b8" stroke-width="9"/>
          <path d="M139 119 C165 119 156 72 190 72 S225 119 246 119" fill="none" stroke="#c0cce7" stroke-width="2"/>
          <text x="190" y="151" text-anchor="middle" fill="#a0abc7" font-size="10">earpiece tubing</text>
          <rect x="246" y="101" width="54" height="36" rx="8" fill="#293750" stroke="#8fb5ff" stroke-width="2"/>
          <circle cx="273" cy="119" r="7" fill="#0b0f1b" stroke="#8fb5ff" stroke-width="2"/>
          <text x="273" y="155" text-anchor="middle" fill="#e7ecfb" font-size="10">BOYA BY-M1</text><text x="273" y="168" text-anchor="middle" fill="#a0abc7" font-size="9">replaces one earpiece</text>
          <path d="M301 119 H348" fill="none" stroke="#8fb5ff" stroke-width="2" marker-end="url(#arr)"/>
          <rect x="356" y="83" width="92" height="71" rx="8" fill="#202a40" stroke="#8296c4" stroke-width="2"/>
          <rect x="366" y="92" width="72" height="48" rx="3" fill="#0b0f1b" stroke="#65769a"/>
          <text x="402" y="117" text-anchor="middle" fill="#8fb5ff" font-size="10">audio capture</text>
          <text x="402" y="171" text-anchor="middle" fill="#a0abc7" font-size="10">computer</text>
          <text x="24" y="188" fill="#a0abc7" font-size="9">Schematic of the recorded setup; it does not represent valve motion.</text>
        </svg>'''
        left_panel, middle_panel, right_panel = st.columns([1.0, 1.4, 1.4], gap="small")
        with left_panel:
            st.markdown(acoustic_path_svg, unsafe_allow_html=True)
        with middle_panel:
            st.markdown("**Band-limited acoustic envelope · 20–400 Hz**")
            audio_fig = go.Figure()
            for channel in audio_state["channels"]:
                audio_fig.add_trace(go.Scatter(
                    x=channel["time_s"], y=channel["value"], mode="lines", name=channel["label"],
                    line={"width": 1.4},
                    hovertemplate="Session time %{x:.1f} s<br>1 s normalized RMS %{y:.4f}<extra>%{fullData.name}</extra>",
                ))
            audio_fig.add_vline(x=audio_state["cursor_session_time_s"], line_dash="dash", line_color="#ef8a17")
            audio_fig.update_layout(
                height=285, margin={"l": 30, "r": 8, "t": 8, "b": 30},
                xaxis_title="Session time (s)", yaxis_title="Normalized RMS",
                legend={"orientation": "h", "y": 1.15}, hovermode="x unified",
            )
            st.plotly_chart(audio_fig, use_container_width=True, key="pcg_audio_envelope")
        with right_panel:
            st.markdown("**H10 reference and acoustic spectral-rate features**")
            if audio_state["h10_time_s"]:
                h10_fig = go.Figure(go.Scatter(
                    x=audio_state["h10_time_s"], y=audio_state["h10_rate_bpm"], mode="lines",
                    name="H10 reference", line={"color": "#f2f4ff", "width": 1.4},
                    hovertemplate="Session time %{x:.1f} s<br>H10 rate %{y:.1f} bpm<extra></extra>",
                ))
                feature_palette = ["#ffb648", "#57d9e6", "#b68cff", "#ff8fbd"]
                for index, feature in enumerate(audio_state["acoustic_features"]):
                    h10_fig.add_trace(go.Scatter(
                        x=feature["time_s"], y=feature["value"], mode="lines",
                        name={
                            "pcg_cardio_near_candidate": "H10-guided candidate",
                            "pcg_dominant_event_rate": "Blind dominant spectral component",
                            "pcg_secondary_event_rate": "Blind second-ranked spectral component",
                        }.get(feature["channel"], feature["label"]),
                        line={"color": feature_palette[index % len(feature_palette)], "width": 1.5,
                              "dash": "dash" if feature["reference_informed"] else "solid"},
                        hovertemplate=f"Session time %{{x:.1f}} s<br>{feature['label']}: %{{y:.1f}} {feature['unit']}<extra></extra>",
                    ))
                h10_fig.add_vline(x=audio_state["cursor_session_time_s"], line_dash="dash", line_color="#ef8a17")
                h10_fig.update_layout(
                    height=285, margin={"l": 30, "r": 8, "t": 58, "b": 30},
                    xaxis_title="Session time (s)", yaxis_title="Rate (per min)",
                    legend={"orientation": "h", "y": 1.18, "yanchor": "bottom", "x": 0, "xanchor": "left", "font": {"size": 10}},
                )
                st.plotly_chart(h10_fig, use_container_width=True, key="pcg_h10_reference_context")
            else:
                st.info("H10 rate is unavailable in this window.")
        with st.expander("Acoustic feature definitions and provenance"):
            st.caption("The H10-guided spectral candidate is selected against the H10 median over the same preceding 30 s window. H10 supplies rate context only; it does not identify acoustic events.")
            if acoustic_rate_features_exported:
                st.write(acoustic_rate_feature_description + ". Spectral-rate features were computed offline; only numeric features are in this CSV. The WAV and spectrum are not loaded or stored here.")
            else:
                st.write("No acoustic spectrum or rate-feature series is stored in this export; the external WAV is not loaded.")
            st.markdown(
                f"**Provenance / quality:** take `{audio_state['take_id']}` · "
                f"source `{audio_state['source']}` · source asset `{audio_state['source_asset']}` (external; not embedded) · "
                f"{audio_state['feature_description']} · "
                f"{audio_state['coverage_fraction']:.0%} coverage in displayed window · clipping {audio_state['clipping_status']} · "
                f"clock `{audio_state['clock_provenance']}` · alignment `{audio_state['alignment_status']}` · "
                "audio start estimated from file metadata; no hardware synchronization. One-second RMS does not resolve event timing. "
                "A component near cardiac rate or near twice that rate does not identify S1/S2, valve events, or pathology."
            )

    with st.expander("Data provenance and coverage"):
        coverage_summary = {
            "scenario": str(real_data["scenario"].iloc[0]) if "scenario" in real_data.columns else "unspecified",
            "rows": int(len(real_data)),
            "channels": sorted(real_data["channel"].astype(str).unique().tolist()),
            "layers": sorted(real_data["layer"].astype(str).unique().tolist()),
            "sources": sorted(real_data["source"].astype(str).unique().tolist()),
            "clock_provenance": sorted(real_data["clock_provenance"].astype(str).unique().tolist()),
            "alignment_status": sorted(real_data["alignment_status"].astype(str).unique().tolist()),
            "episode_relationship": sorted(real_data["episode_relationship"].astype(str).unique().tolist()),
            "time_s": [start_t, stop_t],
            "shared_cursor_s": float(cursor_t),
        }
        if "take_id" in real_data:
            coverage_summary["takes"] = sorted(real_data["take_id"].dropna().astype(str).unique())
        st.write(coverage_summary)

with forecast_tab:
    holdout_tab, explore_tab = st.tabs(["Forecast comparison: 30 s context → 30 s held-out future", "Exploratory TimesFM"])

    with explore_tab:
        st.subheader("TimesFM 3 observed-feature forecast")
        st.caption(
            "TimesFM forecasts selected sensor/estimator bpm series using only samples at or before the shared cursor. "
            "A forecast of CHROM or MAX blind bpm is a forecast of that estimator output, not patient heart rate. "
            "This is separate from Pulse's action-conditioned latent physiology."
        )
        bpm_obs = real_data[(real_data["unit"] == "bpm") & real_data["layer"].isin(["sensor", "estimate"]) & (real_data["time_s"] <= cursor_t)].copy()
        diagnostic_tag = bpm_obs["channel"].astype(str).str.lower().str.contains("diagnostic|candidate|guided|surrogate", regex=True)
        diagnostic_tag |= bpm_obs["source"].astype(str).str.lower().str.contains("diagnostic|candidate|guided|surrogate", regex=True)
        bpm_obs = bpm_obs[~diagnostic_tag].copy()
        if "take_id" in bpm_obs.columns and not bpm_obs.empty:
            forecast_takes = sorted(bpm_obs["take_id"].dropna().astype(str).unique())
            if forecast_takes:
                default_take = max(forecast_takes, key=lambda take: float(bpm_obs.loc[bpm_obs.take_id.astype(str) == take, "time_s"].max()))
                forecast_take = st.selectbox(
                    "Forecast within take (do not bridge acquisition/intervention gaps)",
                    forecast_takes,
                    index=forecast_takes.index(default_take),
                )
                bpm_obs = bpm_obs[bpm_obs["take_id"].astype(str) == forecast_take].copy()
                st.caption(f"Forecast history is restricted to {forecast_take}; samples from other session intervals are excluded.")
        bpm_obs["series_id"] = bpm_obs["channel"].astype(str) + " | " + bpm_obs["source"].astype(str)
        series_ids = sorted(bpm_obs["series_id"].unique().tolist())
        if not series_ids:
            if "latent" in set(real_data["layer"]):
                st.info("No sensor/estimate bpm history is available at this cursor. Pulse latent HR is kept separate from TimesFM's observed-feature forecast.")
            else:
                st.info("No sensor/estimate bpm history is available at this cursor in the selected scenario.")
        else:
            recommended = [key for key in series_ids if "H10_raw_ECG_fixed" in key or "MAX30102_IR_12s" in key or "iPad8_CHROM_12s" in key]
            default_series = recommended[:3] if recommended else series_ids[: min(3, len(series_ids))]
            selected = st.multiselect("Observed bpm series", series_ids, default=default_series)
            c1, c2 = st.columns(2)
            context = c1.slider("Context length (one-second points)", 32, 512, 32, 32)
            horizon = c2.slider("Forecast horizon (seconds)", 8, 128, 32, 8)
            available_points, available_origin = shared_history_points(bpm_obs, selected)
            if available_points < context:
                st.warning(
                    f"Only {available_points} shared one-second history points are available at this cursor; "
                    f"the selected context requires {context}. Move the cursor later or shorten the context."
                )
            if st.button(
                "Run TimesFM forecast from cursor", type="primary",
                disabled=(not selected or available_points < context),
            ):
                with st.spinner("Loading TimesFM checkpoint and forecasting on the NVIDIA GPU…"):
                    try:
                        forecast = forecast_bpm(bpm_obs, selected, horizon=horizon, context_points=context)
                    except Exception as exc:
                        st.error(f"Forecast unavailable: {exc}")
                    else:
                        actual_origin = float(forecast["forecast_origin_time_s"].iloc[0])
                        st.caption(
                            f"Forecast origin: {actual_origin:.2f} s (latest shared sampled time at or before "
                            f"the inspection cursor at {cursor_t:.2f} s). Orange dashed = forecast origin; "
                            "red dotted = inspection cursor."
                        )
                        forecast["series"] = forecast["channel"].astype(str).map(
                            lambda value: value.split(" | ", 1)[0]
                        ) + " / TimesFM-3"
                        observed = bpm_obs[bpm_obs["series_id"].isin(selected)].copy()
                        observed["series"] = observed.apply(short_label, axis=1)
                        observed["series_key"] = observed["channel"].astype(str) + " | " + observed["source"].astype(str)
                        forecast["series_key"] = forecast["channel"].astype(str) + " | TimesFM-3"
                        combined = pd.concat([observed, forecast], ignore_index=True)
                        combined["upper_error"] = (combined["high_80"] - combined["value"]).clip(lower=0)
                        combined["lower_error"] = (combined["value"] - combined["low_80"]).clip(lower=0)
                        chart = px.line(
                            combined, x="time_s", y="value", color="series", line_dash="layer",
                            line_group="series_key", error_y="upper_error", error_y_minus="lower_error",
                            hover_data=["source", "layer", "unit"],
                            labels={"time_s": time_axis_label, "value": "Rate (bpm)"},
                        )
                        chart.add_vline(
                            x=actual_origin, line_width=2, line_dash="dash", line_color="#ef8a17",
                        )
                        chart.add_vline(
                            x=cursor_t, line_width=1, line_dash="dot", line_color="#d62728",
                        )
                        chart.update_layout(height=460, hovermode="closest")
                        st.plotly_chart(chart, width="stretch")
                        st.dataframe(forecast, width="stretch")

        st.caption("Forecast output is model-generated research output, not a clinical measurement or intervention response.")


    with holdout_tab:
        st.subheader("30 s forecast origin · 30 s held-out future")
        st.caption(
            "First experiment: H10 RR-derived HR is the target. The chart keeps the complete measured take visible; "
            "TimesFM and the Pulse ensemble receive only the first 30 seconds. Future measurements are used only "
            "for retrospective scoring, never as model input."
        )
        all_bpm = real_data[
            real_data["unit"].astype(str).str.lower().eq("bpm")
            & real_data["layer"].astype(str).isin(["sensor", "estimate"])
        ].copy()
        candidate_text = (all_bpm["channel"].astype(str) + " " + all_bpm["source"].astype(str)).str.lower()
        all_bpm = all_bpm[~candidate_text.str.contains("diagnostic|candidate|guided|surrogate", regex=True)]
        if "take_id" not in all_bpm.columns:
            st.info("This export has no take_id field, so a take-bounded 30/30 evaluation cannot be formed.")
        else:
            all_bpm["series_id"] = all_bpm["channel"].astype(str) + " | " + all_bpm["source"].astype(str)
            available = sorted(x for x in all_bpm["series_id"].unique().tolist()
                               if "h10_raw_ecg_rr_bpm" in x.lower())
            if not available:
                st.info("No recorded sensor/estimate bpm series is available in this episode.")
            else:
                preferred = [x for x in available if "h10_raw_ecg_rr_bpm" in x.lower()]
                preferred += [x for x in available if "h10" in x.lower() and x not in preferred]
                default_series = preferred[0] if preferred else available[0]
                target_series = st.selectbox("Forecast target series", available, index=available.index(default_series), key="holdout_target_series")
                target_rows = all_bpm[all_bpm["series_id"] == target_series]
                takes = sorted(target_rows["take_id"].dropna().astype(str).unique().tolist())
                preferred_takes = [x for x in takes if x.startswith("recovery")]
                if not takes:
                    st.info("The selected series has no take identifier, so it cannot be evaluated independently.")
                    holdout = None
                else:
                    default_take = preferred_takes[0] if preferred_takes else takes[0]
                    take_id = st.selectbox("Take", takes, index=takes.index(default_take), key="holdout_take")
                    try:
                        holdout = prepare_holdout(all_bpm, target_series, take_id)
                    except ValueError as exc:
                        st.warning(f"This series cannot support the fixed 30 s context without extrapolation or bridging a large gap: {exc}")
                        holdout = None
                if holdout is not None:
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Forecast origin", "30.0 s")
                    c2.metric("Held-out measured samples", str(holdout["heldout_observations"]))
                    c3.metric("Observed target coverage", f"through {holdout['all_actual']['plot_time_s'].max():.1f} s")
                    st.caption(
                        f"Target: `{holdout['target_channel']}` from `{holdout['target_source']}` in `{take_id}`. "
                        "TimesFM input is a regular 1 Hz context formed only from samples at or before 30 s; "
                        "interpolation is limited to gaps no larger than 4.1 s. The held-out measurements remain hidden from the model."
                    )

                    run = st.button("Run TimesFM-3 from 30 s", type="primary", key="run_fixed_holdout")
                    cache_key = f"{target_series}::{take_id}"
                    if run:
                        with st.spinner("Loading TimesFM-3 and forecasting the held-out 30 seconds…"):
                            try:
                                result = forecast_bpm(
                                    holdout["context_frame"], [target_series], horizon=30, context_points=30
                                )
                                st.session_state["fixed_holdout_result"] = {"key": cache_key, "forecast": result}
                            except Exception as exc:
                                st.session_state.pop("fixed_holdout_result", None)
                                st.error(f"TimesFM forecast unavailable: {exc}")
                    cached = st.session_state.get("fixed_holdout_result")
                    forecast = cached["forecast"] if cached and cached.get("key") == cache_key else pd.DataFrame()

                    pulse_candidates = data[
                        data["source"].astype(str).eq("Pulse")
                        & data["channel"].astype(str).eq("heart_rate")
                        & data["layer"].astype(str).eq("latent")
                        & data["take_id"].astype(str).eq(take_id)
                        & data["processing_stage"].astype(str).eq("hr_constrained_pulse_ensemble_candidate_v1")
                    ].copy() if "take_id" in data.columns else pd.DataFrame()
                    mechanistic = None
                    if not pulse_candidates.empty:
                        try:
                            sigma_values = pd.to_numeric(pulse_candidates["conditioning_sigma_bpm"], errors="coerce").dropna().unique()
                            if len(sigma_values) != 1:
                                raise ValueError("candidate export must contain one predeclared conditioning sigma")
                            mechanistic = condition_pulse_ensemble(
                                holdout["context_frame"], pulse_candidates,
                                observation_sigma_bpm=float(sigma_values[0]),
                            )
                        except ValueError as exc:
                            st.warning(f"Pulse ensemble cannot be conditioned for this take: {exc}")

                    fig = go.Figure()
                    actual = holdout["all_actual"]
                    context_actual = actual[actual["plot_time_s"] <= 30]
                    future_actual = actual[actual["plot_time_s"] > 30]
                    fig.add_vrect(x0=0, x1=30, fillcolor="rgba(60,125,220,0.10)", line_width=0, annotation_text="OBSERVED CONTEXT", annotation_position="top left")
                    fig.add_vrect(x0=30, x1=60, fillcolor="rgba(242,138,23,0.08)", line_width=0, annotation_text="HELD-OUT FUTURE", annotation_position="top left")
                    fig.add_trace(go.Scatter(
                        x=context_actual["plot_time_s"], y=context_actual["value"], mode="lines+markers",
                        name="Measured · context", line={"color": "#455a8a", "width": 2}, marker={"size": 4},
                        hovertemplate="Take time %{x:.2f} s<br>Measured %{y:.1f} bpm<extra></extra>",
                    ))
                    fig.add_trace(go.Scatter(
                        x=future_actual["plot_time_s"], y=future_actual["value"], mode="lines+markers",
                        name="Measured · held-out truth", line={"color": "#202a40", "width": 2}, marker={"size": 4},
                        hovertemplate="Take time %{x:.2f} s<br>Held-out measurement %{y:.1f} bpm<extra></extra>",
                    ))
                    target_label = (
                        "H10 RR-derived HR" if holdout["target_channel"] == "h10_raw_ecg_rr_bpm"
                        else f"{holdout['target_source']} · {holdout['target_channel']}"
                    )
                    if not forecast.empty:
                        fx = forecast["time_s"].to_numpy(dtype=float)
                        fig.add_trace(go.Scatter(
                            x=np.r_[fx, fx[::-1]],
                            y=np.r_[forecast["high_80"].to_numpy(dtype=float), forecast["low_80"].to_numpy(dtype=float)[::-1]],
                            fill="toself", fillcolor="rgba(40,150,190,0.18)", line={"width": 0},
                            name="TimesFM central 80% interval", hoverinfo="skip",
                        ))
                        fig.add_trace(go.Scatter(
                            x=fx, y=forecast["value"], mode="lines", name="ML forecast of H10 RR-derived HR",
                            line={"color": "#1684a7", "width": 3},
                            hovertemplate="Forecast time %{x:.0f} s<br>TimesFM %{y:.1f} bpm<extra></extra>",
                        ))
                    baselines = reference_baselines(holdout["context_frame"])
                    for baseline_key, label, color, dash in [
                        ("persistence", "Persistence baseline", "#7a6fa8", "dot"),
                        ("linear_trend", "Linear trend baseline · fit to 21–30 s", "#b47b25", "dashdot"),
                    ]:
                        baseline = baselines[baseline_key]
                        fig.add_trace(go.Scatter(
                            x=baseline["time_s"], y=baseline["value"], mode="lines", name=label,
                            line={"color": color, "width": 2, "dash": dash},
                        ))
                    if mechanistic is not None:
                        summary = mechanistic["summary"]
                        future_x = summary["time_s"].to_numpy(dtype=float)
                        fig.add_trace(go.Scatter(
                            x=np.r_[future_x, future_x[::-1]],
                            y=np.r_[summary["high_80"].to_numpy(), summary["low_80"].to_numpy()[::-1]],
                            fill="toself", fillcolor="rgba(205,90,65,0.16)", line={"width": 0},
                            name="HR-constrained Pulse ensemble · central 80%", hoverinfo="skip",
                        ))
                        fig.add_trace(go.Scatter(
                            x=future_x, y=summary["median"], mode="lines",
                            name="HR-constrained mechanistic projection · Pulse HR",
                            line={"color": "#c34e3d", "width": 3, "dash": "dash"},
                            hovertemplate="Pulse forecast time %{x:.0f} s<br>Weighted median %{y:.1f} bpm<extra></extra>",
                        ))
                    fig.add_vline(x=30, line_width=2, line_dash="dash", line_color="#ef8a17", annotation_text="forecast origin · 30 s")
                    fig.update_layout(
                        height=470, margin={"l": 45, "r": 20, "t": 55, "b": 45},
                        xaxis={"title": "Seconds from take start", "range": [0, 60]},
                        yaxis_title="Heart rate (bpm)", hovermode="x unified", legend={"orientation": "h", "y": 1.12},
                    )
                    st.plotly_chart(fig, use_container_width=True, key="fixed_30_30_holdout_chart")

                    if not forecast.empty:
                        scored, metrics = score_forecast(forecast, holdout["future_actual"])
                        if metrics:
                            m1, m2, m3, m4 = st.columns(4)
                            m1.metric("ML MAE", f"{metrics['mae_bpm']:.1f} bpm", help=f"Mean absolute error for the ML forecast of {target_label}, at measured held-out timestamps only.")
                            m2.metric("ML RMSE", f"{metrics['rmse_bpm']:.1f} bpm", help="Root mean squared error at measured held-out timestamps only.")
                            m3.metric("ML 80% interval coverage", f"{metrics['coverage_80_pct']:.0f}%", help=f"{metrics['n']} measured future points compared; no truth values are interpolated.")
                            m4.metric("ML interval width", f"{(forecast['high_80'] - forecast['low_80']).mean():.1f} bpm", help="Mean width of the TimesFM central 80% interval.")
                            st.caption(
                                f"Recovery change over the scored measured span: ML {metrics['forecast_change_bpm']:+.1f} bpm, "
                                f"H10 {metrics['observed_change_bpm']:+.1f} bpm "
                                f"(change error {metrics['change_error_bpm']:+.1f} bpm)."
                            )
                            with st.expander("Forecast versus held-out measurements"):
                                st.dataframe(scored, hide_index=True, use_container_width=True)
                    baseline_scores = []
                    for baseline_key, label in [("persistence", "Persistence"), ("linear_trend", "Linear trend")]:
                        points, score = score_point_forecast(baselines[baseline_key], holdout["future_actual"])
                        if score:
                            baseline_scores.append((label, score))
                    if baseline_scores:
                        st.markdown("##### Reference baselines · same held-out H10 samples")
                        metric_cols = st.columns(len(baseline_scores))
                        for col, (label, score) in zip(metric_cols, baseline_scores):
                            col.metric(f"{label} MAE", f"{score['mae_bpm']:.1f} bpm")
                            col.caption(
                                f"RMSE {score['rmse_bpm']:.1f} bpm · recovery change "
                                f"{score['forecast_change_bpm']:+.1f} bpm predicted, "
                                f"{score['observed_change_bpm']:+.1f} bpm observed"
                            )
                    if mechanistic is not None:
                        mechanistic_forecast = mechanistic["summary"].rename(columns={"median": "value"})
                        mech_scored, mech_metrics = score_forecast(mechanistic_forecast, holdout["future_actual"])
                        best_context_rmse = mechanistic["best_conditioning_rmse_bpm"]
                        discrepancy_scale = mechanistic["observation_sigma_bpm"]
                        fit_status = "Poor" if best_context_rmse > discrepancy_scale else "Within scale"
                        st.markdown("##### Pulse context compatibility · 0–30 s only")
                        fit_cols = st.columns(3)
                        fit_cols[0].metric(
                            "Context compatibility",
                            fit_status,
                            help="Compares the best candidate's six-point conditioning RMSE with the predeclared discrepancy scale. This is a descriptive check, not a calibrated posterior test.",
                        )
                        fit_cols[1].metric("Best candidate context RMSE", f"{best_context_rmse:.1f} bpm")
                        fit_cols[2].metric("Declared discrepancy scale", f"{discrepancy_scale:.1f} bpm")
                        st.caption(
                            "Relative ensemble weights select the least-mismatched candidates; they do not establish good absolute fit. "
                            "The plot below shows the unweighted candidate family against the conditioning observations."
                        )
                        with st.expander("Unweighted Pulse candidates versus H10 conditioning context"):
                            context_fig = go.Figure()
                            context_paths = mechanistic["context_trajectories"]
                            grouped_context = list(context_paths.groupby("candidate_episode_id", sort=False))
                            if grouped_context:
                                candidate_matrix = np.stack([
                                    part.sort_values("time_s")["value"].to_numpy(dtype=float)
                                    for _, part in grouped_context
                                ])
                                context_times = grouped_context[0][1].sort_values("time_s")["time_s"].to_numpy(dtype=float)
                                context_low = np.min(candidate_matrix, axis=0)
                                context_high = np.max(candidate_matrix, axis=0)
                                context_fig.add_trace(go.Scatter(
                                    x=np.r_[context_times, context_times[::-1]],
                                    y=np.r_[context_high, context_low[::-1]],
                                    fill="toself", fillcolor="rgba(195,78,61,0.12)",
                                    line={"width": 0}, name="Unweighted candidate min–max envelope",
                                    hoverinfo="skip",
                                ))
                            for candidate_id, part in grouped_context:
                                part = part.sort_values("time_s")
                                context_fig.add_trace(go.Scatter(
                                    x=part["time_s"], y=part["value"], mode="lines",
                                    name="Pulse candidate" if candidate_id == grouped_context[0][0] else None,
                                    showlegend=(candidate_id == grouped_context[0][0]),
                                    line={"color": "rgba(195,78,61,0.24)", "width": 1},
                                    hovertemplate=f"{candidate_id}<br>%{{x:.0f}} s · %{{y:.1f}} bpm<extra></extra>",
                                ))
                            h10_context = holdout["context_frame"].sort_values("time_s")
                            context_fig.add_trace(go.Scatter(
                                x=h10_context["time_s"], y=h10_context["value"], mode="lines+markers",
                                name="H10 conditioning context", line={"color": "#263d66", "width": 3},
                                marker={"size": 5},
                                hovertemplate="H10 · %{x:.0f} s · %{y:.1f} bpm<extra></extra>",
                            ))
                            context_fig.update_layout(
                                height=390, margin={"l": 45, "r": 20, "t": 35, "b": 45},
                                xaxis_title="Seconds from recovery-take start",
                                yaxis_title="Heart rate (bpm)", hovermode="x unified",
                                legend={"orientation": "h", "y": 1.12},
                            )
                            st.plotly_chart(context_fig, use_container_width=True, key="pulse_context_support_plot")
                            st.caption(
                                f"All {mechanistic['member_count']} predeclared Pulse trajectories are shown without H10 weighting. "
                                "The red band is their full min–max support; only H10 samples at 5, 10, 15, 20, 25 and 30 s determine weights."
                            )
                        if mech_metrics:
                            m1, m2, m3, m4 = st.columns(4)
                            m1.metric("Mechanistic MAE", f"{mech_metrics['mae_bpm']:.1f} bpm", help="H10-conditioned Pulse ensemble median, evaluated only on held-out measured timestamps.")
                            m2.metric("Mechanistic RMSE", f"{mech_metrics['rmse_bpm']:.1f} bpm", help="Root mean squared error of the conditioned Pulse ensemble median.")
                            m3.metric("Mechanistic 80% interval coverage", f"{mech_metrics['coverage_80_pct']:.0f}%")
                            m4.metric("Mechanistic interval width", f"{(mechanistic['summary']['high_80'] - mechanistic['summary']['low_80']).mean():.1f} bpm")
                            st.caption(
                                f"Recovery change over the scored measured span: Pulse ensemble median "
                                f"{mech_metrics['forecast_change_bpm']:+.1f} bpm, H10 "
                                f"{mech_metrics['observed_change_bpm']:+.1f} bpm "
                                f"(change error {mech_metrics['change_error_bpm']:+.1f} bpm)."
                            )
                            st.caption(
                                f"HR-constrained projection: {mechanistic['member_count']} candidate trajectories, "
                                f"effective ensemble size {mechanistic['effective_sample_size']:.1f}; "
                                f"equal prior weights, conditioned at 5, 10, 15, 20, 25 and 30 s "
                                f"with predeclared σ={mechanistic['observation_sigma_bpm']:.1f} bpm."
                            )
                            best_candidate = mechanistic["members"].iloc[0]
                            st.caption(
                                f"Highest-weight candidate (diagnostic only): `{best_candidate['candidate_episode_id']}`; "
                                f"conditioning-block RMSE {best_candidate['conditioning_block_rmse_bpm']:.1f} bpm."
                            )
                            with st.expander("Pulse candidate context fit and weights"):
                                st.dataframe(mechanistic["members"], hide_index=True, use_container_width=True)

                    st.markdown("#### Mechanistic branch")
                    if mechanistic is None:
                        st.info(
                            "No HR-constrained Pulse ensemble is available for this take. The local Pulse/OpenBF example is a "
                            "0.84 s representative normotensive cycle, not an exercise/recovery trajectory, so it cannot supply this forecast."
                        )
                        with st.expander("Mechanistic conditioning levels"):
                            st.markdown(
                                "**Level 1 · Protocol-matched simulation:** a Pulse run with declared exercise/recovery inputs; "
                                "useful context, but not scored as a participant forecast. This run is not present in the selected data.\n\n"
                                "**Level 2 · HR-constrained mechanistic projection:** weight a predeclared ensemble of Pulse state/parameter "
                                "trajectories using H10 only at 5, 10, 15, 20, 25 and 30 s, then plot its weighted 31–60 s distribution. Candidate rows "
                                "must be tagged `processing_stage=hr_constrained_pulse_ensemble_candidate_v1`.\n\n"
                                "**Level 3 · Multimodal state inference:** estimate latent state and parameters from multiple validated "
                                "observation models. This is future work.\n\n"
                                "Before a candidate run, the exercise-to-Pulse mapping, baseline/parameter ranges, transition delay, "
                                "recovery control, and predeclared conditioning σ must be documented. See `docs/MECHANISTIC_FORECAST_PROTOCOL.md`."
                            )
                    else:
                        st.caption(
                            "The plot shows an HR-constrained mechanistic projection, not a fully individualized state estimate. "
                            "Its ensemble range reflects candidate trajectories under the stated weighting assumptions."
                        )
                    st.caption("Forecast evaluation is retrospective: held-out data are visible for scoring, but never passed into TimesFM.")
