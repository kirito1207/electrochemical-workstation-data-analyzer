# Stage 5.3.2.1 Windows manual acceptance checklist

Use the existing PowerShell 7 environment and virtual environment.

## Continuous presentation

- Import i-t records without defining an Event and open “分析设置”.
- Confirm the metadata table stays at the top and the mode label says Continuous Stability.
- Confirm the large empty Event Timeline and Event response/Calibration areas do not occupy space.
- Confirm Stability Windows and 数据质量 / 中断区间 are visually separate.
- Confirm Analysis/Early/Late rows are compact, the help text wraps cleanly, and the interruption table defaults to three rows with a scrollbar.
- Confirm the workflow status contains no irrelevant Calibration line.

## Event entry and transitions

- Click “进入 Event 设置”; confirm the full Timeline editor appears but the scientific mode remains Continuous until an Event is actually added.
- Add the first Event and confirm the page remains in Event context even before Timeline confirmation.
- Confirm Default Timeline/sample override selection, display indices, cursor draft, edit/delete and confirmation controls remain available.
- Confirm Continuous Stability no longer occupies Event-mode space.
- Delete the last Event and confirm the page automatically returns to Continuous presentation with prior Analysis/Early/Late/interruption settings intact.

## Calibration progressive disclosure

- In Event mode with Calibration unchecked, confirm only its checkbox and short description occupy space.
- Enable Calibration and confirm x label, x unit, explicit Event list and apply action appear.
- Disable it and confirm those controls hide; where existing workflow semantics retain state, re-enabling should restore it.

## Resize and regressions

- Check 1280×800, a narrower normal window, maximize and restore.
- Confirm Confirm Metadata, Timeline actions, feedback and the run button remain visible and usable.
- Switch between Workspaces with different modes; confirm presentation and scientific state do not leak.
- Rerun representative Continuous stability/interruption analysis and Event response/Calibration analysis; verify numerical results and exports are unchanged.
- Recheck LSV batch Include, Group, Electrode Type, selected-potential, omnibus, pairwise, plots and export.
