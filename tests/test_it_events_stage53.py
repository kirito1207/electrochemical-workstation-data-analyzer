from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from analysis import (
    CalibrationSelection, Event, EventAnalysisError, EventTimeline, ITEventInput,
    PlateauPolicy, ResponseWindow, analyze_it_event_batch, analyze_it_events,
    define_response_windows,
)
from export import export_it_event_csv_bundle
from plotting import build_it_event_figure


def _timeline():
    return EventTimeline(
        events=(
            Event("e3", 91.0, "Gas switch"),
            Event("e1", 31.0, "Light on", 2.0, "level"),
            Event("e2", 61.0, "Temperature", 7.0, "level", "confirmed in notebook"),
        ),
        user_confirmed=True,
        source="researcher-confirmed",
    )


def test_event_without_numeric_value_and_arbitrary_name_is_accepted():
    event = Event("light", 120.0, "Light on / manual disturbance")
    EventTimeline((event,), True).validate()
    assert event.value is None and event.unit is None


def test_event_with_value_and_arbitrary_unit_is_accepted():
    event = Event("temp", 180.0, "Temperature", 35.0, "°C")
    EventTimeline((event,), True).validate()
    assert (event.value, event.unit) == (35.0, "°C")


def test_events_are_sorted_by_time():
    assert [row.event_id for row in _timeline().events] == ["e1", "e2", "e3"]


def test_duplicate_event_id_is_rejected():
    timeline = EventTimeline((Event("x", 10, "A"), Event("x", 20, "B")), True)
    with pytest.raises(EventAnalysisError, match="unique"):
        timeline.validate()


def test_event_time_range_validation():
    with pytest.raises(EventAnalysisError, match="outside"):
        _timeline().validate(recording_start_s=1.0, recording_end_s=80.0)


def test_unconfirmed_timeline_cannot_enter_formal_analysis(synthetic_it_data):
    timeline = replace(_timeline(), user_confirmed=False)
    with pytest.raises(EventAnalysisError, match="user_confirmed"):
        analyze_it_events(synthetic_it_data, timeline, sample_id="E1")


def test_default_baseline_and_event_segments_are_independent(synthetic_it_data):
    windows = define_response_windows(synthetic_it_data, _timeline())
    assert windows[0] == ResponseWindow(None, 1.0, 31.0, "baseline")
    assert [(row.event_id, row.start_time_s, row.end_time_s) for row in windows[1:]] == [
        ("e1", 31.0, 61.0), ("e2", 61.0, 91.0), ("e3", 91.0, 120.0)
    ]


def test_tail_fraction_preserves_window_based_delta_formula(synthetic_it_data):
    result = analyze_it_events(synthetic_it_data, _timeline(), sample_id="Any sample", group="Any Group")
    assert result.windows[0].n == 6
    assert result.windows[0].actual_start_s == 25.0
    e2 = next(row for row in result.responses if row.event_id == "e2")
    assert e2.baseline_mean_uA == pytest.approx(2.0)
    assert e2.response_mean_uA == pytest.approx(-1.5)
    assert e2.delta_current_uA == pytest.approx(-3.5)
    assert e2.response_magnitude_uA == pytest.approx(3.5)


def test_explicit_windows_are_supported_without_single_point_response(synthetic_it_data):
    policy = PlateauPolicy("explicit", explicit_windows=(
        ResponseWindow(None, 1.0, 3.0, "baseline"),
        ResponseWindow("e1", 31.0, 31.5, "custom"),
    ))
    result = analyze_it_events(synthetic_it_data, _timeline(), sample_id="E1", policy=policy)
    single = next(row for row in result.responses if row.event_id == "e1")
    assert single.response_n == 1 and single.status == "unavailable"
    assert next(row for row in result.responses if row.event_id == "e2").status == "unavailable"


def test_calibration_is_off_by_default_even_for_numeric_events(synthetic_it_data):
    result = analyze_it_events(synthetic_it_data, _timeline(), sample_id="E1")
    assert result.calibration is None


