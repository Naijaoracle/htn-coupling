from __future__ import annotations

import html
import numpy as np
import pandas as pd


RGB_CHANNELS = {
    "camera_mean_red": "Red",
    "camera_mean_green": "Green",
    "camera_mean_blue": "Blue",
}


RATE_COLORS = {
    "H10 reference rate": "#f2f4ff",
    "CHROM blind winner": "#ffb648",
    "POS blind winner": "#b68cff",
    "Y blind winner": "#57d9e6",
    "Reference-informed candidate": "#ff8fbd",
}


def _svg_plot(series: list[dict], y_label: str, cursor: float | None, percent: bool = False) -> str:
    """Render a responsive SVG server-side so embedded-browser timing cannot blank it."""
    width, height, left, right, top, bottom = 1000.0, 260.0, 70.0, 16.0, 14.0, 34.0
    plot_width, plot_height = width - left - right, height - top - bottom
    points = [
        (float(x), float(y))
        for item in series
        for x, y in zip(item["time_s"], item["value"])
        if np.isfinite(x) and np.isfinite(y)
    ]
    if not points:
        return (
            f'<svg viewBox="0 0 {width:g} {height:g}" preserveAspectRatio="none" role="img">'
            f'<text x="{left:g}" y="38" fill="#a0abc7" font-size="15">'
            "No eligible series in this take</text></svg>"
        )
    x_min, x_max = min(x for x, _ in points), max(x for x, _ in points)
    y_min, y_max = min(y for _, y in points), max(y for _, y in points)
    if x_max <= x_min:
        x_max = x_min + 1.0
    if y_max <= y_min:
        y_min, y_max = y_min - 1.0, y_max + 1.0
    pad = (y_max - y_min) * 0.08
    y_min, y_max = y_min - pad, y_max + pad

    def sx(value: float) -> float:
        return left + (value - x_min) / (x_max - x_min) * plot_width

    def sy(value: float) -> float:
        return top + (y_max - value) / (y_max - y_min) * plot_height

    parts = [f'<svg viewBox="0 0 {width:g} {height:g}" preserveAspectRatio="none" role="img">',
             f'<rect width="{width:g}" height="{height:g}" fill="#0e1423"/>']
    for i in range(5):
        y = top + plot_height * i / 4
        value = y_max - (y_max - y_min) * i / 4
        parts.append(f'<line x1="{left:g}" y1="{y:.2f}" x2="{width-right:g}" y2="{y:.2f}" stroke="#27334e"/>')
        tick_label = format(value, ".2f" if percent else ".0f")
        parts.append(f'<text x="30" y="{y+4:.2f}" fill="#a0abc7" font-size="11" text-anchor="end">{tick_label}</text>')
    for i in range(6):
        value = x_min + (x_max - x_min) * i / 5
        x = sx(value)
        parts.append(f'<line x1="{x:.2f}" y1="{top:g}" x2="{x:.2f}" y2="{top+plot_height:g}" stroke="#27334e"/>')
        parts.append(f'<text x="{x:.2f}" y="{height-bottom+22:g}" fill="#a0abc7" font-size="11" text-anchor="middle">{value:.0f}</text>')
    safe_label = html.escape(y_label)
    parts.append(f'<text x="14" y="{top+plot_height/2:g}" fill="#a0abc7" font-size="11" text-anchor="middle" transform="rotate(-90 14 {top+plot_height/2:g})">{safe_label}</text>')
    for item in series:
        commands: list[str] = []
        started = False
        previous: float | None = None
        for x_raw, y_raw in zip(item["time_s"], item["value"]):
            x, y = float(x_raw), float(y_raw)
            if not np.isfinite(x) or not np.isfinite(y):
                started, previous = False, None
                continue
            if previous is not None and x - previous > float(item.get("max_gap", np.inf)):
                started = False
            commands.append(f'{"L" if started else "M"}{sx(x):.2f},{sy(y):.2f}')
            started, previous = True, x
        if commands:
            dash = ' stroke-dasharray="7 5"' if item.get("dashed") else ""
            color = html.escape(str(item.get("color", "#cbd5e1")), quote=True)
            parts.append(f'<path d="{" ".join(commands)}" fill="none" stroke="{color}" stroke-width="2"{dash}/>')
    if cursor is not None and x_min <= float(cursor) <= x_max:
        x = sx(float(cursor))
        parts.append(f'<line x1="{x:.2f}" y1="{top:g}" x2="{x:.2f}" y2="{top+plot_height:g}" stroke="#ffb648" stroke-width="2" stroke-dasharray="6 5"/>')
    parts.append("</svg>")
    return "".join(parts)


