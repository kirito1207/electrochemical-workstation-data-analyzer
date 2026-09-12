# Stage 5.3.1.1 Windows manual acceptance checklist

- Confirm the metadata section title is exactly “① 样本信息”.
- Double-click Event, Time / s, Value, Unit and Notes cells; each must open the whole-row editor. Event ID must remain unchanged and the Edit button must still work.
- Edit an Event time after analysis; its Timeline must become unconfirmed, the result must become stale, and export must be blocked.
- Add five Events to Default Timeline. Select Sample A, confirm the inherited-state label, and verify add/edit/delete asks for an override instead of changing Default.
- Create Sample A override and confirm it is copied from Default with matching event_id values. Change only event_1 time and confirm the override.
- Leave Sample B without an override, analyze, and verify A uses its custom time while B uses Default time.
- Delete a middle Event from one override and verify later responses remain associated by event_id rather than shifting by row position.
- Restore Sample A to Default and verify its override is removed and the result becomes stale.
- Rename Sample ID after creating an override; verify the override remains attached and its displayed label updates.
- Toggle Include off/on and verify the override is retained. Remove the file and verify the orphan override is removed safely.
- Create different Default/override states in two Workspaces and verify they never cross.
- Use Chinese Sample IDs/Groups/Events including 玻碳2、温度变化、光照开启、加样、应激、样本、事件 and units µM、μM、°C. Inspect raw preview, Raw + Events, Event Response, Calibration, LSV figures and exported PNG/SVG/PDF for missing glyph boxes.
- Run with Calibration disabled and confirm the plot selector has no Calibration entry and no calibration figure/CSV is generated.
- Run with Calibration enabled and confirmed compatible Events; confirm the Calibration option appears. Disable and rerun; confirm the option disappears and any prior Calibration selection falls back to Raw + Events.
- Recheck maximize/restore, data/result tab switching, Workspace switching and LSV/i-t switching for layout stability.

This stage does not add drift, peak, t50/t90, AUC, recovery, automatic Event detection, unit conversion, CV/CA, ML, or packaging.
