# Stage 5.3 Windows manual acceptance checklist

- Confirm raw i-t preview and numeric cursor still work without a Timeline.
- Confirm a future Event draft can take cursor time but is not formally added without confirmation.
- Exercise Events with no value, arbitrary names, Unicode units, and notes.
- Verify Event edits mark any future result stale rather than rerunning automatically.
- Verify 1, 2, and N included records with arbitrary Sample ID/Group labels.
- Use records of different duration and confirm late Events are unavailable only for the short record.
- Confirm each formal response uses at least two samples and exposes baseline/response mean, SD, n, signed delta, and magnitude.
- Confirm calibration is absent by default and uses only explicitly selected Events when enabled.
- Confirm missing values or inconsistent units block calibration without automatic conversion.
- Check `events.csv`, `response_windows.csv`, `event_responses.csv`, `event_summary.csv`, and optional `calibration.csv`.
- Confirm raw event-marker figure labels arbitrary Event names/value/unit.
- Re-run LSV result tabs, hover, Workspace switching, and data-page layout regression.

Stage 5.3 does not yet add the formal i-t Event editor GUI; these GUI-specific interactions remain acceptance criteria for that later implementation.
