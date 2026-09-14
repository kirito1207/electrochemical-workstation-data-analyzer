from __future__ import annotations

import tkinter as tk

import pytest

from analysis import ContinuousStabilitySettings, InterruptionType
from analysis.it_events import ITAnalysisMode
from chi_gui.it_workflow import ITMetadataDraftRow, ITWorkflowState, workflow_status_lines
from chi_gui.widgets.it_analysis import ITSettingsPanel, it_settings_view


def _workflow():
    workflow = ITWorkflowState(metadata_rows=[
        ITMetadataDraftRow("r1", "sample-1.bin", sample_id="S1", group="A"),
        ITMetadataDraftRow("r2", "sample-2.bin", sample_id="S2", group="A"),
    ])
    workflow.current_interruption_record_key = "r1"
    return workflow


@pytest.fixture
def mode_panel():
    root = tk.Tk(); root.geometry("1280x800")
    workflow = _workflow()
    panel = ITSettingsPanel(
        root, on_change=lambda *_args: None, on_confirm_metadata=lambda: None,
        on_confirm_timeline=lambda: None, on_add_cursor_event=lambda: None,
        on_run=lambda: None,
    )
    panel.pack(fill="both", expand=True)
    panel.render(workflow, workspace_token="workspace-1")
    root.update()
    try:
        yield root, panel, workflow
    finally:
        root.destroy()


def test_view_is_derived_from_existing_analysis_mode():
    assert it_settings_view(ITAnalysisMode.CONTINUOUS) == "continuous"
    assert it_settings_view(ITAnalysisMode.CONTINUOUS, event_setup_requested=True) == "event"
    assert it_settings_view(ITAnalysisMode.EVENT) == "event"


def test_no_event_shows_only_continuous_mode_frame(mode_panel):
    _root, panel, workflow = mode_panel
    assert workflow.analysis_mode == ITAnalysisMode.CONTINUOUS
    assert panel.metadata_frame.winfo_manager() == "grid"
    assert panel.continuous_frame.winfo_manager() == "grid"
    assert panel.event_mode_frame.winfo_manager() == ""
    assert panel.event_frame.winfo_manager() == "grid"  # retained inside hidden parent
    assert panel.event_settings_frame.winfo_manager() == ""
    assert panel.calibration_details.winfo_manager() == ""
    assert "Continuous Stability" in panel.mode_status.get()


def test_continuous_sections_are_split_and_interruption_table_is_compact(mode_panel):
    _root, panel, _workflow_state = mode_panel
    assert panel.continuous_windows_frame.winfo_manager() == "grid"
    assert panel.interruptions_frame.winfo_manager() == "grid"
    assert int(panel.interruptions.cget("height")) == 3
    assert panel.interruptions.cget("yscrollcommand")


def test_enter_event_setup_expands_editor_without_changing_scientific_mode(mode_panel):
    _root, panel, workflow = mode_panel
    before = workflow.current_signature()
    panel._toggle_event_setup()
    assert workflow.analysis_mode == ITAnalysisMode.CONTINUOUS
    assert workflow.current_signature() == before
    assert panel.event_mode_frame.winfo_manager() == "grid"
    assert panel.continuous_frame.winfo_manager() == ""
    assert panel.event_frame.winfo_manager() == "grid"
    assert panel.event_settings_frame.winfo_manager() == ""
    assert "添加首个 Event" in panel.mode_detail.get()


def test_first_unconfirmed_event_switches_to_full_event_view(mode_panel):
    _root, panel, workflow = mode_panel
    workflow.add_event(time_s=10, name="Light on")
    panel.render(workflow, workspace_token="workspace-1")
    assert workflow.analysis_mode == ITAnalysisMode.EVENT
    assert not workflow.timeline_confirmed
    assert panel.event_mode_frame.winfo_manager() == "grid"
    assert panel.event_settings_frame.winfo_manager() == "grid"
    assert panel.continuous_frame.winfo_manager() == ""
    assert panel.event_entry_button.winfo_manager() == ""


def test_delete_last_event_restores_continuous_and_preserves_stability_state(mode_panel):
    _root, panel, workflow = mode_panel
    settings = ContinuousStabilitySettings(1, 100, 1, 10, 90, 100)
    workflow.set_continuous_settings(settings)
    interval = workflow.add_interruption(
        "r1", start_s=40, end_s=50,
        interruption_type=InterruptionType.MANUAL_PAUSE, reason="pause",
    )
    event = workflow.add_event(time_s=10, name="Event")
    workflow.set_tail_fraction(0.35)
    workflow.set_metric("magnitude")
    panel.render(workflow, workspace_token="workspace-1")
    workflow.delete_events((event.event_id,))
    panel.render(workflow, workspace_token="workspace-1")
    assert workflow.analysis_mode == ITAnalysisMode.CONTINUOUS
    assert workflow.continuous_settings == settings
    assert workflow.continuous_interruptions["r1"] == [interval]
    assert workflow.tail_fraction == 0.35 and workflow.analysis_metric == "magnitude"
    assert panel.continuous_frame.winfo_manager() == "grid"
    assert panel.analysis_start.get() == "1" and panel.late_end.get() == "100"


def test_calibration_progressive_disclosure_preserves_disabled_state(mode_panel):
    _root, panel, workflow = mode_panel
    first = workflow.add_event(time_s=10, name="A", value=1, unit="level")
    second = workflow.add_event(time_s=20, name="B", value=2, unit="level")
    panel.render(workflow, workspace_token="workspace-1")
    assert panel.calibration_details.winfo_manager() == ""
    workflow.set_calibration(True, (first.event_id, second.event_id), "Level", "level")
    panel.render(workflow, workspace_token="workspace-1")
    assert panel.calibration_details.winfo_manager() == "grid"
    workflow.set_calibration(False, (first.event_id, second.event_id), "Level", "level")
    panel.render(workflow, workspace_token="workspace-1")
    assert panel.calibration_details.winfo_manager() == ""
    assert workflow.calibration_event_ids == (first.event_id, second.event_id)
    assert workflow.calibration_x_label == "Level" and workflow.calibration_x_unit == "level"


def test_mode_aware_status_excludes_irrelevant_sections():
    workflow = _workflow()
    continuous = " ".join(workflow_status_lines(workflow))
    assert "Continuous Stability" in continuous
    assert "Calibration" not in continuous
    workflow.add_event(time_s=10, name="Event")
    event = " ".join(workflow_status_lines(workflow))
    assert "Event Response" in event and "Calibration" in event
    assert "Analysis 各 record" not in event and "Early" not in event


def test_footer_remains_outside_mode_host_and_run_button_visible(mode_panel):
    root, panel, _workflow_state = mode_panel
    for geometry in ("900x650", "1280x800", "1500x900"):
        root.geometry(geometry); root.update()
        assert panel.footer.winfo_manager() == "grid"
        assert panel.run_button.winfo_manager() == "grid"
        assert panel.run_button.winfo_viewable()
