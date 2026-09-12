"""Generic i-t Event figures built only from completed backend results."""
from __future__ import annotations
from dataclasses import dataclass
import math

import numpy as np

from .common import (colors_for_groups, configure_group_ticks, group_figure_width,
                     legend_columns, new_figure, style_axes)


@dataclass(frozen=True, slots=True)
class ITResponseScatterPoint:
    x: float
    value_uA: float
    sample_id: str
    group: str
    event_id: str
    event_name: str


@dataclass(frozen=True, slots=True)
class ITResponseScatterSeries:
    event_id: str
    event_name: str
    points: tuple[ITResponseScatterPoint, ...]

def build_it_event_figure(result):
    figure, axis = new_figure(width=7.2, height=4.4)
    timeline_signatures = {
        tuple((event.event_id, event.time_s, event.name, event.value, event.unit)
              for event in item.timeline.events)
        for item in result.files
    }
    for file_index, item in enumerate(result.files):
        line, = axis.plot(item.data.time_s, item.data.current_A * 1e6,
                          linewidth=0.9, label=item.sample_id)
        if len(timeline_signatures) > 1:
            for event in item.timeline.events:
                axis.axvline(event.time_s, color=line.get_color(), linewidth=0.75,
                             linestyle="--", alpha=0.72)
                axis.text(event.time_s, 0.98 - 0.08 * (file_index % 4),
                          f"{item.sample_id}: {event.name}",
                          transform=axis.get_xaxis_transform(), rotation=90,
                          va="top", ha="right", fontsize=6, color=line.get_color())
    if len(timeline_signatures) <= 1:
        shared_events = result.files[0].timeline.events if result.files else result.timeline.events
        for event in shared_events:
            axis.axvline(event.time_s, color="#666666", linewidth=0.8, linestyle="--")
            label = event.name
            if event.value is not None:
                label += f"\n{event.value:g}" + (f" {event.unit}" if event.unit else "")
            axis.text(event.time_s, 0.98, label, transform=axis.get_xaxis_transform(),
                      rotation=90, va="top", ha="right", fontsize=7)
    axis.set(xlabel="Time / s", ylabel="Current / µA", title="i-t raw time series with confirmed Events")
    if result.files: axis.legend(ncol=legend_columns(len(result.files)))
    style_axes(axis)
    return figure


def build_it_response_figure(result, *, include_hover_metadata=False):
    """Plot individual responses and group mean ± sample SD for every Event."""

    groups = tuple(dict.fromkeys(item.group for item in result.files))
    events_by_id = {}
    for item in result.files:
        for response in item.responses:
            events_by_id.setdefault(response.event_id, response.event_name)
    events = tuple(events_by_id.items())
    width = group_figure_width(tuple(name for _event_id, name in events), base=6.5)
    figure, axis = new_figure(width=width, height=4.6)
    colors = colors_for_groups(groups)
    metric = result.analysis_metric
    event_centres = np.arange(len(events), dtype=float)
    offsets = np.linspace(-0.28, 0.28, max(len(groups), 1)) if len(groups) > 1 else np.zeros(1)
    series = []
    for event_index, (event_id, event_name) in enumerate(events):
        event_points = []
        for group_index, group in enumerate(groups):
            rows = [row for item in result.files for row in item.responses
                    if item.group == group and row.event_id == event_id and row.status == "ok"]
            values = [row.delta_current_uA if metric == "signed" else row.response_magnitude_uA
                      for row in rows]
            centre = float(event_centres[event_index] + offsets[group_index])
            jitter = np.linspace(-0.045, 0.045, len(values)) if len(values) > 1 else np.zeros(len(values))
            for row, value, delta_x in zip(rows, values, jitter):
                point = ITResponseScatterPoint(centre + float(delta_x), float(value), row.sample_id,
                                               group, event_id, event_name)
                event_points.append(point)
                axis.scatter(point.x, point.value_uA, s=25, color=colors[group], alpha=0.82,
                             zorder=3, label=group if event_index == 0 and delta_x == jitter[0] else None)
            if values:
                mean = float(np.mean(values))
                sd = float(np.std(values, ddof=1)) if len(values) > 1 else math.nan
                axis.errorbar(centre, mean, yerr=None if math.isnan(sd) else sd, fmt="D", ms=4,
                              color=colors[group], capsize=3, linewidth=1.1, zorder=4)
        series.append(ITResponseScatterSeries(event_id, event_name, tuple(event_points)))
    configure_group_ticks(axis, tuple(name for _event_id, name in events))
    axis.set(xlabel="Event", ylabel=("Signed ΔI / µA" if metric == "signed" else "|ΔI| / µA"),
             title="Event responses: individual samples and mean ± SD")
    if groups:
        axis.legend(title="Group", ncol=legend_columns(len(groups)))
    style_axes(axis)
    return (figure, tuple(series)) if include_hover_metadata else figure


def build_it_calibration_figure(result):
    """Plot explicitly selected calibration points and per-record OLS fits."""

    figure, axis = new_figure(width=6.5, height=4.5)
    plotted = 0
    for item in result.files:
        calibration = item.calibration
        if calibration is None:
            continue
        responses = {row.event_id: row for row in item.responses if row.status == "ok"}
        x = np.asarray(calibration.x_values, dtype=float)
        y = np.asarray([
            responses[event_id].delta_current_uA
            if calibration.analysis_metric == "signed"
            else responses[event_id].response_magnitude_uA
            for event_id in calibration.event_ids
        ], dtype=float)
        axis.scatter(x, y, s=28, label=f"{item.sample_id} data")
        order = np.argsort(x)
        axis.plot(x[order], calibration.intercept_uA + calibration.slope_uA_per_x * x[order],
                  linewidth=1.1, label=f"{item.sample_id} OLS (R²={calibration.r_squared:.3g})")
        plotted += 1
    selection = result.calibration_selection
    x_label = f"{selection.x_label} / {selection.x_unit}" if selection else "Calibration x"
    axis.set(xlabel=x_label, ylabel=("Signed ΔI / µA" if result.analysis_metric == "signed" else "|ΔI| / µA"),
             title="Explicit Event calibration")
    if plotted:
        axis.legend(ncol=legend_columns(plotted))
    else:
        axis.text(0.5, 0.5, "Calibration 未开启", transform=axis.transAxes, ha="center", va="center")
    style_axes(axis)
    return figure

__all__ = ["ITResponseScatterPoint", "ITResponseScatterSeries", "build_it_calibration_figure",
           "build_it_event_figure", "build_it_response_figure"]
