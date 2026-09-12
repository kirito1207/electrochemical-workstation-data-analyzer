# Stage 5.3.1.3.1 Windows manual acceptance checklist

- Import 10 i-t files and select the first five rows with the same click/Ctrl/Shift/drag gestures used in LSV.
- Click the editable Group Combobox and type `PB_A`; verify all five Treeview rows remain visibly selected.
- Click “设置 Group”; verify only the first five rows change to `PB_A` and the Combobox choices now include it.
- Select the last five rows, set `PB_B`, and verify the first five remain unchanged.
- Press Ctrl+A, click “不纳入”, and verify all rows become excluded without deleting sample Timeline overrides.
- With the same rows selected, click “纳入” and verify all rows become included again.
- Use “设置备注” for selected rows, including an empty value to clear Notes.
- Click “设置 Group” with no selection and verify inline feedback says to select samples first.
- Double-click one Sample ID and verify the existing single-row editor still works; no same-value Sample ID batch action should exist.
- After each batch change, verify metadata requires confirmation again and any completed result becomes stale without automatic rerun.
- Verify No-Event Continuous analysis and confirmed Event analysis both still run unchanged.
- Verify the footer run button remains visible with long feedback and after inline batch operations.
- Switch between LSV and i-t and confirm the selection → Group input → Set Group mental model is consistent.

Parser, Continuous/Event scientific calculations, event identity, Timeline inheritance, Calibration and plotting values are outside this hotfix.
