# Stage 5.3.2 Windows manual acceptance checklist

Use PowerShell 7 and the existing virtual environment. Work only with copies or read-only access to experiment files.

## Continuous windows and stability

- Import a roughly 1000 s i-t record with no Event and confirm Sample ID/Group metadata.
- Leave Analysis range blank once and verify it resolves to the record's actual first/last sample.
- Set Analysis to 0–1000 s, Early to 100–200 s, and Late to 900–1000 s; verify Early/Late, signed change, Retention, drift and R².
- Compare Analysis 0–1000 s with 100–1000 s for a rapid-start record; values may differ and the software must not choose one automatically.
- Verify the raw plot still shows the complete immutable curve and highlights Analysis, Early and Late ranges.

## Interruption-aware QC

- Add a per-record 2–4 s interruption with each type; edit by button and double-click, then delete it.
- Verify invalid start/end, out-of-record bounds and overlapping intervals are rejected or reported without changing raw arrays.
- Verify the raw figure shades the interruption while retaining the original samples.
- With Early 0.5–1.5 s and Late 900–1000 s, verify Retention remains available but is flagged as crossing an interruption.
- With Early 1–3 s overlapping a 2–4 s interruption, verify Early and Retention are unavailable; no subset is silently recomputed.
- Verify separate pre-gap and post-gap `segment_N` rows and no single overall drift across the gap.
- Use records of different lengths; an uncovered window should affect only that record.

## Group, export, Workspace, and regressions

- Verify Record Stability, Segment / Interruption QC and Group Summary tables.
- Verify Retention plot has a 100% reference and Drift plot has a zero reference.
- Export and inspect `continuous_stability.csv`, `continuous_segments.csv`, `continuous_group_summary.csv`, `interruptions.csv` and all continuous figures.
- Change a window, interruption, Group or Include state after analysis; verify the result becomes stale and cannot be exported until rerun.
- Configure different windows/interruptions in two Workspaces and verify no state crosses between them.
- In LSV, select multiple rows and use “不纳入/纳入”; verify only selected rows change, confirmation is invalidated, and Group/Electrode Type controls still work.
- Define an Event and rerun the established Event workflow; verify Event responses and optional Calibration are unchanged.
