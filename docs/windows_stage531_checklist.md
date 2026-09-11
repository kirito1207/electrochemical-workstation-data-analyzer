# Stage 5.3.1 Windows manual acceptance checklist

Use PowerShell 7 and the existing `.venv`. Do not alter source `.bin` files during this checklist.

- Open i-t and confirm all four pages are enabled; return to LSV and confirm its existing workflow is unchanged.
- Import one record, edit Sample ID/Group/Notes, confirm metadata, create and confirm Events, then run without Calibration.
- Move/click/step the numeric cursor and confirm no Event or formal result changes. Use “从当前游标添加草稿” and confirm the draft uses the selected curve's actual sampled time but leaves Timeline unconfirmed.
- Add arbitrary Unicode Event names, optional numeric values/units and notes. Confirm automatic time sorting, stable IDs after edit, and inline rejection of duplicate times.
- Confirm an empty or edited/unconfirmed Timeline blocks formal analysis while raw preview remains available.
- Verify the GUI explanation: baseline is record start to first Event; each response segment runs from one Event to the next or record end; default tail fraction is 0.20 and invalid values are rejected.
- Inspect Event Response rows for baseline mean, response mean, signed ΔI, magnitude, response SD, requested window bounds and status.
- Analyze records of different duration and confirm missing late Events are retained only as unavailable responses for the shorter record.
- Enable Calibration manually, provide a generic x label/unit and explicitly select numeric Events. Confirm numeric Events are not preselected and mixed units are rejected without conversion.
- Inspect raw + Events, Event Response, and Calibration figures. Hover first/middle/last individual response points and confirm Sample ID/Group/Event/value mapping.
- Modify an Event or response setting after analysis and confirm the result is stale and export is blocked until reanalysis.
- Export a fresh result and confirm generic CSV plus PNG/SVG/PDF figures are written to a new timestamped directory without reanalysis or overwrite.
- Workspace 1 and Workspace 2 must retain independent metadata, Timeline, metric, Calibration, results, selected plot and export path.
- Maximize, restore, resize, switch result/data tabs, switch Workspace and switch LSV/i-t; confirm the data-page preview/right-panel split remains stable.

Stage 5.3.1 does not expose an explicit-window editor and does not add drift, t50/t90, peak, AUC, recovery, automatic event detection, CV/CA, ML, or executable packaging.