def test_calibration_uses_only_explicitly_selected_events(synthetic_it_data):
    selection = CalibrationSelection(("e1", "e2"), "Condition level", "level")
    result = analyze_it_events(synthetic_it_data, _timeline(), sample_id="E1", calibration_selection=selection)
    assert result.calibration.event_ids == ("e1", "e2")
    assert result.calibration.x_values == (2.0, 7.0)
    assert result.calibration.slope_uA_per_x == pytest.approx(-0.5)
    assert result.calibration.intercept_uA == pytest.approx(0.0, abs=1e-12)


def test_calibration_rejects_missing_value_and_mixed_units(synthetic_it_data):
    with pytest.raises(EventAnalysisError, match="numeric value"):
        analyze_it_events(synthetic_it_data, _timeline(), sample_id="E1", calibration_selection=CalibrationSelection(("e2", "e3"), "X", "level"))
    mixed = EventTimeline((Event("a", 31, "A", 1, "uM"), Event("b", 61, "B", 2, "mM")), True)
    with pytest.raises(EventAnalysisError, match="automatic conversion"):
        analyze_it_events(synthetic_it_data, mixed, sample_id="E1", calibration_selection=CalibrationSelection(("a", "b"), "Concentration", "uM"))


def test_shared_timeline_handles_variable_record_duration_per_file(synthetic_it_data):
    short = replace(
        synthetic_it_data,
        file_name="short.bin",
        n_points=70,
        actual_last_time_s=70.0,
        actual_recorded_duration_s=70.0,
        time_s=np.asarray(synthetic_it_data.time_s[:70]),
        current_A=np.asarray(synthetic_it_data.current_A[:70]),
    )
    batch = analyze_it_event_batch((
        ITEventInput(synthetic_it_data, "Sample Alpha", "G1"),
        ITEventInput(short, "Sample beta-自由", "Condition-N"),
    ), _timeline())
    assert len(batch.files) == 2
    late = next(row for row in batch.files[1].responses if row.event_id == "e3")
    assert late.status == "unavailable"
    assert any(row.status == "ok" for row in batch.files[1].responses)


@pytest.mark.parametrize("count", (1, 2, 5, 12))
def test_batch_has_no_fixed_file_or_group_count(synthetic_it_data, count):
    inputs = tuple(ITEventInput(synthetic_it_data, f"sample-{i}", f"group-{i}") for i in range(count))
    assert len(analyze_it_event_batch(inputs, _timeline()).files) == count


def test_generic_event_export_uses_generic_names(tmp_path, synthetic_it_data):
    batch = analyze_it_event_batch((ITEventInput(synthetic_it_data, "E1", "Control"),), _timeline())
    files = export_it_event_csv_bundle(batch, tmp_path)
    assert {row.name for row in files} == {"events.csv", "event_responses.csv", "response_windows.csv", "event_summary.csv"}
    assert not any("concentration" in row.name.lower() for row in files)


def test_optional_calibration_export_and_event_marker_figure(tmp_path, synthetic_it_data):
    selection = CalibrationSelection(("e1", "e2"), "Condition level", "level")
    batch = analyze_it_event_batch(
        (ITEventInput(synthetic_it_data, "E1", "G"),),
        _timeline(),
        calibration_selection=selection,
    )
    assert "calibration.csv" in {row.name for row in export_it_event_csv_bundle(batch, tmp_path)}
    figure = build_it_event_figure(batch)
    try:
        labels = {text.get_text() for text in figure.axes[0].texts}
        assert any("Light on" in label and "2 level" in label for label in labels)
        assert len(figure.axes[0].lines) == 1 + len(batch.timeline.events)
    finally:
        import matplotlib.pyplot as plt
        plt.close(figure)


def test_generic_event_core_contains_no_pb42_or_concentration_assumptions():
    text = Path("src/analysis/it_events.py").read_text(encoding="utf-8").lower()
    for token in ("pb42", "pb10", "pb20", "exactly 42", "concentration_um", "addition_time"):
        assert token not in text
