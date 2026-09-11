# Project Context

## Project identity and scope

Electrochemical Workstation Data Analyzer is a desktop-oriented electrochemical data analysis project. Its repository-level identity is generic, while its currently validated native binary parser is deliberately narrower: real-file validation primarily covers CH Instruments CHI760E Linear Sweep Voltammetry (LSV) and Amperometric i-t Curve data. The project must not claim support for every workstation vendor or describe the parser as universal.

The current development state is **Stage 5.2.1.1**, including the Stage 5.2 Generic LSV formal-analysis GUI, Stage 5.2.1 usability/workspace hardening, and the selected-potential scatter hover hit-test hotfix. Development history remains cumulative; the repository rename does not reset its stages.

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

Current Generic LSV formal Material statistics use only `Material`. `Bare` remains available for raw visualization, metadata/provenance, and control inspection, but it does not enter Material mean, sample SD, SEM, CV, MAD flags, sign-QC Material counts, Welch tests, Mann–Whitney tests, Hedges' g, selected-potential Material scatter, or Material mean curves.

Descriptive output currently includes n, mean, median, sample SD, SEM, CV%, minimum, Q1, Q3, and maximum. Explicit comparisons currently provide a Welch independent-samples t-test, Mann–Whitney sensitivity analysis, mean difference `LEFT - RIGHT`, bootstrap confidence intervals, Hedges' g, and Holm correction within a configured Primary family. Bootstrap seeds and resample counts are recorded for reproducibility.

## Current GUI and backend status

The GUI currently provides multiple independent Workspaces, file/folder import, raw curve preview, per-curve visibility, numeric cursor control, LSV selected-potential readings, editable metadata, configurable Groups, Bare/Material classification, formal Generic LSV analysis, result tables, publication plots, Sample ID hover on selected-potential scatter, and export.

The i-t backend is implemented: user-confirmed step protocols, plateau extraction, response calculation, calibration, QC, plotting, and export exist. The formal i-t GUI has not yet been implemented. CV and CA are future technique-specific extensions and must not be routed through LSV assumptions.

## Known follow-up work (not part of this repository-identity stage)

1. Fix the abnormal page width/layout when returning to “数据与曲线” after analysis.
2. Ensure Generic analysis handles 1, 2, 3, and N Groups throughout the GUI without assuming exactly two.
3. Continue to the formal i-t GUI only after the LSV GUI follow-ups are separately scoped.

The existing `ComparisonDefinition` remains suitable for explicit pairwise comparisons between any Groups. Do not add ANOVA, Games–Howell, Tukey, Kruskal–Wallis, or Dunn tests without a separate scientific/statistical design discussion.

## Near-term roadmap and change discipline

The next work should address the two known Generic LSV GUI issues above, then separately design the i-t formal GUI. Later CV/CA support requires dedicated parsers and technique-specific scientific semantics. Machine learning, broad vendor claims, large package renames, and new statistical families are outside the current roadmap unless explicitly scoped.

Any future change must preserve raw-data immutability, provenance, user-confirmed metadata, explicit target/comparison definitions, non-destructive QC, signed values, and separation of parser, analysis, plotting, export, GUI, and optional presets.
