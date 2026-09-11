"""Generic i-t raw curves with user-confirmed event markers."""
from __future__ import annotations
from .common import new_figure, style_axes

def build_it_event_figure(result):
    figure, axis = new_figure(width=7.2, height=4.4)
    for item in result.files:
        axis.plot(item.data.time_s, item.data.current_A * 1e6, linewidth=0.9, label=item.sample_id)
    for event in result.timeline.events:
        axis.axvline(event.time_s, color="#666666", linewidth=0.8, linestyle="--")
        label = event.name
        if event.value is not None:
            label += f"\n{event.value:g}" + (f" {event.unit}" if event.unit else "")
        axis.text(event.time_s, 0.98, label, transform=axis.get_xaxis_transform(), rotation=90, va="top", ha="right", fontsize=7)
    axis.set(xlabel="Time / s", ylabel="Current / µA", title="i-t raw time series with confirmed Events")
    if result.files: axis.legend()
    style_axes(axis)
    return figure

__all__ = ["build_it_event_figure"]
