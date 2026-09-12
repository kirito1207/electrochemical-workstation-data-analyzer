# Stage 5.3.1.2 Windows manual acceptance checklist

- Add Event A/B/C to Default Timeline and confirm the visible `#` column is 1/2/3 with no Internal ID column.
- Delete the first Event and confirm visible numbering becomes 1/2. Add another Event and confirm it becomes 1/2/3 while internal IDs remain unique and are not reused.
- Reorder by editing an Event time and confirm display numbering follows time order while edit/delete still target the correct Event.
- Create a Sample override, delete a middle Event, add a new one and confirm visible numbering remains continuous while formal alignment still follows event_id.
- Select Calibration Events and confirm labels use display numbers rather than `event_N`; analyze and verify the underlying selected event_ids and CSV provenance remain correct.
- Complete an analysis, modify a Sample override and confirm the result becomes stale while the full run button remains visible and enabled.
- Trigger long validation/feedback text and use a long Chinese Sample ID/Timeline label; confirm text wraps and does not push the run button off-screen.
- Check narrow normal size, maximize and restore. The run button must remain fully visible; only a running background task may disable it.
- Confirm Calibration disabled/enabled selector behavior from Stage 5.3.1.1 remains intact.
- Confirm LSV metadata, multi-group, omnibus, pairwise, hover, plotting, layout and export remain unchanged.

Workspace display-number cleanup and new scientific features are outside Stage 5.3.1.2.
