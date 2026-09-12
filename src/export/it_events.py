"""Generic CSV export for i-t events, windows, responses, and optional calibration."""
from __future__ import annotations
import csv
from dataclasses import asdict
from pathlib import Path
from analysis.it_events import ITAnalysisMode, ITEventBatchResult

def _write(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    return path

def export_it_event_csv_bundle(result: ITEventBatchResult, output_dir):
    output = Path(output_dir)
    if result.mode == ITAnalysisMode.CONTINUOUS:
        legacy_rows = [asdict(row) for row in result.continuous_summaries]
        legacy_fields = tuple(legacy_rows[0]) if legacy_rows else (
            "source_file", "sample_id", "group", "duration_s", "mean_current_uA",
            "sd_current_uA", "min_current_uA", "max_current_uA", "first_time_s",
            "last_time_s", "status",
        )
        stability_rows = []
        interruption_rows = []
        for row in result.stability_records:
            values = asdict(row)
            values["warnings"] = " | ".join(row.warnings)
            values["interruptions"] = "; ".join(
                f"{item.interval_id}:{item.start_s:g}-{item.end_s:g}:{item.interruption_type.value}:{item.reason}"
                for item in row.interruptions
            )
            stability_rows.append(values)
            for item in row.interruptions:
                interruption_rows.append({
                    "source_file": row.source_file, "sample_id": row.sample_id,
                    "group": row.group, "interval_id": item.interval_id,
                    "start_s": item.start_s, "end_s": item.end_s,
                    "type": item.interruption_type.value, "reason": item.reason,
                })
        segment_rows = [asdict(row) for row in result.stability_segments]
        group_rows = [asdict(row) for row in result.stability_group_summaries]
        generated = [_write(output / "continuous_summary.csv", legacy_rows, legacy_fields)]
        generated.append(_write(
            output / "continuous_stability.csv", stability_rows,
            tuple(stability_rows[0]) if stability_rows else
            ("source_file", "sample_id", "group", "record_start_s", "record_end_s",
             "analysis_start_s", "analysis_end_s", "qc_status", "warnings"),
        ))
        generated.append(_write(
            output / "continuous_segments.csv", segment_rows,
            tuple(segment_rows[0]) if segment_rows else
            ("source_file", "sample_id", "group", "segment_id", "start_s", "end_s",
             "duration_s", "n_points", "mean_A", "sd_A", "slope_A_per_s", "r_squared", "status"),
        ))
        generated.append(_write(
            output / "continuous_group_summary.csv", group_rows,
            tuple(group_rows[0]) if group_rows else
            ("group", "metric", "unit", "n", "mean", "sd", "sem", "cv_percent",
             "median", "minimum", "maximum"),
        ))
        generated.append(_write(
            output / "interruptions.csv", interruption_rows,
            tuple(interruption_rows[0]) if interruption_rows else
            ("source_file", "sample_id", "group", "interval_id", "start_s", "end_s", "type", "reason"),
        ))
        return tuple(generated)
    events = [asdict(row) for row in result.timeline.events]
    responses = [asdict(row) for item in result.files for row in item.responses]
    windows = [{"source_file": item.data.file_name, "sample_id": item.sample_id, "group": item.group, **asdict(row)} for item in result.files for row in item.windows]
    summaries = [asdict(row) for row in result.summaries]
    generated = [
        _write(output / "events.csv", events, tuple(events[0]) if events else ("event_id", "time_s", "name", "value", "unit", "notes")),
        _write(output / "event_responses.csv", responses, tuple(responses[0]) if responses else ("source_file", "sample_id", "group", "event_id", "status")),
        _write(output / "response_windows.csv", windows, tuple(windows[0]) if windows else ("source_file", "sample_id", "group", "event_id", "status")),
        _write(output / "event_summary.csv", summaries, tuple(summaries[0]) if summaries else ("group", "event_id", "event_name", "n")),
    ]
    calibrations = [asdict(item.calibration) for item in result.files if item.calibration is not None]
    if calibrations:
        generated.append(_write(output / "calibration.csv", calibrations, tuple(calibrations[0])))
    return tuple(generated)

__all__ = ["export_it_event_csv_bundle"]
