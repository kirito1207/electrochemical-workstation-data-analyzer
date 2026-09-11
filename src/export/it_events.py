"""Generic CSV export for i-t events, windows, responses, and optional calibration."""
from __future__ import annotations
import csv
from dataclasses import asdict
from pathlib import Path
from analysis.it_events import ITEventBatchResult

def _write(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    return path

def export_it_event_csv_bundle(result: ITEventBatchResult, output_dir):
    output = Path(output_dir)
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
