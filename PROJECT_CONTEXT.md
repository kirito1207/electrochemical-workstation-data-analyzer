# Project Context

## Project identity and scope

Electrochemical Workstation Data Analyzer is a desktop-oriented electrochemical data analysis project. Its repository-level identity is generic, while its currently validated native binary parser is deliberately narrower: real-file validation primarily covers CH Instruments CHI760E Linear Sweep Voltammetry (LSV) and Amperometric i-t Curve data. The project must not claim support for every workstation vendor or describe the parser as universal.

The current development state is **Stage 5.2.3**, including the Stage 5.2 Generic LSV formal-analysis GUI, Stage 5.2.1 usability/workspace hardening, the Stage 5.2.1.1 selected-potential scatter hover hit-test hotfix, Stage 5.2.2 multi-group/layout hardening, and Stage 5.2.3 overall multi-group condition-effect statistics. Development history remains cumulative.

## Architecture

- `src/chi_parser/`: strict, validated, technique-specific CHI760E parsing and diagnostics.
- `src/analysis/`: generic metadata, selected-potential LSV analysis/statistics, sign QC, MAD flags, technique routing, and the i-t analysis backend.
- `src/plotting/`: scientific figures built from analysis results.
- `src/export/`: CSV, Excel, figures, and provenance logs.
- `src/chi_gui/`: Tkinter/ttk desktop GUI and independent Workspace state.
- `src/presets/`: optional experiment-specific workflows; PB42 is a preset, not the generic core.
- `tests/`: parser, analysis, export, plotting-adjacent, and GUI regression tests.

The design is **generic-first**: generic core code must not depend on PB42 group names, sample counts, filenames, or fixed comparisons. PB42/H2O2 remains a useful example, validated experimental workflow, and optional preset. Internal package names such as `chi_parser` and `chi_gui` are intentionally retained until any future package migration is designed and tested as a separate stage.

## Scientific invariants

Raw `.bin` files are read-only. The parser is responsible only for reliable decoding, validation, provenance, and immutable numerical arrays; it must not modify scientific data.

The default pipeline performs no smoothing, normalization, baseline correction, or automatic outlier removal. It must not silently add any of these operations. MAD is a **Possible outlier** flag only and never removes an observation automatically.

For LSV selected-potential analysis, the user explicitly supplies the target potential E*. If E* matches an actual sample within the validated tolerance, the actual sample is used. If E* lies between two valid grid points, current is obtained by linear interpolation. Extrapolation is forbidden. The software must not search for the most significant p-value, largest group difference, “best potential,” or any other data-selected target.

Signed current and absolute magnitude are both retained because magnitude can conceal current-direction reversal. Current-sign QC reports positive, negative, and near-zero counts without changing inclusion or values. A comparison is performed only when explicitly defined by the user; Generic Mode does not automatically generate every pairwise comparison.

## Metadata and statistical membership

`Workspace`, `Group`, and `Electrode Type` are distinct concepts:

- A **Workspace** is an independent GUI working container/session. It may contain multiple Groups and is never converted automatically into a statistical Group.
- A **Group** is a user-confirmed experimental condition.
- **Material** and **Bare** are Electrode Type values. A Bare control may share the same Group as Material electrodes under the same experimental condition.

Current Generic LSV formal statistics use only `Material`. `Bare` remains available for raw visualization, metadata/provenance, and control inspection, but it does not enter Material mean, sample SD, SEM, CV, MAD flags, sign-QC Material counts, pairwise Welch/Mann–Whitney tests, overall Welch ANOVA/Kruskal–Wallis tests, Hedges' g, selected-potential Material scatter, or Material mean curves.

Descriptive output currently includes n, mean, median, sample SD, SEM, CV%, minimum, Q1, Q3, and maximum. Explicit comparisons currently provide a Welch independent-samples t-test, Mann–Whitney sensitivity analysis, mean difference `LEFT - RIGHT`, bootstrap confidence intervals, Hedges' g, and Holm correction within a configured Primary family. Bootstrap seeds and resample counts are recorded for reproducibility.

For 3 or more Material Groups, the current selected-potential metric is also analyzed with one-way Welch ANOVA and Kruskal–Wallis sensitivity analysis using every confirmed included Material Group. The two omnibus results are always reported side by side and never gate explicit pairwise comparisons. With fewer than 3 Groups they are not applicable; formal omnibus calculation also requires `n >= 2` in every participating Group. No group-subset selection, classical equal-variance ANOVA, automatic normality-test routing, Tukey, Games–Howell, or Dunn procedure is implemented.

Each included Material sample is currently treated as one statistical input unit. The software does not infer biological versus technical replication, electrode nesting, paired observations, repeated measures, or batch structure. Experiments with those designs require a separately designed paired, repeated-measures, or mixed-effects analysis; none is implemented in Stage 5.2.3.

## Current GUI and backend status

The GUI currently provides multiple independent Workspaces, file/folder import, raw curve preview, per-curve visibility, numeric cursor control, LSV selected-potential readings, editable metadata, configurable Groups, Bare/Material classification, formal Generic LSV analysis, result tables, publication plots, Sample ID hover on selected-potential scatter, and export. Confirmed Material metadata automatically determines 1, 2, 3, or N Groups. Single-group analysis needs no comparison; multi-group analysis accepts any user-declared pairwise comparisons without generating all pairs automatically. Descriptive tables and scientific plots retain every Material Group. Overall multi-group results appear in their own results tab; the existing Left Group / Right Group / Role / Holm Family / Name pairwise editor is intentionally retained unchanged.

The data page owns an independent horizontal pane layout with bounded left/right minimum widths and a remembered sash fraction. Other workflow pages cannot feed their requested Treeview or canvas width back into the data-page split. Long curve filenames use bounded display labels while their full path remains available in details/provenance.

The i-t backend is implemented: user-confirmed step protocols, plateau extraction, response calculation, calibration, QC, plotting, and export exist. The formal i-t GUI has not yet been implemented. CV and CA are future technique-specific extensions and must not be routed through LSV assumptions.

## Known follow-up work

Stage 5.2.2 addressed the abnormal “数据与曲线” width after analysis and the 1/2/3/N Group GUI workflow. Stage 5.2.3 adds overall Welch ANOVA and Kruskal–Wallis results/export without changing that layout or the pairwise editor. Windows manual regression remains required for result/data tab switching, maximize/restore, stale results, export, hover, and multi-Workspace interaction. The next implementation stage may address the formal i-t GUI only when separately scoped.

The existing `ComparisonDefinition` remains the explicit pairwise contract between any two Groups. Omnibus results are stored separately and must not be inserted into pairwise rows. Do not add Games–Howell, Tukey, Dunn, paired/repeated-measures, or mixed-effects tests without a separate scientific/statistical design discussion.

## Near-term roadmap and change discipline

Future multi-group work may separately consider scientifically selected post-hoc procedures and structured experimental designs. The formal i-t GUI also requires a separate stage. Later CV/CA support requires dedicated parsers and technique-specific scientific semantics. Machine learning, broad vendor claims, large package renames, and new statistical families remain outside scope unless explicitly designed.

Any future change must preserve raw-data immutability, provenance, user-confirmed metadata, explicit target/comparison definitions, non-destructive QC, signed values, and separation of parser, analysis, plotting, export, GUI, and optional presets.
