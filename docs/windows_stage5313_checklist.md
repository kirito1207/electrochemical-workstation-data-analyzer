# Stage 5.3.1.3 Windows manual acceptance checklist

## LSV-consistent i-t metadata selection

- Import 10 i-t files. Verify normal click, Ctrl-click, Shift-click, Ctrl+A and drag range selection match the LSV metadata table.
- Use Select All and Clear Selection, then open “批量设置选中行”; verify the dialog reports the selected row count.
- Assign Group `PB_A` to the first five rows and `PB_B` to the last five rows.
- Batch-replace Notes, batch Include=False, then Include=True. Verify metadata confirmation is invalidated after each batch.
- Confirm a pre-existing sample Timeline override remains attached to the same record after Group/Notes/Include changes.
- Double-click one cell while several rows are selected. Verify only that row receives the normal single-row editor.
- Verify Sample ID has no unsafe same-value batch operation.

## Event-optional formal analysis

- In a new Workspace, import i-t files, complete and confirm metadata, define no Events and do not confirm Timeline. Formal analysis must succeed in Continuous mode.
- Verify Continuous Summary contains every included Sample ID/Group and full-record duration, mean, sample SD, min/max current, first/last time and status.
- Verify the result plot selector contains only `Raw i-t / Continuous`, curves cover the complete time range, and no Event marker appears.
- Export and verify `continuous_summary.csv` plus raw PNG/SVG/PDF exist; Event/response/Calibration CSVs must not exist.
- Add one Event without confirming. Formal analysis must be blocked with a Timeline confirmation message.
- Confirm the Timeline and rerun. Event Response must return and the unchanged optional Calibration workflow must remain available.
- Delete the final Event. Verify the prior result becomes stale, mode returns to Continuous, and Calibration is cleared/disabled.
- Add the first Event again. Verify mode becomes Event, the result becomes stale, and confirmation is required.

## Layout and regressions

- With long feedback, many selected rows and after closing the batch dialog, verify the analysis footer button remains fully visible.
- Maximize and restore the window; verify the footer and metadata table remain usable.
- Verify Event display index remains separate from stable `event_id`, including sample overrides.
- Verify Event-mode values, CJK labels (`玻碳`, `温度`, `光照`, `稳定性`, `过氧化氢`, `µM`, `°C`), LSV workflows and Calibration plot hiding remain unchanged.

Advanced stability/kinetic metrics, CV and CA remain outside Stage 5.3.1.3.