def _downsample(x: np.ndarray, y: np.ndarray, max_points: int) -> tuple[list[float], list[float]]:
    if len(x) > max_points:
        take = np.unique(np.linspace(0, len(x) - 1, max_points).round().astype(int))
        x, y = x[take], y[take]
    return x.astype(float).tolist(), y.astype(float).tolist()


def rppg_observation_payload(
    frame: pd.DataFrame,
    take_id: str,
    cursor_time_s: float,
    max_points: int = 1800,
) -> dict:
    """Build an HTML-safe payload from recorded iPad RGB and derived rate rows."""
    rows = frame[
        (frame["take_id"].astype(str) == str(take_id))
        & (frame["source"].astype(str) == "iPad8_RGB")
        & (frame["layer"].astype(str) == "sensor")
        & frame["channel"].astype(str).isin(RGB_CHANNELS)
    ].copy()
    if rows.empty:
        raise ValueError(f"No iPad RGB observations are available for take {take_id!r}")
    rows["local_time_s"] = (
        pd.to_numeric(rows["take_time_s"], errors="coerce")
        if "take_time_s" in rows else pd.to_numeric(rows["time_s"], errors="coerce") - float(rows["time_s"].min())
    )
    rows = rows.dropna(subset=["local_time_s", "value"]).sort_values("local_time_s")
    start_s = float(rows["time_s"].min())
    stop_s = float(rows["time_s"].max())
    local_cursor = float(cursor_time_s) - start_s
    cursor_inside = start_s <= float(cursor_time_s) <= stop_s
    display_time = local_cursor if cursor_inside else float(rows["local_time_s"].max())

    rgb = {}
    for channel, label in RGB_CHANNELS.items():
        part = rows[rows["channel"].astype(str) == channel]
        if part.empty:
            continue
        x = part["local_time_s"].to_numpy(dtype=float)
        y = part["value"].to_numpy(dtype=float)
        x_plot, y_plot = _downsample(x, y, max_points)
        mean = float(np.mean(y))
        normalized = ((y / mean) - 1.0) * 100.0 if mean else np.zeros_like(y)
        _, normalized_plot = _downsample(x, normalized, max_points)
        nearest = int(np.argmin(np.abs(x - display_time)))
        rgb[label.lower()] = {
            "time_s": x_plot,
            "fractional_change_pct": normalized_plot,
            "channel": channel,
            "mean_raw": mean,
            "nearest_raw": float(y[nearest]),
            "nearest_fractional_change_pct": float(normalized[nearest]),
            "source": str(part["source"].iloc[0]),
            "clock_provenance": str(part["clock_provenance"].iloc[0]) if "clock_provenance" in part else "unspecified",
            "alignment_status": str(part["alignment_status"].iloc[0]) if "alignment_status" in part else "unknown",
        }

    if not rgb:
        raise ValueError(f"No RGB channel series found in take {take_id!r}")

    # The three ROI mean streams in this export share timestamps. Show a small,
    # literal sample of those numeric estimator inputs rather than suggesting
    # that the dashboard is forwarding stored image frames.
    input_frame = rows.pivot(index="local_time_s", columns="channel", values="value").sort_index()
    input_frame = input_frame.dropna(subset=list(RGB_CHANNELS))
    input_times = input_frame.index.to_numpy(dtype=float)
    nearest_input = int(np.argmin(np.abs(input_times - display_time)))
    sample_start = max(0, nearest_input - 3)
    sample_stop = min(len(input_frame), nearest_input + 4)
    input_samples = [
        {
            "time_s": float(index),
            "red": float(values["camera_mean_red"]),
            "green": float(values["camera_mean_green"]),
            "blue": float(values["camera_mean_blue"]),
        }
        for index, values in input_frame.iloc[sample_start:sample_stop].iterrows()
    ]

    rate_rows = frame[
        (frame["take_id"].astype(str) == str(take_id))
        & (frame["unit"].astype(str).str.lower().isin(["bpm", "beats/min", "beat/min"]))
        & (frame["layer"].astype(str).isin(["sensor", "estimate"]))
    ].copy()
    rate_rows["descriptor"] = (rate_rows["channel"].astype(str) + " " + rate_rows["source"].astype(str)).str.lower()
    rates = []
    for _, part in rate_rows.groupby(["channel", "source"], sort=False):
        descriptor = " ".join(part["descriptor"].unique())
        ref_candidate = any(tag in descriptor for tag in ("diagnostic", "candidate", "guided"))
        if ref_candidate:
            label = "Reference-informed candidate"
        elif "h10" in descriptor:
            label = "H10 reference rate"
        elif "chrom" in descriptor and "ipad" in descriptor:
            label = "CHROM blind winner"
        elif "pos" in descriptor and "ipad" in descriptor:
            label = "POS blind winner"
        elif ("y_blind" in descriptor or "ipad8_y" in descriptor) and "ipad" in descriptor:
            label = "Y blind winner"
        else:
            continue
        channel, source = str(part["channel"].iloc[0]), str(part["source"].iloc[0])
        x = pd.to_numeric(part["take_time_s"], errors="coerce").to_numpy(dtype=float) if "take_time_s" in part else pd.to_numeric(part["time_s"], errors="coerce").to_numpy(dtype=float) - start_s
        y = pd.to_numeric(part["value"], errors="coerce").to_numpy(dtype=float)
        valid = np.isfinite(x) & np.isfinite(y)
        x, y = x[valid], y[valid]
        if not len(x):
            continue
        x, y = _downsample(x, y, max_points)
        rates.append({
            "label": label, "channel": channel, "source": source,
            "time_s": x, "value": y,
            "reference_informed": ref_candidate,
            "clock_provenance": str(part["clock_provenance"].iloc[0]) if "clock_provenance" in part else "unspecified",
            "alignment_status": str(part["alignment_status"].iloc[0]) if "alignment_status" in part else "unknown",
        })

    rgb_plot_series = [
        {"time_s": value["time_s"], "value": value["fractional_change_pct"], "color": color, "max_gap": 1.5}
        for (key, value), color in zip(rgb.items(), ("#ff666e", "#51e395", "#76a9ff"))
    ]
    for rate in rates:
        rate["color"] = RATE_COLORS.get(rate["label"], "#cbd5e1")
        rate["max_gap"] = 10.0
    rate_legend_html = "".join(
        f'<span><i class="swatch" style="background:{rate["color"]};'
        f'{"height:0;border-top:2px dashed " + rate["color"] if rate["reference_informed"] else ""}'
        f'"></i>{html.escape(rate["label"])}{" (diagnostic)" if rate["reference_informed"] else ""}</span>'
        for rate in rates
    )

    return {
        "mode": "real_observation",
        "scenario": str(rows["scenario"].iloc[0]) if "scenario" in rows else "unspecified",
        "take_id": str(take_id),
        "episode_id": str(rows["episode_id"].iloc[0]) if "episode_id" in rows else str(take_id),
        "session_start_s": start_s,
        "session_stop_s": stop_s,
        "local_duration_s": float(rows["local_time_s"].max()),
        "cursor_session_time_s": float(cursor_time_s),
        "cursor_local_time_s": local_cursor if cursor_inside else None,
        "display_local_time_s": display_time,
        "cursor_inside_take": bool(cursor_inside),
        "rgb": rgb,
        "input_samples": input_samples,
        "rates": rates,
        "rgb_plot_svg": _svg_plot(rgb_plot_series, "change (%)", local_cursor if cursor_inside else None, percent=True),
        "rate_plot_svg": _svg_plot(rates, "rate (bpm)", local_cursor if cursor_inside else None),
        "rate_legend_html": rate_legend_html,
        "rgb_transform": "per-channel mean-normalized fractional change: 100 × (ROI mean / take mean − 1)",
        "candidate_warning": "Reference-informed candidates are diagnostic overlays, not blind outputs; bin proximity alone does not prove physical origin.",
    }
