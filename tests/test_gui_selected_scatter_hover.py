"""Stage 5.2.1.1 screen-space selected-potential hover regression tests."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pytest

from chi_gui.widgets.lsv_analysis import (
    SELECTED_POINT_HOVER_RADIUS_PX,
    nearest_selected_scatter_point,
)
from plotting.selected_potential import (
    SelectedScatterPoint,
    SelectedScatterSeries,
    build_selected_potential_figure,
)


def _all_points(series):
    return tuple(point for group_series in series for point in group_series.points)


def _hit_at_point(axis, series, point, *, dx=0.0, dy=0.0):
    x_px, y_px = axis.transData.transform((point.x, point.value_uA))
    return nearest_selected_scatter_point(series, axis, x_px + dx, y_px + dy)


@pytest.mark.parametrize("position", ("first", "middle", "last"))
def test_first_middle_and_last_individual_points_can_be_hit(synthetic_analysis_result, position):
    figure, series = build_selected_potential_figure(
        synthetic_analysis_result, "magnitude", include_hover_metadata=True
    )
    try:
        figure.canvas.draw()
        points = _all_points(series)
        index = {"first": 0, "middle": len(points) // 2, "last": len(points) - 1}[position]
        assert _hit_at_point(figure.axes[0], series, points[index]) is points[index]
    finally:
        plt.close(figure)


@pytest.mark.parametrize("selector", (min, max))
def test_horizontal_edge_points_can_be_hit(synthetic_analysis_result, selector):
    figure, series = build_selected_potential_figure(
        synthetic_analysis_result, "signed", include_hover_metadata=True
    )
    try:
        figure.canvas.draw()
        points = _all_points(series)
        point = selector(points, key=lambda item: item.x)
        assert _hit_at_point(figure.axes[0], series, point) is point
    finally:
        plt.close(figure)


@pytest.mark.parametrize("selector", (min, max))
def test_vertical_edge_points_can_be_hit(synthetic_analysis_result, selector):
    figure, series = build_selected_potential_figure(
        synthetic_analysis_result, "magnitude", include_hover_metadata=True
    )
    try:
        figure.canvas.draw()
        points = _all_points(series)
        point = selector(points, key=lambda item: item.value_uA)
        assert _hit_at_point(figure.axes[0], series, point) is point
    finally:
        plt.close(figure)


class _IdentityTransform:
    def transform(self, coordinate):
        return coordinate


class _IdentityAxis:
    def __init__(self):
        self.transData = _IdentityTransform()


def test_nearest_of_two_close_points_is_selected():
    first = SelectedScatterPoint("G", "A", 10.0, 10.0)
    second = SelectedScatterPoint("G", "B", 14.0, 10.0)
    series = (SelectedScatterSeries(None, (first, second)),)
    assert nearest_selected_scatter_point(series, _IdentityAxis(), 13.0, 10.0) is second


def test_exact_distance_tie_uses_stable_manifest_order():
    first = SelectedScatterPoint("G", "first", 10.0, 10.0)
    second = SelectedScatterPoint("G", "second", 14.0, 10.0)
    series = (SelectedScatterSeries(None, (first, second)),)
    assert nearest_selected_scatter_point(series, _IdentityAxis(), 12.0, 10.0) is first


def test_outside_hover_radius_returns_no_point():
    point = SelectedScatterPoint("G", "S1", 10.0, 10.0)
    series = (SelectedScatterSeries(None, (point,)),)
    assert nearest_selected_scatter_point(
        series, _IdentityAxis(), 10.0 + SELECTED_POINT_HOVER_RADIUS_PX + 0.01, 10.0
    ) is None


def test_s11_like_arbitrary_id_has_no_special_case():
    points = (
        SelectedScatterPoint("G", "ordinary", 0.0, 0.0),
        SelectedScatterPoint("G", "S11-any-user-text", 4.0, 3.0),
    )
    hit = nearest_selected_scatter_point(
        (SelectedScatterSeries(None, points),), _IdentityAxis(), 4.0, 3.0, radius_px=1.0
    )
    assert hit is points[1]
    assert hit.sample_id == "S11-any-user-text"


def test_s11_point_is_hit_on_real_selected_scatter_transform(synthetic_analysis_result):
    figure, series = build_selected_potential_figure(
        synthetic_analysis_result, "magnitude", include_hover_metadata=True
    )
    try:
        figure.canvas.draw()
        point = next(point for point in _all_points(series) if point.sample_id == "S11")
        assert _hit_at_point(figure.axes[0], series, point) is point
    finally:
        plt.close(figure)


def test_hover_metadata_contains_every_material_and_no_bare_or_mean(synthetic_analysis_result):
    figure, series = build_selected_potential_figure(
        synthetic_analysis_result, "magnitude", include_hover_metadata=True
    )
    try:
        points = _all_points(series)
        expected = tuple(
            item for item in synthetic_analysis_result.files
            if item.manifest.electrode_type == "Material"
        )
        assert len(points) == len(expected) == 39
        assert {(point.group, point.sample_id) for point in points} == {
            (item.manifest.group, item.manifest.sample_id) for item in expected
        }
        assert all(item.manifest.electrode_type != "Bare" for item in expected)
        # One hover point per Material row proves mean/errorbar artists add none.
        assert sum(len(item.points) for item in series) == len(expected)
    finally:
        plt.close(figure)


def test_magnitude_and_signed_hover_values_are_metric_specific(synthetic_analysis_result):
    magnitude_figure, magnitude_series = build_selected_potential_figure(
        synthetic_analysis_result, "magnitude", include_hover_metadata=True
    )
    signed_figure, signed_series = build_selected_potential_figure(
        synthetic_analysis_result, "signed", include_hover_metadata=True
    )
    try:
        magnitude = {(p.group, p.sample_id): p.value_uA for p in _all_points(magnitude_series)}
        signed = {(p.group, p.sample_id): p.value_uA for p in _all_points(signed_series)}
        expected_rows = [
            item for item in synthetic_analysis_result.files
            if item.manifest.electrode_type == "Material"
        ]
        for item in expected_rows:
            key = (item.manifest.group, item.manifest.sample_id)
            assert magnitude[key] == item.selected.response_magnitude_uA
            assert signed[key] == item.selected.current_uA
    finally:
        plt.close(magnitude_figure)
        plt.close(signed_figure)


def test_hover_metadata_does_not_change_static_render(synthetic_analysis_result):
    static_figure = build_selected_potential_figure(synthetic_analysis_result, "magnitude")
    metadata_figure, _series = build_selected_potential_figure(
        synthetic_analysis_result, "magnitude", include_hover_metadata=True
    )
    try:
        static_figure.canvas.draw(); metadata_figure.canvas.draw()
        static_pixels = np.asarray(static_figure.canvas.buffer_rgba()).copy()
        metadata_pixels = np.asarray(metadata_figure.canvas.buffer_rgba()).copy()
        np.testing.assert_array_equal(static_pixels, metadata_pixels)
    finally:
        plt.close(static_figure)
        plt.close(metadata_figure)
